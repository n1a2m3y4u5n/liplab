"""Aggregate frozen D65 seed0/seed1 development artifacts without loading models or inference."""
import argparse
import copy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import nextreg_gpu_fill_wasm_order as ORDER_AUDIT

ARCH = 'fusion_distill65_roi256_lips80_kd_v1'
TEACHER = '42b5fc382377c3a6db4567a989d372b741d8b34504323956bd92bb58ed084c35'
BASELINES = {0: 'd499c9f26affd57ef9cc4014c48337669ecfed7466a1ef8ac81c68742007ca1a',
             1: 'a0d2ff6c17799a0036f20dcf346594de0de794dfc358480d64c211928983c35f'}
THRESHOLDS = {'accuracy_delta_min': .02, 'cer_delta_max': .02, 'size_ratio_max': .75, 'latency_ratio_max': .6}
COUNTS = {'teacher_parameters': 6068989, 'student_parameters': 3962957, 'roi_parameters': 3940973, 'coordinate_parameters': 21984}
ROI_INPUT = '3b2b48ccab377f037ed82015d9cbc84f811392a4c3fa7fa7539a744534c8ccc7'
PAIR_INPUT = {'roi': ROI_INPUT, 'lips': '7c8383e4a505b00880d73e2079d59cb4167efba8aa112109c8affb14b8ce9ad3',
              'combined': '0fe46e1232254fb6193d2fd25d295893394894f2058337f67d018fe771b6c2a8'}
ROI_PROTOCOL = '5 warmups/model; 20 alternating-order pairs; median walltime session.run only; B1 T75 80x80 deterministic uint8-range float32'
PAIR_PROTOCOL = '5 warmups/model; 20 alternating-order pairs; median walltime session.run only; roi B1T75x80x80 plus lips B1T75x80; xorshift20261102'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def finite(v, label, positive=False):
    require(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v), label + ': invalid number')
    require(not positive or v > 0, label + ': must be positive')
    return float(v)


def close(v, expected, label):
    require(math.isclose(finite(v, label), expected, rel_tol=1e-10, abs_tol=1e-10), label + ': inconsistent')


def sha_value(v, label):
    require(isinstance(v, str) and re.fullmatch(r'[0-9a-fA-F]{64}', v) is not None, label + ': invalid SHA256')
    return v.lower()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def wasm_check(w, paired):
    require(w['execution_provider'] == 'onnxruntime-web WASM CPU', 'wrong WASM provider')
    require(w['ort_version'] == '1.19.2' and w['num_threads'] == 1, 'wrong WASM version/threads')
    require(isinstance(w['node'], str) and w['node'].startswith('v24.'), 'wrong Node version')
    require(w['host'].upper() == 'CNSAI2025' and isinstance(w['cpu'], str) and w['cpu'], 'wrong/missing WASM PC')
    require(w['protocol'] == (PAIR_PROTOCOL if paired else ROI_PROTOCOL), 'wrong WASM protocol')
    require(w['input_sha256'] == (PAIR_INPUT if paired else ROI_INPUT), 'wrong fixed WASM input')
    names = ('full', 'compact') if paired else ('teacher', 'student')
    medians = {}
    for name in names:
        sha_value(w['model_sha256'][name], name + ' WASM model')
        values = w['samples_ms'][name]
        require(isinstance(values, list) and len(values) == 20, 'expected 20 WASM samples')
        for v in values:
            finite(v, 'WASM sample', positive=True)
        medians[name] = statistics.median(values)
        close(w[name + '_median_ms'], medians[name], name + ' median')
    ratio = medians[names[1]] / medians[names[0]]
    close(w['latency_ratio'], ratio, 'WASM ratio')
    stamp = datetime.fromisoformat(w['time'].replace('Z', '+00:00'))
    require(stamp.tzinfo is not None and stamp.utcoffset() is not None, 'WASM time must include timezone')
    env = {k: w[k] for k in ('host', 'cpu', 'ort_version', 'node', 'num_threads', 'execution_provider')}
    env['host'] = env['host'].upper()
    return {'ratio': ratio, 'env': env, 'time': stamp, 'time_iso': w['time'], 'paired_input': paired}


def validate_seed(seed, data, file_hash, file_size):
    """file_hash/name and file_size/name are injected only for synthetic tests."""
    s, a, e, w, arch, train = (data[k] for k in ('selection', 'accuracy', 'export', 'wasm', 'architecture', 'train'))
    require(s['seed'] == a['seed'] == arch['seed'] == train['seed'] == seed, 'selected metadata seed mismatch')
    require(s['architecture'] == a['architecture'] == arch['architecture'] == ARCH, 'architecture mismatch')
    require(s['status'] == a['status'] == 'validation_selection_only_no_adjudication', 'wrong selection scope')
    for key, value in COUNTS.items():
        require(s[key] == arch[key] == value, 'wrong architecture count: ' + key)
    close(s['parameter_ratio'], 3962957 / 6068989, 'parameter ratio')
    close(arch['parameter_ratio'], 3962957 / 6068989, 'architecture parameter ratio')
    require(arch['teacher_seed'] == 0 and arch['method'] == 'paired_full_fusion_distillation_T2', 'teacher seed/method changed')
    require(sha_value(s['teacher_sha256'], 'teacher') == sha_value(arch['teacher_sha256'], 'architecture teacher') == TEACHER, 'fixed full-fusion teacher changed')
    require(sha_value(s['baseline_sha256'], 'baseline') == sha_value(a['baseline_model_sha256'], 'accuracy baseline') == BASELINES[seed], 'wrong same-seed B33 baseline')
    require(sha_value(e['full']['checkpoint_sha256'], 'export teacher checkpoint') == TEACHER, 'wrong exported full teacher')
    candidate = sha_value(s['candidate_sha256'], 'candidate')
    require(candidate == sha_value(a['candidate_model_sha256'], 'accuracy candidate') ==
            sha_value(e['compact']['checkpoint_sha256'], 'export candidate checkpoint') ==
            sha_value(file_hash('model.pt'), 'actual model.pt'), 'candidate checkpoint SHA mismatch')
    for key, value in THRESHOLDS.items():
        close(s['thresholds'][key], value, 'threshold ' + key)
    for key in ('accuracy_delta_min', 'cer_delta_max'):
        close(a['thresholds'][key], THRESHOLDS[key], 'accuracy threshold ' + key)
    close(e['size_ratio_max'], .75, 'export threshold')
    for key in ('student_seed', 'teacher_seed'):
        if key in s:
            require(s[key] == (seed if key == 'student_seed' else 0), key + ' mismatch')
    require(train['best_epoch'] == a['candidate']['best_epoch'], 'selected epoch mismatch')
    close(train['best_val_4way_mean'], a['candidate']['best_val_4way_mean'], 'selected accuracy metadata')
    close(train['best']['val_cer'], a['candidate']['best']['val_cer'], 'selected CER metadata')
    require(train['best']['epoch'] == train['best_epoch'], 'train best epoch metadata mismatch')
    for key in ('n_sent', 'n_words', 'n_val_items'):
        require(isinstance(train[key], int) and not isinstance(train[key], bool) and train[key] > 0, 'invalid training metadata count')
    prep = sha_value(a['prep_sha256'], 'accuracy prep')
    require(prep == sha_value(arch['prep_sha256'], 'architecture prep'), 'prep metadata changed')
    for label in ('candidate', 'baseline'):
        mean = finite(a[label]['best_val_4way_mean'], label + ' mean')
        require(0 <= mean <= 1, 'accuracy outside range')
        require(finite(a[label]['best']['val_cer'], label + ' CER') >= 0, 'negative CER')
    delta = a['candidate']['best_val_4way_mean'] - a['baseline']['best_val_4way_mean']
    cer_delta = a['candidate']['best']['val_cer'] - a['baseline']['best']['val_cer']
    for record in (s, a):
        close(record['accuracy_delta'], delta, 'accuracy delta')
        close(record['cer_delta'], cer_delta, 'CER delta')
    for key in ('full', 'compact'):
        model_sha = sha_value(e[key]['sha256'], key + ' ONNX')
        require(model_sha == sha_value(w['model_sha256'][key], key + ' WASM model') ==
                sha_value(file_hash(key + '.onnx'), key + ' actual ONNX'), 'ONNX/WASM SHA mismatch')
        require(isinstance(e[key]['bytes'], int) and not isinstance(e[key]['bytes'], bool) and e[key]['bytes'] > 0, 'bad ONNX bytes')
        require(file_size(key + '.onnx') == e[key]['bytes'], 'actual ONNX byte size mismatch')
        require(e[key]['weights'] == 'FP32' and e[key]['opset'] == 17, 'wrong ONNX format')
        for field in ('wrap_diff', 'onnx_diff'):
            require(0 <= finite(e[key][field], key + ' ' + field) < .001, 'ONNX technical validity failed')
    timing = wasm_check(w, True)
    ratio = e['compact']['bytes'] / e['full']['bytes']
    close(e['size_ratio'], ratio, 'export size ratio')
    close(s['size_ratio'], ratio, 'selection size ratio')
    close(s['latency_ratio'], timing['ratio'], 'selection latency ratio')
    gates = {'accuracy': delta >= .02, 'cer': cer_delta <= .02, 'size': ratio <= .75, 'latency': timing['ratio'] <= .6}
    require(s['gates'] == gates and s['overall_keep_path'] is all(gates.values()), 'final four-gate math inconsistent')
    require(a['keep_path'] is (gates['accuracy'] and gates['cer']) and e['size_ok'] is gates['size'], 'raw gate math inconsistent')
    if 'per_seed_all_four_pass' in s:
        require(s['per_seed_all_four_pass'] is all(gates.values()), 'seed1 aggregate gate inconsistent')
    for filename in ('accuracy-selection.json', 'export.json', 'wasm.json'):
        require(sha_value(s['source_sha256'][filename], filename + ' source') ==
                sha_value(file_hash(filename), filename + ' actual source'), 'selected metadata source hash mismatch')
    return {'seed': seed, 'all_four_pass': all(gates.values()), 'gates': gates, 'accuracy_delta': delta,
            'cer_delta': cer_delta, 'size_ratio': ratio, 'latency_ratio': timing['ratio'],
            'teacher_sha256': TEACHER, 'baseline_sha256': BASELINES[seed], 'candidate_sha256': candidate,
            'architecture': ARCH, **COUNTS, 'parameter_ratio': 3962957 / 6068989,
            'selected_epoch': train['best_epoch'], 'prep_sha256': prep,
            'training_counts': {k: train[k] for k in ('n_sent', 'n_words', 'n_val_items')},
            'source_sha256': {filename: file_hash(filename) for filename in ('selection.json', 'accuracy-selection.json', 'export.json', 'wasm.json', 'architecture.json', 'train_summary.json')},
            'actual_model_sha256_verified': True, 'actual_onnx_sha256_and_bytes_verified': True,
            'historical_seed1_not_registered_flag': s.get('seed1_not_registered'),
            'timing': timing}


def aggregate(rows, prior_wasms, seed_wasms):
    require([row['seed'] for row in rows] == [0, 1], 'expected D65s0 then D65s1')
    require(len(prior_wasms) == 6 and len(seed_wasms) == 2, 'require six prior and two D65 WASM records')
    require(rows[0]['candidate_sha256'] != rows[1]['candidate_sha256'], 'D65s0/D65s1 share identical checkpoint bytes')
    require(rows[0]['prep_sha256'] == rows[1]['prep_sha256'] and rows[0]['training_counts'] == rows[1]['training_counts'], 'D65s0/D65s1 data metadata differs')
    order_audit = ORDER_AUDIT.audit(list(prior_wasms) + list(seed_wasms))
    for row, wasm in zip(rows, seed_wasms):
        require(row['timing']['time_iso'] == wasm['time'], 'selected D65 timing record differs from order audit')
        close(wasm['latency_ratio'], row['latency_ratio'], 'audited D65 latency ratio')
    d0, d1 = (row['all_four_pass'] for row in rows)
    evidence = bool(d0)
    stable = bool(d0 and d1)
    status = 'both_pass_development_stability' if stable else ('not_reproduced' if d0 else 'record_only_D65s0_failed')
    serial_rows = []
    for row in rows:
        row = copy.deepcopy(row)
        row['timing'].pop('time')
        serial_rows.append(row)
    return {'candidate': 'fusion_distill65', 'status': 'validation_selection_only_no_adjudication',
            'stability_status': status, 'stability_evidence_eligible': evidence,
            'both_pass_development_stability': stable, 'seed1_reproduced': bool(d1) if d0 else None,
            'seed1_record_only': not d0, 'no_best_seed_selection': True, 'independent_adjudication': False,
            'thresholds_each_seed': THRESHOLDS, 'seeds': serial_rows,
            'wasm_order': list(ORDER_AUDIT.ORDER),
            'wasm_times': {r['label']: r['time'] for r in order_audit['records']},
            'global_wasm_order_audit': order_audit,
            'same_wasm_environment_verified': True,
            'input_contract': 'C0/C1/C65s0/C65s1 fixed ROI-only input; D0/D1/D65s0/D65s1 fixed paired ROI+lips input; fixed protocols and matching ROI bytes.',
            'historical_seed1_not_registered_flag_superseded': True,
            'explicit_seed1_authorization_in_effect': True,
            'registered_train_speakers': 33, 'validation_speakers': 12,
            'historical_results_untouched': True,
            'interpretation': 'Development validation12 only; clean evaluation pending; D65s1 is stability evidence only if D65s0 passes all four gates; otherwise record only regardless of D65s1 result. No best-seed/app/Android/independent-judgement claim.'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def run(a):
    out = Path(a.out).resolve()
    require(not out.exists(), 'Refuse existing stability output')
    rows, seed_wasms = [], []
    for seed, root in enumerate((a.seed0_root, a.seed1_root)):
        root = Path(root).resolve()
        mapping = {'selection': 'selection.json', 'accuracy': 'accuracy-selection.json', 'export': 'export.json',
                   'wasm': 'wasm.json', 'architecture': 'architecture.json', 'train': 'train_summary.json'}
        payload = {key: read(root / name) for key, name in mapping.items()}
        rows.append(validate_seed(seed, payload, lambda name: sha(root / name), lambda name: (root / name).stat().st_size))
        seed_wasms.append(payload['wasm'])
    result = aggregate(rows, [read(p) for p in a.prior_wasm], seed_wasms)
    result['global_wasm_source_sha256'] = {label: sha(path) for label, path in zip(ORDER_AUDIT.ORDER[:6], a.prior_wasm)}
    result['global_wasm_source_sha256'].update({label: row['source_sha256']['wasm.json'] for label, row in zip(ORDER_AUDIT.ORDER[6:], rows)})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    return result


def self_test():
    def timing(time, paired):
        names = ('full', 'compact') if paired else ('teacher', 'student')
        return {'execution_provider': 'onnxruntime-web WASM CPU', 'ort_version': '1.19.2', 'num_threads': 1,
                'node': 'v24.22.1', 'host': 'CNSAi2025', 'cpu': 'synthetic', 'time': time,
                'protocol': PAIR_PROTOCOL if paired else ROI_PROTOCOL, 'input_sha256': PAIR_INPUT if paired else ROI_INPUT,
                'model_sha256': {names[0]: 'a'*64, names[1]: 'b'*64},
                'samples_ms': {names[0]: [100.]*20, names[1]: [50.]*20},
                names[0]+'_median_ms': 100., names[1]+'_median_ms': 50., 'latency_ratio': .5, 'latency_ok': True}

    def fixture(seed, passed=True):
        delta = .03 if passed else .01
        candidate = str(seed + 1)*64
        gates = {'accuracy': passed, 'cer': True, 'size': True, 'latency': True}
        s = dict(status='validation_selection_only_no_adjudication', architecture=ARCH, seed=seed,
                 thresholds=THRESHOLDS, teacher_sha256=TEACHER, baseline_sha256=BASELINES[seed], candidate_sha256=candidate,
                 accuracy_delta=delta, cer_delta=.01, size_ratio=.5, latency_ratio=.5, gates=gates, overall_keep_path=passed,
                 parameter_ratio=3962957/6068989, source_sha256={k: 'c'*64 for k in ('accuracy-selection.json','export.json','wasm.json')}, **COUNTS)
        cand = dict(best_epoch=3, best_val_4way_mean=.4+delta, best={'epoch': 3, 'val_cer': .61})
        a = dict(status=s['status'], architecture=ARCH, seed=seed, candidate_model_sha256=candidate,
                 baseline_model_sha256=BASELINES[seed], accuracy_delta=delta, cer_delta=.01, keep_path=passed,
                 thresholds={'accuracy_delta_min':.02,'cer_delta_max':.02}, prep_sha256='d'*64,
                 candidate=cand, baseline=dict(best_epoch=3,best_val_4way_mean=.4,best={'val_cer':.6}))
        e = dict(full=dict(checkpoint_sha256=TEACHER,sha256='a'*64,bytes=200,weights='FP32',opset=17,wrap_diff=0,onnx_diff=0),
                 compact=dict(checkpoint_sha256=candidate,sha256='b'*64,bytes=100,weights='FP32',opset=17,wrap_diff=0,onnx_diff=0),
                 size_ratio=.5,size_ratio_max=.75,size_ok=True)
        w = timing(f'2026-11-02T12:0{seed+6}:00Z',True)
        arch = dict(architecture=ARCH,seed=seed,teacher_seed=0,teacher_sha256=TEACHER,prep_sha256='d'*64,
                    method='paired_full_fusion_distillation_T2',parameter_ratio=3962957/6068989,**COUNTS)
        train = dict(seed=seed,**cand,n_sent=886,n_words=9112,n_val_items=2238)
        payload = dict(selection=s,accuracy=a,export=e,wasm=w,architecture=arch,train=train)
        hashes = {'model.pt':candidate,'full.onnx':'a'*64,'compact.onnx':'b'*64}
        return payload, lambda name: hashes.get(name,'c'*64), lambda name:200 if name=='full.onnx' else 100

    def row(seed, passed=True):
        data, h, n = fixture(seed, passed)
        return validate_seed(seed,data,h,n)

    prior = [timing(f'2026-11-02T12:0{i}:00Z', label in ORDER_AUDIT.PAIRED)
             for i, label in enumerate(ORDER_AUDIT.ORDER[:6])]
    def combined(rows):
        payloads = [fixture(seed)[0]['wasm'] for seed in (0, 1)]
        return aggregate(rows, prior, payloads)
    tests=[]
    require(combined([row(0),row(1)])['both_pass_development_stability'],'both pass failed');tests.append('both_pass')
    require(combined([row(0),row(1,False)])['stability_status']=='not_reproduced','D65s1 failure masked');tests.append('D65s0_pass_D65s1_fail')
    for d1pass in (True,False):
        r=combined([row(0,False),row(1,d1pass)])
        require(r['seed1_record_only'] and r['seed1_reproduced'] is None and not r['both_pass_development_stability'],'D65s0 failure improperly selected D65s1')
    tests.append('D65s0_fail_D65s1_record_only_both_branches')
    for name, mutate in [('wrong_teacher',lambda d:d['selection'].update(teacher_sha256='f'*64)),
                         ('wrong_threshold',lambda d:d['selection'].update(thresholds={**THRESHOLDS,'accuracy_delta_min':.01})),
                         ('wrong_size_threshold',lambda d:d['selection'].update(thresholds={**THRESHOLDS,'size_ratio_max':.6})),
                         ('wrong_seed',lambda d:d['architecture'].update(seed=1))]:
        data,h,n=fixture(0);mutate(data)
        try: validate_seed(0,data,h,n)
        except ValueError: tests.append(name+'_rejected')
        else: raise AssertionError(name)
    payload,h,n=fixture(0)
    payload['selection']['seed1_not_registered'] = True
    require(combined([validate_seed(0,payload,h,n),row(1)])['both_pass_development_stability'], 'historical registration flag incorrectly blocks explicit authorization')
    tests.append('historical_seed1_not_registered_flag_superseded')
    payload,h,n=fixture(0)
    try: validate_seed(0,payload,lambda name: 'f'*64,n)
    except ValueError: tests.append('actual_candidate_hash_mismatch_rejected')
    else: raise AssertionError('wrong hash accepted')
    bad_prior=copy.deepcopy(prior);bad_prior[5]['time']='2026-11-02T12:08:00Z'
    try: aggregate([row(0),row(1)],bad_prior,[fixture(seed)[0]['wasm'] for seed in (0,1)])
    except ValueError: tests.append('wrong_order_rejected')
    else: raise AssertionError('wrong order accepted')
    return {'synthetic_self_tests_passed':len(tests),'tests':tests,'no_actual_results_read_or_written':True}


def main():
    p=argparse.ArgumentParser()
    for key in ('seed0-root','seed1-root','out'):
        p.add_argument('--'+key)
    p.add_argument('--prior-wasm',nargs=6,metavar='JSON')
    p.add_argument('--self-test',action='store_true')
    a=p.parse_args()
    if a.self_test:
        result=self_test()
    else:
        require(all(getattr(a,key) for key in ('seed0_root','seed1_root','out','prior_wasm')),'Two seed roots, output and six ordered prior WASM JSON paths required')
        result=run(a)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
