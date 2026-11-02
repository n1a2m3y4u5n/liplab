"""Audit the eight registered WASM JSON measurements; never open a model or run it."""
import argparse
import copy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

ORDER = ('C0', 'C1', 'D0', 'D1', 'C65s0', 'C65s1', 'D65s0', 'D65s1')
PAIRED = {'D0', 'D1', 'D65s0', 'D65s1'}
ROI_SHA = '3b2b48ccab377f037ed82015d9cbc84f811392a4c3fa7fa7539a744534c8ccc7'
PAIR_SHA = {'roi': ROI_SHA, 'lips': '7c8383e4a505b00880d73e2079d59cb4167efba8aa112109c8affb14b8ce9ad3',
            'combined': '0fe46e1232254fb6193d2fd25d295893394894f2058337f67d018fe771b6c2a8'}
ROI_PROTOCOL = '5 warmups/model; 20 alternating-order pairs; median walltime session.run only; B1 T75 80x80 deterministic uint8-range float32'
PAIR_PROTOCOL = '5 warmups/model; 20 alternating-order pairs; median walltime session.run only; roi B1T75x80x80 plus lips B1T75x80; xorshift20261102'
ISO = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def numeric(v, name):
    require(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v), name + ': invalid numeric value')
    return float(v)


def close(v, expected, name):
    require(math.isclose(numeric(v, name), expected, rel_tol=1e-10, abs_tol=1e-10), name + ': inconsistent raw value')


def sha_value(v, name):
    require(isinstance(v, str) and re.fullmatch(r'[0-9a-fA-F]{64}', v) is not None, name + ': invalid model SHA256')
    return v.lower()


def record(label, w):
    try:
        paired = label in PAIRED
        expected_protocol = PAIR_PROTOCOL if paired else ROI_PROTOCOL
        expected_input = PAIR_SHA if paired else ROI_SHA
        names = ('full', 'compact') if paired else ('teacher', 'student')
        require(w['execution_provider'] == 'onnxruntime-web WASM CPU', 'wrong WASM execution provider')
        require(w['ort_version'] == '1.19.2', 'wrong ORT version')
        require(type(w['num_threads']) is int and w['num_threads'] == 1, 'wrong WASM thread count')
        require(isinstance(w['node'], str) and re.fullmatch(r'v24\.\d+\.\d+', w['node']) is not None, 'wrong Node version')
        require(isinstance(w['host'], str) and w['host'].upper() == 'CNSAI2025', 'wrong registered measurement host')
        require(isinstance(w['cpu'], str) and bool(w['cpu'].strip()), 'missing CPU')
        require(w['protocol'] == expected_protocol, 'wrong label-specific WASM protocol')
        require(w['input_sha256'] == expected_input, 'wrong label-specific fixed input')
        require(isinstance(w['model_sha256'], dict) and set(w['model_sha256']) == set(names), 'wrong model pair names')
        require(isinstance(w['samples_ms'], dict) and set(w['samples_ms']) == set(names), 'wrong sample pair names')
        shas, medians = {}, {}
        for name in names:
            shas[name] = sha_value(w['model_sha256'][name], name)
            samples = w['samples_ms'][name]
            require(isinstance(samples, list) and len(samples) == 20, 'expected 20 raw timing samples/model')
            for v in samples:
                require(numeric(v, name + ' sample') > 0, 'nonpositive timing sample')
            medians[name] = statistics.median(samples)
            close(w[name + '_median_ms'], medians[name], name + ' median')
        ratio = medians[names[1]] / medians[names[0]]
        close(w['latency_ratio'], ratio, 'latency ratio')
        require(isinstance(w['time'], str) and ISO.fullmatch(w['time']) is not None, 'time must be timezone-aware calendar ISO timestamp')
        stamp = datetime.fromisoformat(w['time'].replace('Z', '+00:00'))
        require(stamp.tzinfo is not None and stamp.utcoffset() is not None, 'missing timestamp timezone')
        env = {k: w[k] for k in ('host', 'cpu', 'node', 'ort_version', 'num_threads', 'execution_provider')}
        return {'label': label, 'time': w['time'], '_stamp': stamp, 'environment': env,
                'input_contract': 'paired_roi_lips' if paired else 'roi_only',
                'input_sha256': copy.deepcopy(expected_input), 'protocol': expected_protocol,
                'model_sha256': shas, 'raw_samples_per_model': 20,
                'verified_medians_ms': medians, 'verified_latency_ratio': ratio,
                'legacy_latency_boolean_ignored': True}
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError(label + ': ' + str(exc)) from exc


def audit(payloads):
    require(len(payloads) == len(ORDER), 'Exactly eight ordered JSON records required')
    rows = [record(label, payload) for label, payload in zip(ORDER, payloads)]
    require(all(row['environment'] == rows[0]['environment'] for row in rows), 'WASM host/CPU/exact Node/ORT/threads/provider differ')
    require(all(rows[i]['_stamp'] < rows[i + 1]['_stamp'] for i in range(len(rows) - 1)),
            'WASM timestamps must be strictly ordered C0<C1<D0<D1<C65s0<C65s1<D65s0<D65s1')
    for row in rows:
        row.pop('_stamp')
    return {'status': 'registered_wasm_order_verified_only', 'order_verified': True,
            'registered_order': list(ORDER), 'environment': rows[0]['environment'], 'records': rows,
            'same_environment_verified': True, 'label_specific_inputs_and_protocols_verified': True,
            'label_assignment': 'Ordered CLI paths; no model or training metadata is loaded by this audit.',
            'model_files_opened': False, 'inference_or_benchmark_performed': False,
            'scientific_gate_decisions_made': False, 'historical_results_modified': False}


def run(paths, output):
    require(len(paths) == len(ORDER), 'Exactly eight ordered JSON paths required')
    output = Path(output).resolve()
    require(not output.exists(), 'Refuse existing audit output')
    payloads, sources = [], []
    for label, raw_path in zip(ORDER, paths):
        path = Path(raw_path).resolve()
        raw = path.read_bytes()
        payloads.append(json.loads(raw.decode('utf-8-sig')))
        sources.append({'label': label, 'source_path': str(path), 'source_file_sha256': hashlib.sha256(raw).hexdigest()})
    result = audit(payloads)
    for row, source in zip(result['records'], sources):
        row.update(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    return result


def self_test():
    fixtures = []
    for i, label in enumerate(ORDER):
        paired = label in PAIRED
        names = ('full', 'compact') if paired else ('teacher', 'student')
        fixtures.append({'execution_provider': 'onnxruntime-web WASM CPU', 'ort_version': '1.19.2', 'num_threads': 1,
                         'node': 'v24.22.1', 'host': 'CNSAi2025', 'cpu': 'synthetic CPU',
                         'protocol': PAIR_PROTOCOL if paired else ROI_PROTOCOL,
                         'input_sha256': copy.deepcopy(PAIR_SHA if paired else ROI_SHA),
                         'model_sha256': {names[0]: 'a'*64, names[1]: 'b'*64},
                         'samples_ms': {names[0]: [100.]*20, names[1]: [55.]*20},
                         names[0]+'_median_ms': 100., names[1]+'_median_ms': 55.,
                         'latency_ratio': .55, 'latency_ok': False,
                         'time': f'2026-11-02T12:0{i}:00.000Z'})
    require(audit(fixtures)['order_verified'], 'valid eight-record audit failed')
    tests = ['valid_eight_records_legacy_boolean_ignored']

    def rejected(name, mutate):
        data = copy.deepcopy(fixtures)
        mutate(data)
        try:
            audit(data)
        except ValueError:
            tests.append(name)
        else:
            raise AssertionError(name + ' was accepted')

    rejected('wrong_time_order_rejected', lambda d: d[5].update(time='2026-11-02T12:03:00Z'))
    rejected('wrong_input_rejected', lambda d: d[6]['input_sha256'].update(lips='c'*64))
    rejected('D65s1_roi_only_contract_rejected', lambda d: d[7].update(input_sha256=ROI_SHA, protocol=ROI_PROTOCOL))
    rejected('different_cpu_rejected', lambda d: d[4].update(cpu='other CPU'))
    rejected('wrong_threads_rejected', lambda d: d[3].update(num_threads=2))
    rejected('malformed_raw_samples_rejected', lambda d: d[0]['samples_ms']['student'].pop())
    rejected('malformed_model_sha_rejected', lambda d: d[2]['model_sha256'].update(compact='not-a-hash'))
    rejected('timezone_missing_rejected', lambda d: d[1].update(time='2026-11-02T12:01:00'))
    rejected('nonfinite_sample_rejected', lambda d: d[5]['samples_ms']['student'].__setitem__(0, float('nan')))
    return {'synthetic_self_tests_passed': len(tests), 'tests': tests, 'no_actual_results_read_or_written': True}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--wasm', nargs=8, metavar='JSON')
    p.add_argument('--out')
    p.add_argument('--self-test', action='store_true')
    a = p.parse_args()
    if a.self_test:
        result = self_test()
    else:
        require(a.wasm is not None and a.out is not None, '--wasm with eight paths and --out are required')
        result = run(a.wasm, a.out)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
