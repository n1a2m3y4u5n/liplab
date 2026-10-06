// 뜻 없는 말 짝 맞추기(C10)의 추상 도형 12개. 한 목록은 이 가운데 6개를 쓰고 낱말과 짝짓는 일은 서버(backend/nonsense_words.py)가 정한다.
// 이름(id)은 backend SHAPES와 같아야 한다(nonsensePairing.test.mjs가 확인). 색이 아니라 모양으로만 구별되게 한 가지 색(currentColor)으로 그린다.
// 좌표는 viewBox 0 0 100 100. 'fill'은 채운 도형, 'stroke'는 굵은 선 도형이다.
export const SHAPES = {
  circle: { kind: 'fill', d: 'M50 14a36 36 0 1 0 0.01 0Z' },
  triangle: { kind: 'fill', d: 'M50 12 88 84H12Z' },
  square: { kind: 'fill', d: 'M18 18h64v64H18Z' },
  diamond: { kind: 'fill', d: 'M50 8 90 50 50 92 10 50Z' },
  star: { kind: 'fill', d: 'M50 8l11 30h32l-26 19 10 31-27-19-27 19 10-31L7 38h32Z' },
  cross: { kind: 'fill', d: 'M38 10h24v28h28v24H62v28H38V62H10V38h28Z' },
  hexagon: { kind: 'fill', d: 'M30 14h40l20 36-20 36H30L10 50Z' },
  ring: { kind: 'stroke', d: 'M50 18a32 32 0 1 0 0.01 0Z' },
  arch: { kind: 'stroke', d: 'M18 86V50a32 32 0 0 1 64 0v36' },
  bolt: { kind: 'fill', d: 'M58 6 20 56h26l-8 38 42-54H54Z' },
  drop: { kind: 'fill', d: 'M50 8C66 32 80 48 80 64a30 30 0 0 1-60 0c0-16 14-32 30-56Z' },
  bars: { kind: 'fill', d: 'M14 16h72v16H14ZM14 42h72v16H14ZM14 68h72v16H14Z' },
}

export const SHAPE_IDS = Object.keys(SHAPES)
