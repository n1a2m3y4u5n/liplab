import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { performance } from 'node:perf_hooks';

// Two-input, fixed synthetic measurement. No inference occurs in --input-only mode.
let rng = 20261102;
function randomU32() { rng ^= rng << 13; rng ^= rng >>> 17; rng ^= rng << 5; return rng >>> 0; }
const roi = new Float32Array(75 * 80 * 80);
for (let i = 0; i < roi.length; i++) roi[i] = randomU32() % 256;
const lips = new Float32Array(75 * 80);
for (let i = 0; i < lips.length; i++) lips[i] = randomU32() / 4294967296 - .5;
const bytes = a => Buffer.from(a.buffer, a.byteOffset, a.byteLength);
const digest = a => crypto.createHash('sha256').update(a).digest('hex');
const inputHashes = { roi: digest(bytes(roi)), lips: digest(bytes(lips)), combined: digest(Buffer.concat([bytes(roi), bytes(lips)])) };
if (process.argv[2] === '--input-only') {
  console.log(JSON.stringify({ seed: 20261102, input_sha256: inputHashes, roi_shape: [1, 75, 80, 80], lips_shape: [1, 75, 80] }));
  process.exit(0);
}
const [ortDir, fullPath, compactPath, output] = process.argv.slice(2);
if (!output) throw Error('Expected ORT package, full.onnx, compact.onnx, output.json');
if (fs.existsSync(output)) throw Error('Refuse duplicate registered timing');
if (os.hostname().toUpperCase() !== 'CNSAI2025') throw Error('WASM timing must run on lab-sub CNSAi2025');
const version = JSON.parse(fs.readFileSync(path.join(ortDir, 'package.json'))).version;
if (version !== '1.19.2' || !process.version.startsWith('v24.')) throw Error('Require ORTWeb1.19.2 and Node24');
const ort = await import(pathToFileURL(path.join(ortDir, 'dist', 'ort.node.min.mjs')).href);
ort.env.wasm.numThreads = 1;
ort.env.wasm.proxy = false;
const source = { full: fs.readFileSync(fullPath), compact: fs.readFileSync(compactPath) };
const sessions = {};
for (const name of ['full', 'compact']) sessions[name] = await ort.InferenceSession.create(source[name], { executionProviders: ['wasm'], graphOptimizationLevel: 'all' });
const feeds = { roi: new ort.Tensor('float32', roi, [1, 75, 80, 80]), lips: new ort.Tensor('float32', lips, [1, 75, 80]) };
async function run(name) {
  const t0 = performance.now();
  const outputs = await sessions[name].run(feeds);
  const ms = performance.now() - t0;
  if (outputs.logits.dims.join(',') !== '1,75,53' || !outputs.logits.data.every(Number.isFinite)) throw Error('Invalid output');
  for (const tensor of Object.values(outputs)) tensor.dispose();
  return ms;
}
for (let i = 0; i < 5; i++) for (const name of ['full', 'compact']) await run(name);
const samples = { full: [], compact: [] };
for (let i = 0; i < 20; i++) {
  for (const name of i % 2 ? ['compact', 'full'] : ['full', 'compact']) samples[name].push(await run(name));
}
const median = a => { const b = [...a].sort((x, y) => x - y); return (b[9] + b[10]) / 2; };
const full = median(samples.full), compact = median(samples.compact);
const result = {
  status: 'paired_development_runtime_measurement_no_adjudication',
  protocol: '5 warmups/model; 20 alternating-order pairs; median walltime session.run only; roi B1T75x80x80 plus lips B1T75x80; xorshift20261102',
  execution_provider: 'onnxruntime-web WASM CPU', ort_version: version, num_threads: 1,
  node: process.version, host: os.hostname(), cpu: os.cpus()[0].model, time: new Date().toISOString(),
  input_sha256: inputHashes, model_sha256: Object.fromEntries(Object.entries(source).map(([k, v]) => [k, digest(v)])),
  samples_ms: samples, full_median_ms: full, compact_median_ms: compact,
  latency_ratio: compact / full, latency_ok: compact / full <= .5
};
fs.writeFileSync(output, JSON.stringify(result, null, 2));
console.log(JSON.stringify(result));
for (const session of Object.values(sessions)) await session.release();
