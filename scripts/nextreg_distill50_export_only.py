"""Recover an unstarted export after a shell stderr failure; never re-score."""
import argparse
import json
from pathlib import Path
import torch
import nextreg_distill50 as M

p = argparse.ArgumentParser()
for key in ('out', 'teacher', 'student'):
    p.add_argument('--' + key, required=True)
a = p.parse_args()
out = Path(a.out)
s = json.loads((out / 'selection.json').read_text(encoding='utf-8'))
assert s['seed'] == s['student']['seed'] == 1 and s['teacher']['seed'] == 0
assert M.D.sha(a.teacher) == s['teacher']['checkpoint_sha256'] == M.TEACHER_SHA256
assert M.D.sha(a.student) == s['student']['checkpoint_sha256']
assert not any((out / n).exists() for n in ('export.json', 'teacher.onnx', 'student.onnx'))
torch.set_num_threads(4)
torch.set_num_interop_threads(1)
export = {'teacher': M.D.export_one(a.teacher, out / 'teacher.onnx', False),
          'student': M.C.export_capacity(a.student, out / 'student.onnx', M.SIZE)}
export['size_ratio'] = export['student']['bytes'] / export['teacher']['bytes']
export.update(size_ok=export['size_ratio'] <= .6, size_ratio_max=.6, seed=1)
(out / 'export.json').write_text(json.dumps(export, indent=2), encoding='utf-8')
print('EXPORT_ONLY_DONE_NO_RESCORING', export['size_ratio'], flush=True)
