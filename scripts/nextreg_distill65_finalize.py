"""Validate existing C65 artifacts and aggregate the two fixed development seeds.

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
from datetime import datetime

TEACHER_SHA = 'd499c9f26affd57ef9cc4014c48337669ecfed7466a1ef8ac81c68742007ca1a'
INPUT_SHA = '3b2b48ccab377f037ed82015d9cbc84f811392a4c3fa7fa7539a744534c8ccc7'
THRESHOLDS = {'accuracy_delta_min': -.02, 'size_ratio_max': .75, 'latency_ratio_max': .6}
COUNTS = {'teacher_parameters': 6047005, 'student_parameters': 3940973,
          'student_front_parameters': 741920, 'student_head_parameters': 3199053}
PAIR_INPUT = {'roi': INPUT_SHA, 'lips': '7c8383e4a505b00880d73e2079d59cb4167efba8aa112109c8affb14b8ce9ad3',
              'combined': '0fe46e1232254fb6193d2fd25d295893394894f2058337f67d018fe771b6c2a8'}
ROI_PROTOCOL = '5 warmups/model; 20 alternating-order pairs; median walltime session.run only; B1 T75 80x80 deterministic uint8-range float32'
PAIR_PROTOCOL = '5 warmups/model; 20 alternating-order pairs; median walltime session.run only; roi B1T75x80x80 plus lips B1T75x80; xorshift20261102'
GLOBAL_ORDER = ['C0', 'C1', 'D0', 'D1', 'C65s0', 'C65s1']


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


def wasm_environment(w, paired):
    require(w['execution_provider'] == 'onnxruntime-web WASM CPU', 'wrong global WASM provider')
    require(w['ort_version'] == '1.19.2' and type(w['num_threads']) is int and w['num_threads'] == 1,
            'wrong global WASM version or threads')
    require(isinstance(w['node'], str) and w['node'].startswith('v24.'), 'wrong global Node version')
    require(w['host'].upper() == 'CNSAI2025' and isinstance(w['cpu'], str) and bool(w['cpu']), 'wrong global PC/CPU')
    require(w['protocol'] == (PAIR_PROTOCOL if paired else ROI_PROTOCOL), 'wrong global timing protocol')
    require(w['input_sha256'] == (PAIR_INPUT if paired else INPUT_SHA), 'wrong global fixed input hash')
    names = ('full', 'compact') if paired else ('teacher', 'student')
    medians = {}
    for name in names:
        digest(w['model_sha256'][name], 'global ' + name + ' model')
        samples = w['samples_ms'][name]
        require(isinstance(samples, list) and len(samples) == 20, 'global timing needs20 raw samples/model')
        for value in samples:
            number(value, 'global raw timing', positive=True)
        medians[name] = statistics.median(samples)
        equal_number(w[name + '_median_ms'], medians[name], 'global ' + name + ' median')
    equal_number(w['latency_ratio'], medians[names[1]] / medians[names[0]], 'global latency ratio')
    stamp = datetime.fromisoformat(w['time'].replace('Z', '+00:00'))
    require(stamp.tzinfo is not None and stamp.utcoffset() is not None, 'global timestamp must include timezone')
    env = {key: w[key] for key in ('host', 'cpu', 'node', 'ort_version', 'num_threads', 'execution_provider')}
    env['host'] = env['host'].upper()
    return env, stamp


def validate_global_order(wasms):
    require(len(wasms) == 6, 'Expected global C0 C1 D0 D1 C65s0 C65s1')
    checks = [wasm_environment(w, i in (2, 3)) for i, w in enumerate(wasms)]
    require(all(env == checks[0][0] for env, _ in checks), 'All six timings must share exact PC/CPU/Node/ORT/threads')
    require(all(a[1] < b[1] for a, b in zip(checks, checks[1:])), 'Global WASM timestamps violate fixed strict order')
    return {'order': GLOBAL_ORDER, 'timestamps': [w['time'] for w in wasms], 'runtime_environment': checks[0][0],
            'roi_input_sha256': INPUT_SHA, 'paired_input_sha256': PAIR_INPUT, 'no_remeasurement': True}


def validate_seed(seed, payload, folder, artifact_sha=file_sha):
    """artifact_sha is injectable solely for synthetic self-tests."""
    try:
        s, e, w, arch, train = (payload[k] for k in ('selection', 'export', 'wasm', 'architecture', 'train'))
        require(seed in (0, 1), 'unexpected seed')
        require(s['seed'] == seed and s['student']['seed'] == seed and e['seed'] == seed, 'seed mismatch')
        require(s['teacher']['seed'] == 0 and s['size'] == '65', 'wrong teacher seed or capacity')
        require(s['status'] == 'validation_selection_only_no_adjudication', 'wrong selection scope')
        for key, value in COUNTS.items():
            require(arch[key] == value, 'wrong architecture parameter count ' + key)
        require(arch['size'] == '65' and arch['teacher_seed'] == 0, 'wrong architecture capacity/teacher seed')
        require(digest(arch['teacher_sha256'], 'architecture teacher') == TEACHER_SHA, 'wrong cached teacher')
        equal_number(arch['parameter_ratio'], 3940973 / 6047005, 'architecture parameter ratio')
        require(arch['preset'] == {'stem': 16, 'channels': [24, 48, 96, 192], 'hidden': 332}, 'wrong65 preset')
        require(arch['dim'] == 53 and arch['dtype'] == 'float16' and arch['teacher_window_frames'] == 400,
                'teacher cache contract changed')
        require('train_only' in arch['targets'], 'teacher cache not declared train-only')
        require(type(arch['frames']) is int and arch['frames'] > 0 and type(arch['train_clip_count']) is int
                and arch['train_clip_count'] > 0, 'bad registered data/cache counts')
        require(train['seed'] == seed and train['init'] is None and train['max_items'] == train['max_val'] == 0,
                'wrong training seed/init or restricted subset')
        require({key: train[key] for key in ('n_sent', 'n_words', 'n_val_items')} ==
                {'n_sent': 886, 'n_words': 9112, 'n_val_items': 2238}, 'B33 training/validation item counts changed')
        require(type(train['best_epoch']) is int and 0 <= train['best_epoch'] < 40 and
                train['best']['epoch'] == train['best_epoch'] == s['student']['epoch'], 'selected checkpoint epoch mismatch')
        require('seed' not in arch or arch['seed'] == seed, 'architecture student seed mismatch')
        for key, value in THRESHOLDS.items():
            equal_number(s['thresholds'][key], value, 'threshold ' + key)
        equal_number(e['size_ratio_max'], .75, 'export size threshold')
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
        size_ok = size_ratio <= .75
        # Historical lower-threshold size booleans are metadata only; recompute at0.75.

        require(w['execution_provider'] == 'onnxruntime-web WASM CPU', 'wrong runtime provider')
        require(w['ort_version'] == '1.19.2' and w['num_threads'] == 1, 'wrong WASM version or threads')
        require(isinstance(w['node'], str) and w['node'].startswith('v24.'), 'wrong Node version')
        require(all(isinstance(w[k], str) and w[k] for k in ('host', 'cpu', 'protocol')), 'missing runtime environment')
        wasm_environment(w, False)
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
            'legacy_lower_size_ok_ignored': True, 'reported_size_ok': e.get('size_ok'),
            'data_contract': {key: arch[key] for key in ('frames', 'train_clip_count', 'teacher_window_frames', 'dim', 'dtype')},
            'training_counts': {key: train[key] for key in ('n_sent', 'n_words', 'n_val_items')},
            'selected_epoch': train['best_epoch'], 'parameters': COUNTS,
            'status': 'validation_selection_only_no_adjudication', 'no_best_seed_selection': True,
        }
    except KeyError as exc:
        raise ValueError('Missing input field: ' + str(exc)) from exc


def combine(rows):
    require(len(rows) == 2 and [r['seed'] for r in rows] == [0, 1], 'expected ordered seed0 and seed1')
    require(rows[0]['runtime'] == rows[1]['runtime'], 'WASM must use same PC, CPU, versions, threads and input')
    require(rows[0]['validation_speakers'] == rows[1]['validation_speakers'], 'seed validation speakers differ')
    require(rows[0]['data_contract'] == rows[1]['data_contract'] and rows[0]['training_counts'] == rows[1]['training_counts'],
            'seed data/cache contracts differ')
    require(rows[0]['student_checkpoint_sha256'] != rows[1]['student_checkpoint_sha256'], 'both seeds reference identical checkpoint bytes')
    stable = all(r['seed_pass'] for r in rows)
    return {'candidate': 'distill65', 'stable_pass': stable, 'seed_pass': {str(r['seed']): r['seed_pass'] for r in rows},
            'thresholds_each_seed': THRESHOLDS, 'teacher_checkpoint_sha256': TEACHER_SHA,
            'seeds': rows, 'status': 'validation_selection_only_no_adjudication',
            'conclusion': '안정 통과' if stable else '안정 통과 아님',
            'no_best_seed_selection': True, 'independent_adjudication': False,
            'historical_38_results_untouched': True, 'historical_50_results_untouched': True,
            'parameters': COUNTS, 'parameter_percent': 100 * 3940973 / 6047005,
            'n_train_speakers_registered': 33, 'n_validation_speakers': 12}


def card(row):
    return f"""# 65% ROI 증류 학생 seed{row['seed']} 개발 모델 카드

- 용도: 등록된 두 시드 개발 선택. 학습33명·검증12명이며 검증 화자는 이전 선택에도 사용됐다. 독립 판정·제품 성능·앱 반영 없음, 깨끗한 평가 대기.
- 구조: 파라미터3,940,973개(선생의65.1723%),40×40 내부입력, stem16, 잔차24·48·96·192,256특징, BiGRU2층332,53자모 CTC. FP32 ONNX.
- 전단741,920·후단3,199,053개다. 초기 순차 계획은 d7068b06 부록으로 seed0 lab-sub/seed1 lab-main 병렬로 갱신했고 두 시드를 모두 실행했다. 더 좋은 시드를 고르지 않는다. 등록 학습은 AMP0·CPU4·cap0.45·배치32·4000프레임·최대40에폭이다.
- 선생은 B33 seed0 SHA256 `{TEACHER_SHA}`다. 학생 seed{row['seed']} SHA256 `{row['student_checkpoint_sha256']}`. 고정 선생·같은 분할·증류·배치 규칙, 학생 시드만 다르다.
- 검증4지: 선생{row['teacher_accuracy']:.9f}, 학생{row['student_accuracy']:.9f}, 차{row['accuracy_delta']:+.9f}; 기준≥−0.02, 통과={row['gates']['accuracy']}.
- 검증 문장CER(보조): 선생{row['teacher_cer']:.9f}, 학생{row['student_cer']:.9f}. 별도 관문이 아니다.
- FP32 ONNX 크기 비율{row['size_ratio']:.9f}, 기준≤0.75, 통과={row['gates']['fp32_onnx_size']}. 같은PC WASM 시간 비율{row['latency_ratio']:.9f}, 기준≤0.60, 통과={row['gates']['cpu_wasm_latency']}.
- 이 시드의 세 관문 통과={row['seed_pass']}. 최종 안정 통과는 상위 decision.json에서 두 시드가 모두 통과할 때만 인정한다. 좋은 시드 선택·과거38% 결과 수정은 없다.
- 고정 WASM 순서는 C0→C1→D0→D1→C65s0→C65s1이며 동일 PC/CPU/Node/ORT·1스레드와 실제 타임스탬프를 검사했다. 옛60% 파일·50% 시간 보조 boolean은 관문에 쓰지 않고75% 파일·60% 시간을 계산했다.
- PT는 로드하지 않고 파일 SHA만 확인했다. 실제 teacher/student ONNX SHA와 WASM 입력 모델 SHA를 대조했다. 집계기는 추론·학습·새 측정·원자료 접근을 하지 않았다.
- KMSAV·평가19명·clean_eval·E2·OLKAVS는 등록상 사용하지 않았다. 검증12명 개발 선택이라는 한계를 유지하며 모델을 앱에 직접 연결하지 않는다.
"""


def finalize(root, prior_wasm):
    root = Path(root).resolve()
    targets = [root / f'seed{s}' / name for s in (0, 1) for name in ('decision.json', 'MODEL_CARD.md')] + [root / 'decision.json']
    require(not any(p.exists() for p in targets), 'Refuse existing decision or model card; no overwrites')
    require(len(prior_wasm) == 4, '--prior-wasm must give exactly C0 C1 D0 D1 JSON paths')
    wasms = [json.loads(Path(path).read_text(encoding='utf-8-sig')) for path in prior_wasm]
    rows = []
    for seed in (0, 1):
        folder = root / f'seed{seed}'
        paths = {name: folder / (name + '.json') for name in ('selection', 'export', 'wasm', 'architecture')}
        paths['train'] = folder / 'train_summary.json'
        payload = {name: json.loads(path.read_text(encoding='utf-8-sig')) for name, path in paths.items()}
        row = validate_seed(seed, payload, folder)
        for label in ('teacher', 'student'):
            require((folder / (label + '.onnx')).stat().st_size == payload['export'][label]['bytes'], label + '.onnx actual bytes mismatch')
        row['source_json_sha256'] = {name: file_sha(path) for name, path in paths.items()}
        rows.append(row)
        wasms.append(payload['wasm'])
    top = combine(rows)
    top['global_wasm_protocol'] = validate_global_order(wasms)
    top['prior_wasm_sources'] = [{'label': label, 'path': str(Path(path).resolve()), 'sha256': file_sha(path)}
                                 for label, path in zip(GLOBAL_ORDER[:4], prior_wasm)]
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
    """Actual hashes/byte lengths, but exclusively temporary synthetic artifacts."""
    import tempfile
    def write(path, value):
        path.write_text(json.dumps(value), encoding='utf-8')
    def change(path, mutate):
        obj = json.loads(path.read_text(encoding='utf-8'))
        mutate(obj)
        write(path, obj)
    def wasm(paired, minute, model_hashes=None):
        names = ('full', 'compact') if paired else ('teacher', 'student')
        return {'execution_provider': 'onnxruntime-web WASM CPU', 'ort_version': '1.19.2', 'num_threads': 1,
                'node': 'v24.22.1', 'host': 'CNSAi2025', 'cpu': 'SYNTHETIC CPU',
                'protocol': PAIR_PROTOCOL if paired else ROI_PROTOCOL,
                'input_sha256': copy.deepcopy(PAIR_INPUT) if paired else INPUT_SHA,
                'time': '2030-01-01T00:%02d:00Z' % minute,
                'model_sha256': model_hashes or {names[0]: 'a' * 64, names[1]: 'b' * 64},
                'samples_ms': {names[0]: [100.] * 20, names[1]: [55.] * 20},
                names[0] + '_median_ms': 100., names[1] + '_median_ms': 55.,
                'latency_ratio': .55, 'latency_ok': False}
    def fixture(base, name):
        root = base / name
        root.mkdir()
        priors = []
        for i, label in enumerate(GLOBAL_ORDER[:4]):
            path = root / (label + '-wasm.json')
            write(path, wasm(i in (2, 3), i))
            priors.append(path)
        for seed in (0, 1):
            folder = root / ('seed%d' % seed)
            folder.mkdir()
            (folder / 'model.pt').write_bytes(('SYNTHETIC student seed%d' % seed).encode())
            (folder / 'teacher.onnx').write_bytes(b'T' * 400)
            (folder / 'student.onnx').write_bytes(b'S' * 300)
            means = {'teacher': .45, 'student': .44}
            selection = {'seed': seed, 'size': '65', 'status': 'validation_selection_only_no_adjudication',
                         'thresholds': copy.deepcopy(THRESHOLDS), 'accuracy_delta': .44 - .45, 'accuracy_ok': True}
            for label, value in means.items():
                selection[label] = {'mean': value, 'cer': .6, 'seed': seed if label == 'student' else 0,
                                    'epoch': 3, 'checkpoint_sha256': file_sha(folder / 'model.pt') if label == 'student' else TEACHER_SHA,
                                    'by_speaker': {d: {'P%d' % i: value for i in range(12)} for d in ('1', '2')}}
            export = {'seed': seed, 'size_ratio_max': .75, 'size_ratio': .75, 'size_ok': False,
                      **{label: {'bytes': (folder / (label + '.onnx')).stat().st_size,
                                 'sha256': file_sha(folder / (label + '.onnx')), 'wrap_diff': 0., 'onnx_diff': 0.}
                         for label in ('teacher', 'student')}}
            arch = dict(COUNTS, size='65', teacher_seed=0, teacher_sha256=TEACHER_SHA,
                        parameter_ratio=3940973 / 6047005, preset={'stem': 16, 'channels': [24, 48, 96, 192], 'hidden': 332},
                        dim=53, dtype='float16', teacher_window_frames=400, targets='clean_center_crop_teacher; train_only',
                        frames=216388, train_clip_count=1000)
            train = {'seed': seed, 'init': None, 'max_items': 0, 'max_val': 0,
                     'n_sent': 886, 'n_words': 9112, 'n_val_items': 2238,
                     'best_epoch': 3, 'best': {'epoch': 3, 'val_cer': .6, 'val_4way_mean': .44}, 'best_val_4way_mean': .44}
            timing = wasm(False, seed + 4, {label: export[label]['sha256'] for label in ('teacher', 'student')})
            for filename, obj in [('selection.json', selection), ('export.json', export), ('wasm.json', timing),
                                  ('architecture.json', arch), ('train_summary.json', train)]:
                write(folder / filename, obj)
        return root, priors
    results = []
    with tempfile.TemporaryDirectory(prefix='c65-finalizer-synthetic-') as tmp:
        base = Path(tmp)
        root, priors = fixture(base, 'pass')
        good = finalize(root, priors)
        require(good['stable_pass'] and all(r['gates']['fp32_onnx_size'] for r in good['seeds']), '75percent boundary failed')
        require(all(r['reported_size_ok'] is False for r in good['seeds']), 'legacy60percent boolean fixture lost')
        require(all(r['gates']['cpu_wasm_latency'] for r in good['seeds']), 'legacy50percent latency flag used')
        results.append('both_pass_075_inclusive_boundary_old060_size_and050_latency_flags_ignored')
        require(all((root / ('seed%d' % s) / 'MODEL_CARD.md').exists() for s in (0, 1)), 'cards not published')
        try:
            finalize(root, priors)
        except ValueError:
            results.append('exclusive_outputs_refuse_overwrite')
        else:
            raise AssertionError('overwrite accepted')
        root, priors = fixture(base, 'one_fail')
        def fail_accuracy(obj):
            obj['student']['mean'] = .42
            obj['student']['by_speaker'] = {d: {'P%d' % i: .42 for i in range(12)} for d in ('1', '2')}
            obj.update(accuracy_delta=.42 - .45, accuracy_ok=False)
        change(root / 'seed1' / 'selection.json', fail_accuracy)
        require(not finalize(root, priors)['stable_pass'], 'one seed failure masked')
        results.append('one_seed_failure_not_stable')
        mutations = [
            ('wrong_actual_pt_hash', lambda r, p: (r / 'seed0' / 'model.pt').write_bytes(b'TAMPERED')),
            ('wrong_new_input_hash', lambda r, p: change(r / 'seed0' / 'wasm.json', lambda x: x.update(input_sha256='0' * 64))),
            ('wrong_prior_pair_hash', lambda r, p: change(p[2], lambda x: x['input_sha256'].update(lips='0' * 64))),
            ('wrong_order', lambda r, p: change(p[3], lambda x: x.update(time='2030-01-01T00:01:30Z'))),
            ('wrong_prior_cpu', lambda r, p: change(p[0], lambda x: x.update(cpu='OTHER CPU'))),
            ('wrong_threshold', lambda r, p: change(r / 'seed0' / 'export.json', lambda x: x.update(size_ratio_max=.6))),
            ('wrong_parameter_count', lambda r, p: change(r / 'seed0' / 'architecture.json', lambda x: x.update(student_parameters=3030525))),
            ('wrong_seed', lambda r, p: change(r / 'seed0' / 'train_summary.json', lambda x: x.update(seed=1))),
            ('wrong_raw_samples', lambda r, p: change(r / 'seed0' / 'wasm.json', lambda x: x['samples_ms'].update(student=[55.] * 19))),
        ]
        for name, mutate in mutations:
            root, priors = fixture(base, name)
            mutate(root, priors)
            try:
                finalize(root, priors)
            except (ValueError, KeyError):
                require(not (root / 'decision.json').exists(), 'invalid input published a decision')
                results.append(name + '_rejected')
            else:
                raise AssertionError(name + ' accepted')
    return {'synthetic_self_tests_passed': len(results), 'tests': results, 'no_real_results_read_or_written': True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path)
    p.add_argument('--prior-wasm', type=Path, nargs=4, metavar=('C0', 'C1', 'D0', 'D1'))
    p.add_argument('--self-test', action='store_true')
    a = p.parse_args()
    if a.self_test:
        require(a.root is None and a.prior_wasm is None, 'Self-test accepts no actual outcome paths')
        result = self_test()
    else:
        if a.root is None or a.prior_wasm is None:
            p.error('--root and four ordered --prior-wasm C0 C1 D0 D1 paths are required')
        result = finalize(a.root, a.prior_wasm)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
