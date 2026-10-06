import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  deviceClass, uaFamilies, deviceInfo, addVideoQuality, buildRenderLog, noiseGain, rmsDbfs, composeSyllable,
  nonsensePreview, playState, reactionTimes, queueOf, hasWebGL,
} from './pilotBattery.js'

test('기기 분류와 사용자 에이전트 계열(판 번호는 버림)', () => {
  assert.equal(deviceClass(390, 844, true), 'phone')
  assert.equal(deviceClass(820, 1180, true), 'tablet')
  assert.equal(deviceClass(1920, 1080, false), 'desktop')
  assert.deepEqual(uaFamilies('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1'),
    { os_family: 'ios', browser_family: 'safari' })
  assert.deepEqual(uaFamilies('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36 Edg/120.0'),
    { os_family: 'windows', browser_family: 'edge' })
  assert.deepEqual(uaFamilies('Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 SamsungBrowser/24.0 Chrome/117 Mobile Safari/537.36'),
    { os_family: 'android', browser_family: 'samsung' })
  assert.deepEqual(uaFamilies(''), { os_family: 'other', browser_family: 'other' })
})

test('기기 요약은 정해진 키만 모은다', () => {
  const win = { screen: { width: 1280, height: 800 }, innerWidth: 1200, innerHeight: 700, devicePixelRatio: 2.004,
    navigator: { maxTouchPoints: 0, userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120 Safari/537.36' } }
  assert.deepEqual(deviceInfo(win), { screen_w: 1280, screen_h: 800, viewport_w: 1200, viewport_h: 700, dpr: 2,
    device_class: 'desktop', os_family: 'mac', browser_family: 'chrome' })
  assert.deepEqual(deviceInfo(null), {})
  assert.equal(hasWebGL(null), false)
})

test('렌더링 요약: 프레임 지연과 영상 누락 비율', () => {
  const v = addVideoQuality(addVideoQuality(null, { totalVideoFrames: 120, droppedVideoFrames: 3 }), { totalVideoFrames: 80, droppedVideoFrames: 1 })
  assert.deepEqual(v, { total: 200, dropped: 4 })
  const log = buildRenderLog({ timing: { frames: 10, meanLateMs: 1.5, maxLateMs: 9, over20Rate: 0, over50Rate: 0 }, video: v,
    device: { dpr: 2 }, renderMode: 'video', webgl: true })
  assert.deepEqual(log, { scope: 'layer', frames: 10, mean_late_ms: 1.5, max_late_ms: 9, over20_rate: 0, over50_rate: 0, dpr: 2,
    render_mode: 'video', webgl: true, video_total_frames: 200, video_dropped_frames: 4, video_drop_rate: 0.02 })
  assert.equal('video_total_frames' in buildRenderLog({ timing: {}, device: {} }), false)
})

test('잡음 이득과 RMS(서버 noise_gain과 같은 식)', () => {
  assert.ok(Math.abs(noiseGain(-20, -20, 0) - 1) < 1e-12)
  assert.ok(Math.abs(noiseGain(-20, -26, 0) - 10 ** (6 / 20)) < 1e-12)   // 잡음이 6 dB 작으면 키운다
  assert.ok(Math.abs(noiseGain(-20, -20, 10) - 10 ** (-10 / 20)) < 1e-12)  // SNR이 높으면 잡음을 줄인다
  assert.ok(Math.abs(rmsDbfs(new Float32Array([0.5, -0.5, 0.5, -0.5])) - 20 * Math.log10(0.5)) < 1e-6)
  assert.equal(rmsDbfs(new Float32Array(4)), -Infinity)
  assert.equal(rmsDbfs([]), -Infinity)
})

test('무의미 낱말 음절 조립과 미리보기', () => {
  assert.equal(composeSyllable('ㅂ', 'ㅏ'), '바')
  assert.equal(composeSyllable('ㄹ', 'ㅗ', 'ㄱ'), '록')
  assert.equal(composeSyllable('x', 'ㅏ'), '')
  assert.equal(nonsensePreview(['ㅏ', 'ㅗ'], [null, null, null]), '_ㅏ_ㅗ_')
  assert.equal(nonsensePreview(['ㅏ', 'ㅗ'], ['ㅂ', 'ㄹ', 'ㄱ']), '바록')
  assert.equal(nonsensePreview(['ㅏ', 'ㅗ'], ['ㅂ', null, 'ㄱ']), '바_ㅗㄱ')
  assert.equal(nonsensePreview(['ㅏ', 'ㅗ'], ['ㅂ', 'ㄹ', null]), '바로_')
})

test('재생·답 가능 여부와 반응 시간', () => {
  assert.deepEqual(playState({ plays: 0, maxPlays: 2 }), { canPlay: true, canAnswer: false, left: 2 })
  assert.deepEqual(playState({ plays: 1, playing: true, maxPlays: 2 }), { canPlay: false, canAnswer: false, left: 1 })
  assert.deepEqual(playState({ plays: 2, firstEndedAt: 100, maxPlays: 2 }), { canPlay: false, canAnswer: true, left: 0 })
  assert.deepEqual(reactionTimes({ firstOnsetAt: 1000, firstEndedAt: 2500.4, answeredAt: 4000 }), { rt_ms: 1500, rt_from_onset_ms: 3000 })
  assert.deepEqual(reactionTimes({ firstOnsetAt: null, firstEndedAt: null, answeredAt: 4000 }), { rt_ms: null, rt_from_onset_ms: null })
})

test('층 진행: 준비 전 문항은 세지 않는다', () => {
  const q = queueOf([{ id: 'a', ready: true }, { id: 'b', ready: false, reason: 'media' }, { id: 'c', ready: true, answered: true }])
  assert.deepEqual(q.todo.map((x) => x.id), ['a'])
  assert.equal(q.nReady, 2)
  assert.equal(q.nDone, 1)
  assert.deepEqual(q.missing.map((x) => x.id), ['b'])
})
