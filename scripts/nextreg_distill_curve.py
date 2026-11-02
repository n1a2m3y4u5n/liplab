"""Read-only fixed capacity aggregation. No model inference or metric remeasurement."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import tempfile
from datetime import datetime

TEACHER_SHA = 'd499c9f26affd57ef9cc4014c48337669ecfed7466a1ef8ac81c68742007ca1a'
INPUT_SHA = '3b2b48ccab377f037ed82015d9cbc84f811392a4c3fa7fa7539a744534c8ccc7'
TEACHER_PARAMETERS = 6047005
PARAMETERS = {'12': 743757, '25': 1498889, '38': 2319893}
FROZEN_TEACHER_ACCURACY = .442025181747035
FROZEN_STUDENT_ACCURACY = .407993672818202
FROZEN_DELTA = -.034031508928833
PROTOCOL = ('5 warmups/model; 20 alternating-order pairs; median walltime session.run only; '
            'B1 T75 80x80 deterministic uint8-range float32')
STATUS = 'validation_selection_only_no_adjudication'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, name):
    require(type(value) in (int, float) and math.isfinite(value), name + ': finite number required')
    return float(value)


def close(actual, expected, name, tolerance=1e-12):
    require(math.isclose(number(actual, name), expected, rel_tol=tolerance, abs_tol=tolerance),
            name + ': inconsistent recorded value')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def check_mean(row, label):
    by = row['by_speaker']
    require(set(by) == {'1', '2'}, label + ': dup1/2 required')
    require(len(by['1']) == 12 and set(by['1']) == set(by['2']), label + ': same twelve speakers required')
    means = []
    for dup in ('1', '2'):
        values = [number(v, label + ' by-speaker accuracy') for v in by[dup].values()]
        require(all(0 <= v <= 1 for v in values), label + ': accuracy outside [0,1]')
        means.append(statistics.fmean(values))
    mean = statistics.fmean(means)
    close(row['mean'], mean, label + ' accuracy mean')
    require(number(row['cer'], label + ' CER') >= 0, label + ': negative CER')
    return mean, set(by['1'])


def read_point(root, label, *, teacher_sha=TEACHER_SHA, input_sha=INPUT_SHA,
               teacher_bytes=24198013, frozen_student_bytes=2986240):
    root = Path(root).resolve()
    files = {name: root / (name + '.json') for name in ('selection', 'export', 'wasm', 'architecture')}
    selection, export, wasm, architecture = (read_json(files[k]) for k in files)
    require(selection['status'] == STATUS, label + ': development selection status required')
    require(selection['teacher']['checkpoint_sha256'] == teacher_sha, label + ': fixed teacher checkpoint changed')
    require(architecture['teacher_sha256'] == teacher_sha and architecture['teacher_seed'] == 0,
            label + ': fixed cache teacher changed')
    require(architecture['teacher_parameters'] == TEACHER_PARAMETERS, label + ': teacher parameter count changed')
    require(architecture['student_parameters'] == PARAMETERS[label], label + ': student parameter count changed')
    close(architecture['parameter_ratio'], PARAMETERS[label] / TEACHER_PARAMETERS, label + ' parameter ratio')
    if label != '12':
        require(str(architecture['size']) == label and str(selection['size']) == label, label + ': capacity label mismatch')
    model_sha = sha(root / 'model.pt')
    require(model_sha == selection['student']['checkpoint_sha256'], label + ': student checkpoint hash mismatch')
    teacher_checkpoint = root / 'teacher.pt'
    if teacher_checkpoint.exists():
        require(sha(teacher_checkpoint) == teacher_sha, label + ': actual teacher checkpoint hash mismatch')
    teacher_acc, speakers = check_mean(selection['teacher'], label + ' teacher')
    student_acc, student_speakers = check_mean(selection['student'], label + ' student')
    require(speakers == student_speakers, label + ': teacher/student speakers differ')
    delta = student_acc - teacher_acc
    close(selection['accuracy_delta'], delta, label + ' accuracy delta')
    accuracy_ok = delta >= -.02
    require(type(selection['accuracy_ok']) is bool and selection['accuracy_ok'] == accuracy_ok,
            label + ': recorded accuracy gate inconsistent')
    sizes, onnx_hashes = {}, {}
    for name in ('teacher', 'student'):
        path = root / (name + '.onnx')
        sizes[name], onnx_hashes[name] = path.stat().st_size, sha(path)
        require(export[name]['bytes'] == sizes[name], label + ': ONNX byte count mismatch')
        require(export[name]['sha256'] == onnx_hashes[name], label + ': export ONNX hash mismatch')
        require(wasm['model_sha256'][name] == onnx_hashes[name], label + ': timing ONNX hash mismatch')
        for key in ('wrap_diff', 'onnx_diff'):
            diff = number(export[name][key], label + ' ' + name + ' ' + key)
            require(0 <= diff < 1e-3, label + ': export technical difference must be <1e-3')
    if label == '12':
        require(sizes['teacher'] == teacher_bytes, label + ': frozen FP32 teacher ONNX size changed')
    size_ratio = sizes['student'] / sizes['teacher']
    close(export['size_ratio'], size_ratio, label + ' file ratio')
    size_ok = size_ratio <= .4
    require(type(export['size_ok']) is bool and export['size_ok'] == size_ok, label + ': recorded size gate inconsistent')
    require(wasm['input_sha256'] == input_sha, label + ': fixed synthetic input hash changed')
    require(wasm['host'].upper() == 'CNSAI2025', label + ': timing must use lab-sub CNSAi2025')
    require(wasm['ort_version'] == '1.19.2', label + ': ORT version changed')
    require(type(wasm['num_threads']) is int and wasm['num_threads'] == 1, label + ': one WASM thread required')
    require(wasm['execution_provider'] == 'onnxruntime-web WASM CPU', label + ': WASM CPU execution provider required')
    require(wasm['protocol'] == PROTOCOL, label + ': timing protocol changed')
    require(wasm['node'].startswith('v24.'), label + ': Node24 required')
    require(isinstance(wasm['cpu'], str) and bool(wasm['cpu'].strip()), label + ': CPU identity missing')
    timestamp = datetime.fromisoformat(wasm['time'].replace('Z', '+00:00'))
    require(timestamp.tzinfo is not None, label + ': timing timestamp must include timezone')
    medians = {}
    for name in ('teacher', 'student'):
        samples = wasm['samples_ms'][name]
        require(len(samples) == 20, label + ': exactly20 raw timings per model required')
        values = [number(v, label + ' raw timing') for v in samples]
        require(all(v > 0 for v in values), label + ': timing must be positive')
        medians[name] = statistics.median(values)
        close(wasm[name + '_median_ms'], medians[name], label + ' ' + name + ' median', tolerance=1e-9)
    latency_ratio = medians['student'] / medians['teacher']
    close(wasm['latency_ratio'], latency_ratio, label + ' latency ratio')
    latency_ok = latency_ratio <= .5
    require(type(wasm['latency_ok']) is bool and wasm['latency_ok'] == latency_ok,
            label + ': recorded latency gate inconsistent')
    all_three = accuracy_ok and size_ok and latency_ok
    if label == '12':
        close(teacher_acc, FROZEN_TEACHER_ACCURACY, 'frozen12 teacher accuracy')
        close(student_acc, FROZEN_STUDENT_ACCURACY, 'frozen12 student accuracy')
        close(delta, FROZEN_DELTA, 'frozen12 accuracy delta')
        require(sizes['student'] == frozen_student_bytes, 'frozen12 FP32 size changed')
        close(latency_ratio, .064387, 'frozen12 published timing ratio', tolerance=5e-7)
        require(not accuracy_ok and not all_three, 'frozen12 cannot become eligible')
    return {'label': label, 'source_root': str(root), 'student_parameters': PARAMETERS[label],
            'teacher_parameters': TEACHER_PARAMETERS, 'capacity_percent': 100 * PARAMETERS[label] / TEACHER_PARAMETERS,
            'teacher_accuracy': teacher_acc, 'student_accuracy': student_acc,
            'accuracy_delta': delta, 'accuracy_delta_pp': delta * 100,
            'teacher_cer': selection['teacher']['cer'], 'student_cer': selection['student']['cer'],
            'teacher_onnx_bytes': sizes['teacher'], 'student_onnx_bytes': sizes['student'], 'size_ratio': size_ratio,
            'teacher_median_ms': medians['teacher'], 'student_median_ms': medians['student'], 'latency_ratio': latency_ratio,
            'accuracy_ok': accuracy_ok, 'size_ok': size_ok, 'latency_ok': latency_ok, 'all_three_pass': all_three,
            'frozen': label == '12', 'eligible': label != '12' and all_three, 'selected': False,
            'teacher_checkpoint_sha256': teacher_sha,
            'teacher_checkpoint_verification': 'actual_file_and_two_provenance_records' if teacher_checkpoint.exists() else 'two_provenance_records_no_teacher_pt_supplied',
            'student_checkpoint_sha256': model_sha, 'onnx_sha256': onnx_hashes,
            'source_json_sha256': {k: sha(v) for k, v in files.items()}, 'input_sha256': input_sha,
            'runtime': {k: wasm[k] for k in ('host', 'cpu', 'node', 'ort_version', 'num_threads', 'execution_provider', 'protocol', 'time')},
            'samples_ms': wasm['samples_ms'], 'validation_speakers': sorted(speakers)}


CSV_FIELDS = ('label student_parameters teacher_parameters capacity_percent teacher_accuracy student_accuracy '
              'accuracy_delta accuracy_delta_pp teacher_cer student_cer teacher_onnx_bytes student_onnx_bytes '
              'size_ratio teacher_median_ms student_median_ms latency_ratio accuracy_ok size_ok latency_ok '
              'all_three_pass frozen eligible selected').split()


def aggregate(small, quarter, medium, out, *, expected=None, synthetic=False):
    out = Path(out).resolve()
    names = ['capacity-curve.' + suffix for suffix in ('json', 'csv', 'png')]
    require(not any((out / name).exists() for name in names), 'Refuse overwrite of final capacity decision or artifacts')
    expected = expected or {}
    points = [read_point(path, label, **expected) for path, label in ((small, '12'), (quarter, '25'), (medium, '38'))]
    require(len({p['runtime']['cpu'] for p in points}) == 1, 'All timings must use the same CPU identity')
    require(len({tuple(p['validation_speakers']) for p in points}) == 1, 'All points must share twelve validation speakers')
    t25, t38 = (datetime.fromisoformat(p['runtime']['time'].replace('Z', '+00:00')) for p in points[1:])
    require(t25 < t38, 'Registered WASM order25 then38 violated')
    candidates = [p for p in points if p['eligible']]
    chosen = min(candidates, key=lambda p: p['student_parameters']) if candidates else None
    if chosen:
        chosen['selected'] = True
    result = {'status': STATUS, 'synthetic_fixture': synthetic,
              'interpretation': 'Validation n=12 development selection only; no independent judgement; clean evaluation pending; no app or Android claim.',
              'selection_rule': 'Minimum student parameter count among the fixed new25/38 candidates satisfying all three gates; frozen12 remains NO-GO.',
              'gates': {'accuracy_delta_min': -.02, 'onnx_size_ratio_max': .4, 'wasm_median_ratio_max': .5},
              'selected_student': chosen['label'] if chosen else None,
              'selected_student_parameters': chosen['student_parameters'] if chosen else None,
              'overall_keep_path': chosen is not None, 'frozen12_status': 'NO-GO_UNCHANGED', 'points': points,
              'source_script_sha256': sha(__file__),
              'plot_script_sha256': sha(Path(__file__).with_name('nextreg_distill_curve_plot.ps1'))}
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='capacity-render-', dir=out) as tmp:
        tmp = Path(tmp)
        with (tmp / names[1]).open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for p in points:
                writer.writerow({k: str(p[k]).lower() if type(p[k]) is bool else p[k] for k in CSV_FIELDS})
        cmd = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
               str(Path(__file__).with_name('nextreg_distill_curve_plot.ps1')),
               '-InputCsv', str(tmp / names[1]), '-OutputPng', str(tmp / names[2])]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise ValueError('Headless .NET plot failed: ' + (exc.stderr or exc.stdout)[-2000:]) from exc
        png = (tmp / names[2]).read_bytes()
        require(png[:8] == b'\x89PNG\r\n\x1a\n' and int.from_bytes(png[16:20], 'big') == 1200
                and int.from_bytes(png[20:24], 'big') == 700, 'Plot must be a1200x700 PNG')
        result['artifacts'] = {name: {'sha256': sha(tmp / name), 'bytes': (tmp / name).stat().st_size} for name in names[1:]}
        (tmp / names[0]).write_text(json.dumps(result, indent=2), encoding='utf-8')
        for name in names[1:] + names[:1]:
            require(not (out / name).exists(), 'Refuse overwrite during final publication')
            (tmp / name).rename(out / name)
    return result


def self_test():
    """Synthetic files only; fixed CLI hashes cannot be overridden in normal operation."""
    def write(path, obj):
        path.write_text(json.dumps(obj), encoding='utf-8')

    with tempfile.TemporaryDirectory(prefix='nextreg-capacity-synthetic-') as tmp:
        tmp = Path(tmp)
        teacher_sha = hashlib.sha256(b'SYNTHETIC teacher checkpoint').hexdigest()
        expected = {'teacher_sha': teacher_sha, 'teacher_bytes': 1000, 'frozen_student_bytes': 123}
        roots = {label: tmp / label for label in PARAMETERS}
        for i, (label, root) in enumerate(roots.items()):
            root.mkdir()
            (root / 'model.pt').write_bytes(('SYNTHETIC student' + label).encode())
            (root / 'teacher.pt').write_bytes(b'SYNTHETIC teacher checkpoint')
            (root / 'teacher.onnx').write_bytes(b'T' * 1000)
            (root / 'student.onnx').write_bytes(b'S' * {'12': 123, '25': 250, '38': 380}[label])
            teacher_acc = FROZEN_TEACHER_ACCURACY
            student_acc = FROZEN_STUDENT_ACCURACY if label == '12' else teacher_acc + {'25': -.01, '38': .01}[label]
            by = lambda value: {str(d): {'S%02d' % n: value for n in range(12)} for d in (1, 2)}
            selection = {'status': STATUS, 'size': label,
                         'teacher': {'mean': teacher_acc, 'cer': .5, 'by_speaker': by(teacher_acc), 'checkpoint_sha256': teacher_sha},
                         'student': {'mean': student_acc, 'cer': .5, 'by_speaker': by(student_acc), 'checkpoint_sha256': sha(root / 'model.pt')},
                         'accuracy_delta': student_acc - teacher_acc, 'accuracy_ok': student_acc - teacher_acc >= -.02}
            export = {name: {'bytes': (root / (name + '.onnx')).stat().st_size, 'sha256': sha(root / (name + '.onnx')),
                             'wrap_diff': 1e-5, 'onnx_diff': 1e-5} for name in ('teacher', 'student')}
            export['size_ratio'] = export['student']['bytes'] / export['teacher']['bytes']
            export['size_ok'] = export['size_ratio'] <= .4
            ratio = {'12': .064387, '25': .3, '38': .4}[label]
            wasm = {'protocol': PROTOCOL, 'execution_provider': 'onnxruntime-web WASM CPU', 'ort_version': '1.19.2',
                    'num_threads': 1, 'node': 'v24.0.0', 'host': 'CNSAi2025', 'cpu': 'SYNTHETIC CPU',
                    'time': '2030-01-01T00:0%d:00Z' % i, 'input_sha256': INPUT_SHA,
                    'model_sha256': {name: export[name]['sha256'] for name in ('teacher', 'student')},
                    'samples_ms': {'teacher': [100.] * 20, 'student': [100 * ratio] * 20},
                    'teacher_median_ms': 100., 'student_median_ms': 100 * ratio, 'latency_ratio': ratio, 'latency_ok': ratio <= .5}
            architecture = {'teacher_parameters': TEACHER_PARAMETERS, 'student_parameters': PARAMETERS[label],
                            'parameter_ratio': PARAMETERS[label] / TEACHER_PARAMETERS, 'teacher_sha256': teacher_sha, 'teacher_seed': 0, 'size': label}
            for name, obj in [('selection', selection), ('export', export), ('wasm', wasm), ('architecture', architecture)]:
                write(root / (name + '.json'), obj)
        original_selection = {label: read_json(root / 'selection.json') for label, root in roots.items()}
        def run(name):
            return aggregate(roots['12'], roots['25'], roots['38'], tmp / name, expected=expected, synthetic=True)
        require(run('both_pass')['selected_student'] == '25', 'Synthetic minimum-capacity choice failed')
        rejected = 0
        try:
            run('both_pass')
        except ValueError:
            rejected += 1
        for label, delta in [('25', -.03), ('38', -.04)]:
            p = roots[label] / 'selection.json'
            obj = read_json(p)
            value = obj['teacher']['mean'] + delta
            obj['student']['mean'] = value
            obj['student']['by_speaker'] = {str(d): {'S%02d' % n: value for n in range(12)} for d in (1, 2)}
            obj['accuracy_delta'], obj['accuracy_ok'] = delta, False
            write(p, obj)
            result = run('fail_' + label)
            require(result['selected_student'] == ('38' if label == '25' else None), 'Synthetic failure branch incorrect')
        write(roots['25'] / 'selection.json', original_selection['25'])
        require(run('only25')['selected_student'] == '25', 'Synthetic only25 branch incorrect')
        write(roots['38'] / 'selection.json', original_selection['38'])
        export_path, wasm_path = roots['25'] / 'export.json', roots['25'] / 'wasm.json'
        original_export, original_wasm = read_json(export_path), read_json(wasm_path)
        (roots['25'] / 'student.onnx').write_bytes(b'S' * 450)
        large_export = read_json(export_path)
        large_export['student']['bytes'] = 450
        large_export['student']['sha256'] = sha(roots['25'] / 'student.onnx')
        large_export['size_ratio'], large_export['size_ok'] = .45, False
        large_wasm = read_json(wasm_path)
        large_wasm['model_sha256']['student'] = large_export['student']['sha256']
        write(export_path, large_export)
        write(wasm_path, large_wasm)
        require(run('size_gate')['selected_student'] == '38', 'Synthetic size gate ignored')
        (roots['25'] / 'student.onnx').write_bytes(b'S' * 250)
        write(export_path, original_export)
        slow = json.loads(json.dumps(original_wasm))
        slow['samples_ms']['student'] = [60.] * 20
        slow['student_median_ms'], slow['latency_ratio'], slow['latency_ok'] = 60., .6, False
        write(wasm_path, slow)
        require(run('latency_gate')['selected_student'] == '38', 'Synthetic latency gate ignored')
        write(wasm_path, original_wasm)
        wasm_path = roots['25'] / 'wasm.json'
        original = read_json(wasm_path)
        for key, value in [('input_sha256', '0' * 64), ('num_threads', 2), ('host', 'OTHER'), ('student_median_ms', 999.)]:
            obj = dict(original)
            obj[key] = value
            write(wasm_path, obj)
            try:
                run('bad_' + key)
            except ValueError:
                rejected += 1
            else:
                raise AssertionError('Accepted tampered synthetic ' + key)
        write(wasm_path, original)
        for filename, modify in [
            ('architecture.json', lambda obj: obj.update(teacher_sha256='0' * 64)),
            ('selection.json', lambda obj: obj['student'].update(checkpoint_sha256='0' * 64)),
            ('export.json', lambda obj: obj['student'].update(onnx_diff=1e-3)),
            ('wasm.json', lambda obj: obj['samples_ms'].update(student=[30.] * 19)),
        ]:
            path = roots['25'] / filename
            valid = read_json(path)
            changed = json.loads(json.dumps(valid))
            modify(changed)
            write(path, changed)
            try:
                run('bad_file_' + filename)
            except ValueError:
                rejected += 1
            else:
                raise AssertionError('Accepted tampered synthetic ' + filename)
            write(path, valid)
        require(rejected == 9, 'Synthetic rejection checks failed')
        print('CAPACITY_CURVE_SYNTHETIC_OK all_choice_branches accuracy_size_latency_gates overwrite_and8_provenance_rejections PNG1200x700')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--small', type=Path)
    p.add_argument('--quarter', type=Path)
    p.add_argument('--medium', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--self-test', action='store_true', help='Use only temporary synthetic artifacts; no real outcome access')
    a = p.parse_args()
    if a.self_test:
        require(not any((a.small, a.quarter, a.medium, a.out)), 'Self-test does not accept outcome paths')
        return self_test()
    require(all((a.small, a.quarter, a.medium, a.out)), '--small --quarter --medium --out are required')
    result = aggregate(a.small, a.quarter, a.medium, a.out)
    print('CAPACITY_CURVE_FINAL', json.dumps({k: result[k] for k in ('selected_student', 'overall_keep_path', 'frozen12_status')}))


if __name__ == '__main__':
    main()
