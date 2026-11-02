import { readFileSync } from 'node:fs'
import { landmarkLips80, coordinateSequence, fusionModelInput, round4 } from '../frontend/src/lib/lipFusion.js'
const input = JSON.parse(readFileSync(0, 'utf8'))
const results = input.cases.map(({ landmarks, W, H }) => landmarkLips80(landmarks, W, H))
const seq = coordinateSequence(input.frames)
const roi = seq.lips.map(() => new Uint8Array(88 * 88))
const pack = fusionModelInput(roi, seq)
process.stdout.write(JSON.stringify({ results, lips: seq.lips.map((x) => Array.from(x)), det: seq.det,
  packed: Array.from(pack.lips), T: pack.T, rounds: input.rounds.map(round4) }))
