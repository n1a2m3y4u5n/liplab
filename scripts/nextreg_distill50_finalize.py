"""Validate existing C50 artifacts and aggregate the two fixed development seeds.

No torch import, model loading, inference, training, export, or timing occurs.
"""
import argparse
import copy
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

TEACHER_SHA = 'd499c9f26affd57ef9cc4014c48337669ecfed7466a1ef8ac81c68742007ca1a'
INPUT_SHA = '3b2b48ccab377f037ed82015d9cbc84f811392a4c3fa7fa7539a744534c8ccc7'
THRESHOLDS = {'accuracy_delta_min': -.02, 'size_ratio_max': .6, 'latency_ratio_max': .6}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def number(value, name, positive=False):
    require(isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value), name + ': invalid number')
    require(not positive or value > 0, name + ': must be positive')
    return float(value)


def digest(value, name):
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{64}', value) is not None, name + ': invalid SHA256')
    return value.lower()


def equal_number(actual, expected, name):
    require(math.isclose(number(actual, name), expected, rel_tol=1e-10, abs_tol=1e-10), name + ': inconsistent')


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def validate_seed(seed, payload, folder, artifact_sha=file_sha):
    """artifact_sha is injectable solely for synthetic self-tests."""
    try:
        s, e, w = (payload[k] for k in ('selection', 'export', 'wasm'))
        require(seed in (0, 1), 'unexpected seed')
        require(s['seed'] == seed and s['student']['seed'] == seed and e['seed'] == seed, 'seed mismatch')
        require(s['teacher']['seed'] == 0 and s['size'] == '50', 'wrong teacher seed or capacity')
        require(s['status'] == 'validation_selection_only_no_adjudication', 'wrong selection scope')
        for key, value in THRESHOLDS.items():
            equal_number(s['thresholds'][key], value, 'threshold ' + key)
        equal_number(e['size_ratio_max'], .6, 'export size threshold')
        require(digest(s['teacher']['checkpoint_sha256'], 'teacher checkpoint') == TEACHER_SHA, 'fixed B33 teacher changed')
        student_pt_sha = digest(s['student']['checkpoint_sha256'], 'student checkpoint')
        require(digest(artifact_sha(Path(folder) / 'model.pt'), 'actual model.pt') == student_pt_sha, 'model.pt SHA mismatch')
        speaker_sets = []
        for label in ('teacher', 'student'):
            mean = number(s[label]['mean'], label + ' mean')
            require(0 <= mean <= 1, label + ': mean outside accuracy range')
            require(number(s[label]['cer'], label + ' CER') >= 0, label + ': negative CER')
            by = s[label]['by_speaker']
            require(set(by) == {'1', '2'}, label + ': wrong duplication conditions')
            keys = set(by['1'])
            require(len(keys) == 12 and set(by['2']) == keys, label + ': expected same 12 validation speakers')
            for row in by.values():
                require(all(0 <= number(v, 'speaker accuracy') <= 1 for v in row.values()), 'speaker accuracy outside range')
            computed = statistics.mean(statistics.mean(row.values()) for row in by.values())
            equal_number(mean, computed, label + ' speaker mean')
            speaker_sets.append(keys)
        require(speaker_sets[0] == speaker_sets[1], 'teacher/student validation speakers differ')
        delta = float(s['student']['mean']) - float(s['teacher']['mean'])
        equal_number(s['accuracy_delta'], delta, 'accuracy delta')
        accuracy_ok = delta >= -.02
        require(s['accuracy_ok'] is accuracy_ok, 'selection accuracy flag inconsistent')

        model_shas = {}
        for label in ('teacher', 'student'):
            row = e[label]
            require(isinstance(row['bytes'], int) and not isinstance(row['bytes'], bool) and row['bytes'] > 0, 'invalid ONNX bytes')
            for key in ('wrap_diff', 'onnx_diff'):
                require(0 <= number(row[key], label + ' ' + key) < .001, label + ': ONNX technical validity failed')
            model_shas[label] = digest(row['sha256'], label + ' ONNX')
            require(model_shas[label] == digest(w['model_sha256'][label], label + ' WASM model'), label + ': WASM/export SHA mismatch')
            model_path = Path(folder) / (label + '.onnx')
            require(digest(artifact_sha(model_path), 'actual ' + label + '.onnx') == model_shas[label], label + '.onnx actual SHA mismatch')
            # file length is checked by the real loader; synthetic tests inject hashes only.
        size_ratio = e['student']['bytes'] / e['teacher']['bytes']
        equal_number(e['size_ratio'], size_ratio, 'size ratio')
        size_ok = size_ratio <= .6
        require(e['size_ok'] is size_ok, 'export size flag inconsistent')

        require(w['execution_provider'] == 'onnxruntime-web WASM CPU', 'wrong runtime provider')
        require(w['ort_version'] == '1.19.2' and w['num_threads'] == 1, 'wrong WASM version or threads')
        require(isinstance(w['node'], str) and w['node'].startswith('v24.'), 'wrong Node version')
        require(all(isinstance(w[k], str) and w[k] for k in ('host', 'cpu', 'protocol')), 'missing runtime environment')
        require('5 warmups' in w['protocol'] and '20 alternating-order pairs' in w['protocol'], 'wrong timing protocol')
        require(digest(w['input_sha256'], 'WASM input') == INPUT_SHA, 'wrong fixed WASM input')
        medians = {}
        for label in ('teacher', 'student'):
            samples = w['samples_ms'][label]
            require(isinstance(samples, list) and len(samples) == 20, label + ': expected 20 timing samples')
            for value in samples:
                number(value, label + ' sample', positive=True)
            medians[label] = statistics.median(samples)
            equal_number(w[label + '_median_ms'], medians[label], label + ' timing median')
        latency_ratio = medians['student'] / medians['teacher']
        equal_number(w['latency_ratio'], latency_ratio, 'latency ratio')
        # The shared historical harness emits latency_ok at 0.50. Ignore it.
        latency_ok = latency_ratio <= .6
        gates = {'accuracy': accuracy_ok, 'fp32_onnx_size': size_ok, 'cpu_wasm_latency': latency_ok}
        return {
            'seed': seed, 'seed_pass': all(gates.values()), 'gates': gates, 'thresholds': THRESHOLDS,
            'accuracy_delta': delta, 'teacher_accuracy': s['teacher']['mean'], 'student_accuracy': s['student']['mean'],
            'teacher_cer': s['teacher']['cer'], 'student_cer': s['student']['cer'],
            'size_ratio': size_ratio, 'latency_ratio': latency_ratio,
            'teacher_onnx_bytes': e['teacher']['bytes'], 'student_onnx_bytes': e['student']['bytes'],
            'teacher_median_ms': medians['teacher'], 'student_median_ms': medians['student'],
            'teacher_checkpoint_sha256': TEACHER_SHA, 'student_checkpoint_sha256': student_pt_sha,
            'onnx_sha256': model_shas, 'artifact_hashes_verified': True,
            'runtime': {k: w[k] for k in ('host', 'cpu', 'ort_version', 'node', 'num_threads', 'input_sha256')},
            'validation_speakers': sorted(speaker_sets[0]), 'legacy_latency_ok_ignored': True,
            'status': 'validation_selection_only_no_adjudication', 'no_best_seed_selection': True,
        }
    except KeyError as exc:
        raise ValueError('Missing input field: ' + str(exc)) from exc


def combine(rows):
    require(len(rows) == 2 and [r['seed'] for r in rows] == [0, 1], 'expected ordered seed0 and seed1')
    require(rows[0]['runtime'] == rows[1]['runtime'], 'WASM must use same PC, CPU, versions, threads and input')
    require(rows[0]['validation_speakers'] == rows[1]['validation_speakers'], 'seed validation speakers differ')
    require(rows[0]['student_checkpoint_sha256'] != rows[1]['student_checkpoint_sha256'], 'both seeds reference identical checkpoint bytes')
    stable = all(r['seed_pass'] for r in rows)
    return {'candidate': 'distill50', 'stable_pass': stable, 'seed_pass': {str(r['seed']): r['seed_pass'] for r in rows},
            'thresholds_each_seed': THRESHOLDS, 'teacher_checkpoint_sha256': TEACHER_SHA,
            'seeds': rows, 'status': 'validation_selection_only_no_adjudication',
            'conclusion': '안정 통과' if stable else '안정 통과 아님',
            'no_best_seed_selection': True, 'independent_adjudication': False,
            'historical_38_results_untouched': True, 'n_train_speakers_registered': 33, 'n_validation_speakers': 12}


def card(row):
    return f"""# 50% ROI 증류 학생 seed{row['seed']} 개발 모델 카드

- 용도: 등록된 두 시드 개발 선택. 학습33명·검증12명이며 검증 화자는 이전 선택에도 사용됐다. 독립 판정·제품 성능·앱 반영 없음, 깨끗한 평가 대기.
- 구조: 파라미터3,030,525개(선생의50.1161%),40×40 내부입력, stem16, 잔차24·48·96·192,256특징, BiGRU2층276,53자모 CTC. FP32 ONNX.
- 선생은 B33 seed0 SHA256 `{TEACHER_SHA}`다. 학생 seed{row['seed']} SHA256 `{row['student_checkpoint_sha256']}`. 고정 선생·같은 분할·증류·배치 규칙, 학생 시드만 다르다.
- 검증4지: 선생{row['teacher_accuracy']:.9f}, 학생{row['student_accuracy']:.9f}, 차{row['accuracy_delta']:+.9f}; 기준≥−0.02, 통과={row['gates']['accuracy']}.
- 검증 문장CER(보조): 선생{row['teacher_cer']:.9f}, 학생{row['student_cer']:.9f}. 별도 관문이 아니다.
- FP32 ONNX 크기 비율{row['size_ratio']:.9f}, 기준≤0.60, 통과={row['gates']['fp32_onnx_size']}. 같은PC WASM 시간 비율{row['latency_ratio']:.9f}, 기준≤0.60, 통과={row['gates']['cpu_wasm_latency']}.
- 이 시드의 세 관문 통과={row['seed_pass']}. 최종 안정 통과는 상위 decision.json에서 두 시드가 모두 통과할 때만 인정한다. 좋은 시드 선택·과거38% 결과 수정은 없다.
- PT는 로드하지 않고 파일 SHA만 확인했다. 실제 teacher/student ONNX SHA와 WASM 입력 모델 SHA를 대조했다. 집계기는 추론·학습·새 측정·원자료 접근을 하지 않았다.
- KMSAV·평가19명·clean_eval·E2·OLKAVS는 등록상 사용하지 않았다. 검증12명 개발 선택이라는 한계를 유지하며 모델을 앱에 직접 연결하지 않는다.
"""


def finalize(root):
    root = Path(root).resolve()
    targets = [root / f'seed{s}' / name for s in (0, 1) for name in ('decision.json', 'MODEL_CARD.md')] + [root / 'decision.json']
    require(not any(p.exists() for p in targets), 'Refuse existing decision or model card; no overwrites')
    rows = []
    for seed in (0, 1):
        folder = root / f'seed{seed}'
        paths = {name: folder / (name + '.json') for name in ('selection', 'export', 'wasm')}
        payload = {name: json.loads(path.read_text(encoding='utf-8-sig')) for name, path in paths.items()}
        row = validate_seed(seed, payload, folder)
        for label in ('teacher', 'student'):
            require((folder / (label + '.onnx')).stat().st_size == payload['export'][label]['bytes'], label + '.onnx actual bytes mismatch')
        row['source_json_sha256'] = {name: file_sha(path) for name, path in paths.items()}
        rows.append(row)
    top = combine(rows)
    contents = []
    for row in rows:
        folder = root / f"seed{row['seed']}"
        contents.extend([(folder / 'decision.json', json.dumps(row, indent=2, ensure_ascii=False)),
                         (folder / 'MODEL_CARD.md', card(row))])
    contents.append((root / 'decision.json', json.dumps(top, indent=2, ensure_ascii=False)))
    created = []
    try:
        for path, text in contents:
            with path.open('x', encoding='utf-8', newline='\n') as f:
                created.append(path)
                f.write(text + '\n')
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return top


def self_test():
    protocol = '5 warmups/model; 20 alternating-order pairs; median walltime session.run only'

    def fixture(seed):
        student_pt = str(seed + 1) * 64
        means = {'teacher': .45, 'student': .44}
        selection = {'seed': seed, 'size': '50', 'status': 'validation_selection_only_no_adjudication',
                     'thresholds': THRESHOLDS, 'accuracy_delta': -.01, 'accuracy_ok': True}
        for label in means:
            selection[label] = dict(mean=means[label], cer=.6, seed=seed if label == 'student' else 0,
                                    checkpoint_sha256=student_pt if label == 'student' else TEACHER_SHA,
                                    by_speaker={d: {f'p{i}': means[label] for i in range(12)} for d in ('1', '2')})
        export = {'seed': seed, 'size_ratio_max': .6, 'size_ratio': .5, 'size_ok': True,
                  'teacher': dict(bytes=200, sha256='a' * 64, wrap_diff=0, onnx_diff=0),
                  'student': dict(bytes=100, sha256='b' * 64, wrap_diff=0, onnx_diff=0)}
        wasm = dict(execution_provider='onnxruntime-web WASM CPU', ort_version='1.19.2', num_threads=1,
                    node='v24.22.1', host='synthetic-host', cpu='synthetic-cpu', protocol=protocol, input_sha256=INPUT_SHA,
                    model_sha256={'teacher': 'a' * 64, 'student': 'b' * 64},
                    samples_ms={'teacher': [100.] * 20, 'student': [55.] * 20},
                    teacher_median_ms=100., student_median_ms=55., latency_ratio=.55, latency_ok=False)
        hashes = {'model.pt': student_pt, 'teacher.onnx': 'a' * 64, 'student.onnx': 'b' * 64}
        return dict(selection=selection, export=export, wasm=wasm), lambda p: hashes[p.name]

    def validate(seed, payload=None, checker=None):
        data, check = fixture(seed)
        return validate_seed(seed, payload or data, Path('synthetic'), checker or check)

    results = []
    good = combine([validate(0), validate(1)])
    require(good['stable_pass'], 'synthetic pass failed')
    require(good['seeds'][0]['gates']['cpu_wasm_latency'], 'legacy 0.50 flag was incorrectly used')
    results.append('passed_both_seeds_legacy_050_flag_ignored')
    bad, check = fixture(1)
    bad['selection']['student']['mean'] = .42
    bad['selection']['student']['by_speaker'] = {d: {f'p{i}': .42 for i in range(12)} for d in ('1', '2')}
    bad['selection'].update(accuracy_delta=.42-.45, accuracy_ok=False)
    require(not combine([validate(0), validate(1, bad, check)])['stable_pass'], 'failure was masked')
    results.append('one_seed_failure_not_stable')
    for name, mutate in [
        ('wrong_seed_rejected', lambda d: d['selection']['student'].update(seed=1)),
        ('wrong_wasm_hash_rejected', lambda d: d['wasm']['model_sha256'].update(student='c' * 64)),
        ('missing_field_rejected', lambda d: d.pop('export')),
    ]:
        payload, checker = fixture(0)
        mutate(payload)
        try:
            validate(0, payload, checker)
        except ValueError:
            results.append(name)
        else:
            raise AssertionError(name)
    try:
        validate(0, checker=lambda p: 'f' * 64)
    except ValueError:
        results.append('actual_artifact_hash_mismatch_rejected')
    else:
        raise AssertionError('actual artifact SHA mismatch accepted')
    return {'synthetic_self_tests_passed': len(results), 'tests': results, 'no_real_results_read_or_written': True}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root')
    p.add_argument('--self-test', action='store_true')
    a = p.parse_args()
    if a.self_test:
        result = self_test()
    else:
        p.error('--root required unless --self-test') if not a.root else None
        result = finalize(a.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
