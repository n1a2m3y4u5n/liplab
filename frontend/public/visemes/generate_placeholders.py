#!/usr/bin/env python3
"""
독화(입모양) 2D 폴백 이미지 생성기
------------------------------------------------------------------
3D(WebGL/GLB) 렌더가 불가능한 환경(저사양·구형 브라우저·GLB 로드 실패)에서
학습이 끊기지 않도록, 15개 viseme 각각을 '실제 입모양'으로 그린 SVG를 만든다.

기존 placeholder(숫자만 적힌 색깔 네모)는 독화 학습에 아무 의미가 없었다.
여기서는 조음음성학적 특징(개방/원순/폐쇄/전설/치경 등)을 단순화한 벡터
입모양으로 표현해, 폴백 상태에서도 입모양 자체를 보고 배울 수 있게 한다.

실행: python3 generate_placeholders.py  →  1.svg ~ 15.svg 생성
"""

CX, CY = 256, 300            # 입 중심
SKIN = "#f0c8a4"
LIP = "#d17d6e"
LIP_DARK = "#b5604f"
INNER = "#5c2a34"            # 입안(어두움)
TEETH = "#fdfbf5"
TONGUE = "#e6867f"

# viseme_id: (반폭 w, 세로열림 h, 원순도 round(0~1), 치아, 혀, 완전폐쇄, 라벨)
SHAPES = {
    1:  (120, 0,   0.0, False, False, True,  "ㅂㅍㅁ"),   # 양순음: 폐쇄
    2:  (150, 150, 0.1, True,  False, False, "ㅏㅐ"),      # 개방모음
    3:  (195, 55,  0.0, True,  False, False, "ㅣㅔ"),      # 전설모음(좌우로 넓게)
    4:  (78,  100, 0.95,False, False, False, "ㅗㅜ"),      # 원순모음(둥근 O)
    5:  (140, 85,  0.2, False, False, False, "ㅓㅡ"),      # 중설모음
    6:  (130, 46,  0.0, True,  True,  False, "ㄷㄴㄹㅅ"),  # 치경음(윗니+혀끝)
    7:  (140, 82,  0.1, False, False, False, "ㄱㅋㅇ"),    # 연구개음
    8:  (150, 112, 0.15,False, False, False, "ㅎ"),        # 성문음(이완 개방)
    9:  (112, 92,  0.5, False, False, False, "ㅘㅝ"),      # 이중모음(원순+개방)
    10: (128, 56,  0.2, True,  False, False, "ㅈㅊ"),      # 경구개음
    11: (120, 20,  0.0, False, False, False, "→ㅂ"),       # 전환→양순
    12: (130, 42,  0.0, True,  False, False, "→ㄷ"),       # 전환→치경
    13: (135, 56,  0.05,False, False, False, "→ㄱ"),       # 전환→연구개
    14: (110, 0,   0.0, False, False, True,  "휴지"),      # 휴지기
    15: (118, 8,   0.0, False, False, False, "중립"),      # 중립
}


def mouth_paths(w, h, r, teeth, tongue, closed):
    ew = w * (1 - 0.45 * r)          # 원순일수록 가로폭이 좁아짐
    parts = []
    if closed or h <= 2:
        # 다문 입: 살짝 굴곡진 한 줄
        parts.append(
            f'<path d="M {CX-ew:.0f} {CY} Q {CX} {CY+8} {CX+ew:.0f} {CY}" '
            f'fill="none" stroke="{LIP_DARK}" stroke-width="14" stroke-linecap="round"/>'
        )
        return "\n  ".join(parts)

    # 입안(어두운 영역) = 위/아래 입술 안쪽 곡선으로 닫힌 형태
    parts.append(
        f'<path d="M {CX-ew:.0f} {CY} Q {CX} {CY-h} {CX+ew:.0f} {CY} '
        f'Q {CX} {CY+h} {CX-ew:.0f} {CY} Z" fill="{INNER}"/>'
    )
    if teeth:
        tw = ew * 0.82
        parts.append(
            f'<rect x="{CX-tw:.0f}" y="{CY-h+6:.0f}" width="{2*tw:.0f}" '
            f'height="{max(16, h*0.34):.0f}" rx="7" fill="{TEETH}"/>'
        )
    if tongue:
        parts.append(
            f'<ellipse cx="{CX}" cy="{CY+h*0.35:.0f}" rx="{ew*0.55:.0f}" '
            f'ry="{h*0.5:.0f}" fill="{TONGUE}"/>'
        )
    # 입술 테두리(위/아래)
    parts.append(
        f'<path d="M {CX-ew:.0f} {CY} Q {CX} {CY-h} {CX+ew:.0f} {CY}" '
        f'fill="none" stroke="{LIP}" stroke-width="16" stroke-linecap="round"/>'
    )
    parts.append(
        f'<path d="M {CX-ew:.0f} {CY} Q {CX} {CY+h} {CX+ew:.0f} {CY}" '
        f'fill="none" stroke="{LIP}" stroke-width="18" stroke-linecap="round"/>'
    )
    if r > 0.4:  # 원순: 앞으로 내민 입술 링을 덧그림
        parts.append(
            f'<ellipse cx="{CX}" cy="{CY}" rx="{ew+18:.0f}" ry="{h+16:.0f}" '
            f'fill="none" stroke="{LIP_DARK}" stroke-width="6" opacity="0.55"/>'
        )
    return "\n  ".join(parts)


def svg(vid):
    w, h, r, teeth, tongue, closed, label = SHAPES[vid]
    body = mouth_paths(w, h, r, teeth, tongue, closed)
    return f'''<svg width="512" height="512" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">
  <rect width="512" height="512" fill="none"/>
  <ellipse cx="256" cy="256" rx="232" ry="232" fill="{SKIN}"/>
  <path d="M 256 176 L 238 262 Q 256 276 274 262 Z" fill="#e0b48c"/>
  {body}
  <text x="256" y="470" font-size="52" fill="#7c4a2d" text-anchor="middle"
        font-family="'Apple SD Gothic Neo','Malgun Gothic',sans-serif" font-weight="700">{label}</text>
</svg>
'''


for vid in SHAPES:
    with open(f"{vid}.svg", "w", encoding="utf-8") as f:
        f.write(svg(vid))
print("generated 1.svg ~ 15.svg")
