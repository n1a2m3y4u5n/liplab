// 말하기 모음·자음 단계(2·3)의 낱말 속 소리 확인(docs/curriculum-roadmap.md 2-5, P9).
// 따로 낸 음절 점수가 숙달 문턱에 닿으면 서버가 목표 소리가 첫 음절에 든 낱말 4개(probes)를 준다. 화면은 이것을 문항 사이에 끼워 내고,
// 채점은 단어 규칙(합격 65)으로 하며 최근 4번 중 3번 합격하면 숙달이다(서버 speak_curriculum._PROBE). 확인 낱말은 { target, probe: true, sound } 모양이다.

export const PROBE_HEADING = '배운 소리를 낱말 속에서도 내 보세요'
export const PROBE_CATEGORY = '낱말 속 소리 확인'

/** 문항 목록에 확인 낱말을 끼운다. 이미 든 확인 낱말은 빼고 at번째 문항 바로 뒤(at < 0이면 맨 앞)에 넣는다. 낱말이 없으면 확인 낱말만 뺀다. */
export function withProbes(items, probes, at = -1) {
  const list = items || []
  const base = list.filter((it) => !it?.probe)
  const tagged = (probes || []).map((p) => ({ ...p, probe: true }))
  if (!tagged.length) return base
  const cut = at < 0 ? 0 : list.slice(0, at + 1).filter((it) => !it?.probe).length
  return [...base.slice(0, cut), ...tagged, ...base.slice(cut)]
}

/** 다음 문항 번호(끝에서 처음으로 돈다). 숙달한 뒤(skipProbes)에는 남은 확인 낱말을 건너뛴다. */
export function nextIndex(items, idx, skipProbes = false) {
  const n = (items || []).length
  if (!n) return 0
  for (let k = 1; k <= n; k += 1) {
    const j = (idx + k) % n
    if (!(skipProbes && items[j]?.probe)) return j
  }
  return (idx + 1) % n
}

export const hasProbes = (items) => (items || []).some((it) => it?.probe)

/** 진행 막대 아래 한 줄. 확인 중이 아니거나 정보가 없으면 null. */
export function probeStatusText(p) {
  if (!p || !p.carryover) return null
  const head = p.tried ? `최근 ${p.tried}번 중 ${p.passed}번 합격` : '아직 확인 전'
  return `숙달 점수에 닿았어요. 낱말 속 소리 확인: ${head} (최근 ${p.n}번 중 ${p.need}번 합격하면 숙달)`
}
