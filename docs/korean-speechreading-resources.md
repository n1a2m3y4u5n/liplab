# 한국어 독화(讀話) 표준 리소스 — LIPLAB 공개 자원 (축 C)

한국어 독화(speechreading)에는 표준화된 공개 자원이 사실상 없다. LIPLAB 고도화 계획서 축 C
("데이터 기반 채점 + 공개 표준 리소스")의 산출물로, 앱 밖 연구·교육에서도 쓸 수 있게 공개한다.

**파일**: [`perceptual-resources.json`](./perceptual-resources.json)

## 구성

| 키 | 내용 | 근거 |
|----|------|------|
| `homophene_dictionary` | 동구형이음(입모양이 같아 시각으로 구별 안 되는 음소 무리) 사전 | 규칙(VISEME_MAP·조음자질) |
| `consonant_visual_space` | 자음 시각 지각공간(MDS 2D 좌표) — 가까울수록 시각적으로 헷갈림 | 규칙 시각자질 + 고전 MDS |
| `difficulty_index` | 단어별 독화 난이도(0~1) = 0.5·비가시성 + 0.3·동구형이음 비율 + 0.2·혼동 이웃밀도 | 규칙 |
| `lookalike_pairs` | 시각 혼동/최소대립 단어쌍(밥↔맘 등) | 규칙 |
| `standard_benchmark` | **표준 평가셋** — 난이도 3구간(easy/medium/hard) 층화, 각 문항에 정답·시각혼동 오답보기·난이도·표적 비심. seed 고정(결정론적, 재현 가능) | 규칙 |
| `jamo_visual_similarity_data` | **데이터 유래** 자모쌍 시각유사도(자음 18개 153쌍, 모음 19개 171쌍) — 강제정렬한 음절 창을 초성·모음 구간으로 나눠 입 주변 블렌드셰이프 27차원(화자별 정규화)을 평균하고, LDA 공간의 자모 중심점 거리를 1 − d/dmax로 바꿈. 키는 두 자모를 유니코드 순으로 붙인 문자열. **기본으로는 싣지 않는다**(`LIPLAB_PUBLISH_DATA_DERIVED=1`일 때만, 아래 배포 묶음 절 참고) | AI Hub 538 실화자 30명 900문장, wav2vec2 강제정렬 + MediaPipe |

## 표준 평가셋 사용법
`standard_benchmark.items`의 각 문항은 4지선다(입모양→단어)다. 오답 보기는 정답과 시각적으로
혼동되는(동구형이음·최소대립) 단어를 우선 배치해 실제 독화 변별력을 잰다. seed가 고정되어
동일 평가셋을 사전·사후로 반복 적용해 향상도를 비교할 수 있다(앱 내 축 I 배치·향상도검사와 호환).

## 정직한 한계
- 규칙 리소스(난이도·동구형이음·시각공간·평가셋)는 조음자질 규칙 기반이며 대규모 데이터 검증 전 단계다.
- `standard_benchmark` 36문항 중 16문항은 오답 보기에 정답과 입모양이 완전히 같은 단어(동구형이음)가 있어,
  입모양만으로는 정답을 가릴 수 없다. 이 문항들은 독화 변별력보다 추측 비중이 크다. 앱의 배치검사와
  `standard_eval_set`은 이런 오답을 빼고 고른다(`assessment._confusable_options`).
- `jamo_visual_similarity_data`는 실화자 데이터 유래이나 30화자 900문장으로 여전히 작다. 같은 특징으로 화자를 바꿔
  입모양 그룹을 가르면 균형 정확도가 자음 0.366, 모음 0.408(우연 0.2 안팎)로 우연보다 높지만, 손코딩 음운
  유사도와의 순위상관은 자음 0.39, 모음 0.28로 약하다. "시각적으로 닮음"과 "조음·청각적으로 닮음"이 갈리는
  부분이 있으나 데이터가 적어 쌍 하나하나의 값은 흔들린다(예: ㅁ·ㅂ 0.92는 뚜렷하지만 ㅃ처럼 드문 자모는 불안정).
  1.2.0(10화자 300문장)은 균형 정확도 0.345·0.386, 순위상관 0.30·0.22였다. 화자를 늘리자 모두 조금씩 올랐다.
  **채점과 문항 선정에는 쓰지 않고** 참고 자원으로만 공개한다. 판별 근거는 `validation` 필드에 함께 든다.
- 1.1.0까지 든 판(4화자 160발화, CTC 구간을 그대로 평균한 코사인)은 CTC 구간이 1~3프레임으로 짧아 거의 모든 쌍이
  0.99 안팎이었고 손코딩과의 상관이 −0.19였다. 1.2.0에서 위 방식으로 바꿨고(10화자), 1.3.0에서 30화자로 다시 만들었다.

## 재생성
```bash
cd backend && python ../scripts/export_perceptual.py   # → docs/perceptual-resources.json
```
데이터 유래 유사도는 `backend/data/c_jamo_similarity.json`이 있으면 포함된다. 이 파일은
`scripts/c_perceptual_demo.py --run <정렬 결과 폴더> --backend backend --tools <실험 도구 폴더> --out c_demo.json --export-sim backend/data/c_jamo_similarity.json`
으로 만든다. 정렬 결과 폴더에는 `d/spans.jsonl`, `bs/`, `manifest.tsv`가, 실험 도구 폴더(`liplab-lab/tools`)에는
`folds.py`와 `train_lipread.py`가 있어야 한다.

라이선스: 규칙 리소스는 자유 사용. 데이터 유래 부분은 원자료(AI Hub 538) 이용약관을 따른다.

## 배포 묶음 만들기
Zenodo 같은 공개 저장소에 올릴 묶음은 다음 명령으로 만든다. 표준 라이브러리만 쓰며, 파일을 만들기만 하고 어디에도 올리지 않는다.
```bash
python3 scripts/build_resource_release.py   # → release/korean-speechreading-resources-1.3.0/
```
묶음에는 `perceptual-resources.json`, `README.md`(한국어 설명과 영어 요약), `LICENSE.md`(CC BY 4.0 고지와 출처 표시 예시),
`CITATION.cff`, `zenodo.json`(업로드 메타데이터 초안), `SHA256SUMS`가 들어간다. 출력 위치는 `--out <폴더>`로 바꾼다(기본 `release/`).

기본값으로는 데이터 유래 부분 `jamo_visual_similarity_data`를 빼고 `meta.data_derived_included`를 `false`로 둔다.
AI Hub 이용약관은 AI Hub 데이터를 승인 없이 제3자에게 제공하지 못하게 하는데, 이 데이터에서 계산한 집계 통계를 재배포해도 되는지는
아직 확인하지 않았다. AI Hub의 확인을 받은 뒤에만 `--include-data-derived`로 넣는다. 이때 폴더 이름 끝에 `-with-data-derived`가
붙어 기본 묶음과 섞이지 않는다. 서버도 같은 기준을 따른다. `/api/public/resources`와 `/api/assessment/resources`는
환경변수 `LIPLAB_PUBLISH_DATA_DERIVED=1`일 때만 이 부분을 싣는다(`perceptual.publish_data_derived`). 저장소 안의 원본
`docs/perceptual-resources.json`에는 데이터 유래 부분이 그대로 들어 있고, 배포 스크립트는 이것으로 README의 검증 수치를 확인한다.

저자, 게시일, DOI, 저작권자, 저장소와 서비스 주소는 `[...]` 자리표시로 나온다. 스크립트 맨 위 `RELEASE_INFO`를 채운 뒤 다시
만들면 모든 파일과 `SHA256SUMS`에 반영되고, 자리표시가 남아 있으면 스크립트가 경고한다. 만든 파일을 손으로 고치면 체크섬이
어긋나므로 `RELEASE_INFO`에서 고친다. 묶음 폴더에 묶음 밖 파일(예: `.DS_Store`)이 있으면 지우지 않고 멈춘다.
