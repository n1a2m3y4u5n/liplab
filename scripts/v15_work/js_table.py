"""표 JSON → visemeShapes.js의 VISEME_BLENDSHAPES_V15 객체 리터럴(무리별 주석 포함)."""
import json, sys
tab = {int(k): v for k, v in json.load(open(sys.argv[1]))[sys.argv[2]].items()}
ORDER = ['jawOpen', 'mouthClose', 'mouthPressLeft', 'mouthPressRight', 'mouthRollLower', 'mouthRollUpper', 'mouthFunnel', 'mouthPucker',
         'mouthSmileLeft', 'mouthSmileRight', 'mouthStretchLeft', 'mouthStretchRight', 'mouthUpperUpLeft', 'mouthUpperUpRight',
         'mouthLowerDownLeft', 'mouthLowerDownRight', 'mouthShrugUpper', 'mouthShrugLower']
NOTE = {
    1: '양순 ㅂ·ㅃ·ㅍ·ㅁ: 입술을 붙이고(mouthClose·압착) 사람처럼 살짝 내민다(538 양순 돌출 중앙값)',
    2: 'ㅏ·ㅐ: 턱 벌림을 538 범위로 줄이고(0.50 → 0.27) 아랫입술을 내린다. 돌출은 가장 작은 무리(돌출 바닥값을 정하는 무리)',
    3: 'ㅣ·ㅔ: 입꼬리 당김을 크게 줄인다(smile 0.45 → 0.15, stretch 0.20 → 0.07, 538 화자의 폭 진폭은 0에 가깝다). 턱은 조금, 돌출은 비원순 기본값',
    4: 'ㅗ·ㅜ: 둥글림을 538 범위로 줄인다(funnel 0.62 → 0.50, pucker 0.48 → 0.32)',
    5: 'ㅓ·ㅡ: 조금 벌리고 기본 돌출',
    6: '치경 ㄷ·ㅌ·ㄴ·ㄹ·ㅅ: 조금 벌리고 윗입술을 살짝 올리며 기본 돌출',
    7: '연구개 ㄱ·ㅋ·ㅇ: 조금 벌리고 기본 돌출',
    8: '성문 ㅎ: 입 안쪽 무리 가운데 턱을 가장 많이 벌린다',
    9: '이중모음 정지 모양(엔진은 내지 않음, 1단계 순환용): 0.6 × 4 + 0.4 × 2',
    10: '경구개 ㅈ·ㅉ·ㅊ: 조금 벌리고 둥글림을 조금 더',
    11: '양순 전환: 입술을 더 꽉 다물고 아랫입술을 말아 넣는다(538에서 양순 전환이 가장 두드러진 무리)',
    12: '치경 전환: 턱을 조금만 벌린 기본 돌출',
    13: '연구개 전환: 조금 벌린 기본 돌출',
    14: '휴지(어절 사이): 다물지 않고 살짝 벌린 이완 자세(538 쉼 구간)',
    15: '중립(재생 전후·한글 아닌 문자): 편하게 다문 기본 자세',
}
lines = ['export const VISEME_BLENDSHAPES_V15 = {']
for v in range(1, 16):
    sh = tab.get(v, {})
    keys = [k for k in ORDER if sh.get(k, 0) >= 0.01] + sorted(k for k in sh if k not in ORDER and sh[k] >= 0.01)
    body = ', '.join(f'{k}: {round(sh[k], 2)}' for k in keys)
    lines.append(f'  // {v}) {NOTE[v]}')
    lines.append(f'  {v}: {{ {body} }},' if body else f'  {v}: {{}},')
lines.append('}')
print('\n'.join(lines))
