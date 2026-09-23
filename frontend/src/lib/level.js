/**
 * 레벨 진행 계산 — 백엔드 규칙 그대로(main.py: level = floor(sqrt(total_xp / 100)) + 1).
 * L레벨 구간은 XP [100·(L-1)², 100·L²). 오른쪽 패널 "레벨 진행"(137:163)과 프로필 XP 바가
 * 같은 값을 보이도록 이 함수를 같이 쓴다.
 * 레벨은 서버가 내려준 값(current_level)을 믿는다 — 시드 계정처럼 XP보다 레벨이 앞서면 남은 XP는 0.
 */
export function levelProgress(level, xp) {
  const L = Math.max(1, Math.floor(Number(level) || 1))
  const cur = Math.max(0, Number(xp) || 0)
  const floor = 100 * (L - 1) ** 2
  const next = 100 * L ** 2
  const span = next - floor
  const inLevel = Math.min(span, Math.max(0, cur - floor))
  return {
    level: L,
    floor,                                  // 이 레벨 시작 XP
    next,                                   // 다음 레벨 시작 XP
    span,                                   // 이 레벨 구간 크기
    inLevel,                                // 이 레벨에서 쌓은 XP
    remaining: Math.max(0, next - cur),     // "다음 레벨까지 N XP 남음"
    pct: span > 0 ? (inLevel / span) * 100 : 0,
  }
}
