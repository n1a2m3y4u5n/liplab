# 한국어 독화(讀話) 표준 리소스 — LIPLAB 공개 자원 (축 C)

한국어 독화(speechreading)에는 표준화된 공개 자원이 사실상 없다. LIPLAB 고도화 계획서 축 C
("데이터 기반 채점 + 공개 표준 리소스")의 산출물로, 앱 밖 연구·교육에서도 쓸 수 있게 공개한다.

**파일**: [`perceptual-resources.json`](./perceptual-resources.json)

## 구성

| 키 | 내용 | 근거 |
|----|------|------|
| `homophene_dictionary` | 동구형이음(입모양이 같아 시각으로 구별 안 되는 음소 무리) 사전 | 규칙(VISEME_MAP·조음자질) |
| `consonant_visual_space` | 자음 시각 지각공간(MDS 2D 좌표) — 가까울수록 시각적으로 헷갈림 | 규칙 시각자질 + 고전 MDS |
| `difficulty_index` | 단어별 독화 난이도(0~1) = 가시성 낮음 × 동구형이음 이웃밀도 | 규칙 |
| `lookalike_pairs` | 시각 혼동/최소대립 단어쌍(밥↔맘 등) | 규칙 |
| `standard_benchmark` | **표준 평가셋** — 난이도 3구간(easy/medium/hard) 층화, 각 문항에 정답·시각혼동 오답보기·난이도·표적 비심. seed 고정(결정론적, 재현 가능) | 규칙 |
| `jamo_visual_similarity_data` | **데이터 유래** 자모쌍 시각유사도(자음 16개 120쌍, 모음 18개 153쌍) — 강제정렬한 음절 창을 초성·모음 구간으로 나눠 입 주변 블렌드셰이프 27차원(화자별 정규화)을 평균하고, LDA 공간의 자모 중심점 거리를 1 − d/dmax로 바꿈. 키는 두 자모를 유니코드 순으로 붙인 문자열 | AI Hub 538 실화자 10명 300문장, wav2vec2 강제정렬 + MediaPipe |

## 표준 평가셋 사용법
`standard_benchmark.items`의 각 문항은 4지선다(입모양→단어)다. 오답 보기는 정답과 시각적으로
혼동되는(동구형이음·최소대립) 단어를 우선 배치해 실제 독화 변별력을 잰다. seed가 고정되어
동일 평가셋을 사전·사후로 반복 적용해 향상도를 비교할 수 있다(앱 내 축 I 배치·향상도검사와 호환).

## 정직한 한계
- 규칙 리소스(난이도·동구형이음·시각공간·평가셋)는 조음자질 규칙 기반이며 대규모 데이터 검증 전 단계다.
- `jamo_visual_similarity_data`는 실화자 데이터 유래이나 10화자 300문장으로 작다. 같은 특징으로 화자를 바꿔
  입모양 그룹을 가르면 균형 정확도가 자음 0.345, 모음 0.386(우연 0.2 안팎)으로 우연보다 높지만, 손코딩 음운
  유사도와의 순위상관은 자음 0.30, 모음 0.22로 약하다. "시각적으로 닮음"과 "조음·청각적으로 닮음"이 갈리는
  부분이 있으나 데이터가 적어 쌍 하나하나의 값은 흔들린다(예: ㅁ·ㅂ 0.90은 뚜렷하지만 ㅃ처럼 드문 자모는 불안정).
  **채점과 문항 선정에는 쓰지 않고** 참고 자원으로만 공개한다. 판별 근거는 `validation` 필드에 함께 든다.
- 1.1.0까지 든 판(4화자 160발화, CTC 구간을 그대로 평균한 코사인)은 CTC 구간이 1~3프레임으로 짧아 거의 모든 쌍이
  0.99 안팎이었고 손코딩과의 상관이 −0.19였다. 1.2.0에서 위 방식으로 바꿨다.

## 재생성
```bash
cd backend && python ../scripts/export_perceptual.py   # → docs/perceptual-resources.json
```
데이터 유래 유사도는 `backend/data/c_jamo_similarity.json`이 있으면 포함된다. 이 파일은
`scripts/c_perceptual_demo.py --run <정렬 결과 폴더> --backend backend --tools <실험 도구 폴더> --out c_demo.json --export-sim backend/data/c_jamo_similarity.json`
으로 만든다. 정렬 결과 폴더에는 `d/spans.jsonl`, `bs/`, `manifest.tsv`가, 실험 도구 폴더(`liplab-lab/tools`)에는
`folds.py`와 `train_lipread.py`가 있어야 한다.

라이선스: 규칙 리소스는 자유 사용. 데이터 유래 부분은 원자료(AI Hub 538) 이용약관을 따른다.
