import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { performance } from 'node:perf_hooks';

// No model/input downloads. Run the installed ORT Web WASM CPU engine in Node.
// Usage: node this.mjs ORT_PACKAGE_DIR teacher.onnx student.onnx output.json
const [ortDir, teacherPath, studentPath, output] = process.argv.slice(2);
if (!output) throw Error('Expected ORT package, teacher, student, output');
if (fs.existsSync(output)) throw Error('Refuse duplicate registered timing');
const ort = await import(pathToFileURL(path.join(ortDir, 'dist', 'ort.node.min.mjs')).href);
ort.env.wasm.numThreads = 1;
ort.env.wasm.proxy = false;
const source = Object.fromEntries([['teacher', teacherPath], ['student', studentPath]].map(([k, p]) => [k, fs.readFileSync(p)]));
const sessions = {};
for (const name of ['teacher', 'student']) sessions[name] = await ort.InferenceSession.create(source[name], { executionProviders: ['wasm'], graphOptimizationLevel: 'all' });
let rng = 20261102;
const data = new Float32Array(75 * 80 * 80);
for (let i = 0; i < data.length; i++) {
  rng ^= rng << 13; rng ^= rng >>> 17; rng ^= rng << 5;
  data[i] = (rng >>> 0) % 256;
}
const feeds = { roi: new ort.Tensor('float32', data, [1, 75, 80, 80]) };
async function run(name) {
  const start = performance.now();
  const outputs = await sessions[name].run(feeds);
  const ms = performance.now() - start;
  if (outputs.logits.dims.join(',') !== '1,75,53' || !outputs.logits.data.every(Number.isFinite)) throw Error('Invalid output');
  for (const t of Object.values(outputs)) t.dispose();
  return ms;
}
for (let i = 0; i < 5; i++) for (const name of ['teacher', 'student']) await run(name);
const samples = { teacher: [], student: [] };
for (let i = 0; i < 20; i++) {
  const order = i % 2 ? ['student', 'teacher'] : ['teacher', 'student'];
  for (const name of order) samples[name].push(await run(name));
}
const median = a => { const b = [...a].sort((x, y) => x - y); return (b[9] + b[10]) / 2; };
const teacher = median(samples.teacher), student = median(samples.student);
const result = {
  protocol: '5 warmups/model; 20 alternating-order pairs; median walltime session.run only; B1 T75 80x80 deterministic uint8-range float32',
  execution_provider: 'onnxruntime-web WASM CPU', ort_version: JSON.parse(fs.readFileSync(path.join(ortDir, 'package.json'))).version,
  num_threads: 1, node: process.version, host: os.hostname(), cpu: os.cpus()[0].model, time: new Date().toISOString(),
  input_sha256: crypto.createHash('sha256').update(Buffer.from(data.buffer)).digest('hex'),
  model_sha256: Object.fromEntries(Object.entries(source).map(([k, b]) => [k, crypto.createHash('sha256').update(b).digest('hex')])),
  samples_ms: samples, teacher_median_ms: teacher, student_median_ms: student,
  latency_ratio: student / teacher, latency_ok: student / teacher <= 0.5,
  status: 'paired_development_runtime_measurement_no_adjudication'
};
fs.writeFileSync(output, JSON.stringify(result, null, 2));
console.log(JSON.stringify(result));
for (const s of Object.values(sessions)) await s.release();
