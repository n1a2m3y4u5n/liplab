# P3 검사 묶음 촬영 목록

목록 파일 판 `draft-2026-10-07`(상태 draft)에서 `scripts/build_shot_list.py`로 만든다. 목록을 고치면 다시 만든다.
점검표는 `docs/pilot/shot-list.csv`, 촬영 뒤 확인은 `python3 scripts/check_pilot_media.py <영상 폴더>`.

## 촬영 규칙

- 1080p, 60fps, H.264 mp4, 음성 48kHz. 정면, 어깨 위부터, 입이 화면 가운데. 조명은 얼굴 앞쪽에서 고르게.
- 클립마다 입을 다문 채 1초 → 한 번 말하기 → 입을 다문 채 1초. 말하기 전후로 웃거나 고개를 끄덕이지 않는다.
- 평소 말 빠르기와 크기로 말한다(일부러 또박또박하지 않는다). 틀리면 그 클립만 다시 찍는다.
- 소리 '필수' 묶음(소음 속 문장, SNR)은 조용한 방에서 녹음한다. 잡음은 나중에 화면에서 섞는다.
- 파일 이름은 아래 '파일' 열 그대로(대소문자 포함). 영상 폴더(LIPLAB_PILOT_MEDIA_DIR) 안에 그 경로로 둔다.
- 같은 자리에서 iPhone ARKit 기록(Live Link Face)을 함께 켠다(계획 P12). 오조음 세트·단독 모음 녹음도 같은 날 받는다.

## 화자 T1 (300클립)

### 실제 얼굴 낱말 (72클립, 소리 녹음만)

| 폼 | 번호 | 대본 | 파일 |
|---|---|---|---|
| A | A1 | 이 | `words/T1/A1.mp4` |
| A | A2 | 호피 | `words/T1/A2.mp4` |
| A | A3 | 기쁨 | `words/T1/A3.mp4` |
| A | A4 | 무지개 | `words/T1/A4.mp4` |
| A | A5 | 지붕 | `words/T1/A5.mp4` |
| A | A6 | 포차 | `words/T1/A6.mp4` |
| A | A7 | 가방 | `words/T1/A7.mp4` |
| A | A8 | 복 | `words/T1/A8.mp4` |
| A | A9 | 연못 | `words/T1/A9.mp4` |
| A | A10 | 삼촌 | `words/T1/A10.mp4` |
| A | A11 | 동무 | `words/T1/A11.mp4` |
| A | A12 | 세탁기 | `words/T1/A12.mp4` |
| A | A13 | 빨간 | `words/T1/A13.mp4` |
| A | A14 | 기린 | `words/T1/A14.mp4` |
| A | A15 | 가지 | `words/T1/A15.mp4` |
| A | A16 | 책상 | `words/T1/A16.mp4` |
| A | A17 | 공원 | `words/T1/A17.mp4` |
| A | A18 | 문 | `words/T1/A18.mp4` |
| A | A19 | 짐 | `words/T1/A19.mp4` |
| A | A20 | 장문 | `words/T1/A20.mp4` |
| A | A21 | 계란 | `words/T1/A21.mp4` |
| A | A22 | 폭소 | `words/T1/A22.mp4` |
| A | A23 | 칸 | `words/T1/A23.mp4` |
| A | A24 | 딸 | `words/T1/A24.mp4` |
| B | B1 | 우유 | `words/T1/B1.mp4` |
| B | B2 | 볶음밥 | `words/T1/B2.mp4` |
| B | B3 | 외로움 | `words/T1/B3.mp4` |
| B | B4 | 빗물 | `words/T1/B4.mp4` |
| B | B5 | 입술 | `words/T1/B5.mp4` |
| B | B6 | 파치 | `words/T1/B6.mp4` |
| B | B7 | 수박 | `words/T1/B7.mp4` |
| B | B8 | 숨 | `words/T1/B8.mp4` |
| B | B9 | 칠판 | `words/T1/B9.mp4` |
| B | B10 | 눈물 | `words/T1/B10.mp4` |
| B | B11 | 문제 | `words/T1/B11.mp4` |
| B | B12 | 하늘 | `words/T1/B12.mp4` |
| B | B13 | 발간 | `words/T1/B13.mp4` |
| B | B14 | 국자 | `words/T1/B14.mp4` |
| B | B15 | 가치 | `words/T1/B15.mp4` |
| B | B16 | 닭 | `words/T1/B16.mp4` |
| B | B17 | 수건 | `words/T1/B17.mp4` |
| B | B18 | 반 | `words/T1/B18.mp4` |
| B | B19 | 삼 | `words/T1/B19.mp4` |
| B | B20 | 토 | `words/T1/B20.mp4` |
| B | B21 | 계산 | `words/T1/B21.mp4` |
| B | B22 | 라면 | `words/T1/B22.mp4` |
| B | B23 | 간 | `words/T1/B23.mp4` |
| B | B24 | 돈 | `words/T1/B24.mp4` |
| C | C1 | 무 | `words/T1/C1.mp4` |
| C | C2 | 호미 | `words/T1/C2.mp4` |
| C | C3 | 램프 | `words/T1/C3.mp4` |
| C | C4 | 바가지 | `words/T1/C4.mp4` |
| C | C5 | 감자 | `words/T1/C5.mp4` |
| C | C6 | 나무 | `words/T1/C6.mp4` |
| C | C7 | 가망 | `words/T1/C7.mp4` |
| C | C8 | 목 | `words/T1/C8.mp4` |
| C | C9 | 가위 | `words/T1/C9.mp4` |
| C | C10 | 강물 | `words/T1/C10.mp4` |
| C | C11 | 농부 | `words/T1/C11.mp4` |
| C | C12 | 도시락 | `words/T1/C12.mp4` |
| C | C13 | 가늠 | `words/T1/C13.mp4` |
| C | C14 | 국수 | `words/T1/C14.mp4` |
| C | C15 | 까치 | `words/T1/C15.mp4` |
| C | C16 | 공책 | `words/T1/C16.mp4` |
| C | C17 | 손녀 | `words/T1/C17.mp4` |
| C | C18 | 남 | `words/T1/C18.mp4` |
| C | C19 | 납 | `words/T1/C19.mp4` |
| C | C20 | 작문 | `words/T1/C20.mp4` |
| C | C21 | 계단 | `words/T1/C21.mp4` |
| C | C22 | 그릇 | `words/T1/C22.mp4` |
| C | C23 | 갓 | `words/T1/C23.mp4` |
| C | C24 | 날 | `words/T1/C24.mp4` |

### 개방형 문장 (132클립, 소리 녹음만)

| 폼 | 번호 | 대본 | 파일 |
|---|---|---|---|
| A | SA01 | 감기에 걸렸어요 | `sentences/T1/SA01.mp4` |
| A | SA02 | 새 옷을 입어 봤어요 | `sentences/T1/SA02.mp4` |
| A | SA03 | 시계가 멈췄어요 | `sentences/T1/SA03.mp4` |
| A | SA04 | 무슨 일이 있었어요 | `sentences/T1/SA04.mp4` |
| A | SA05 | 물이 너무 뜨거워요 | `sentences/T1/SA05.mp4` |
| A | SA06 | 눈이 펑펑 내려요 | `sentences/T1/SA06.mp4` |
| A | SA07 | 선물을 받았어요 | `sentences/T1/SA07.mp4` |
| A | SA08 | 매일 걸어서 다녀요 | `sentences/T1/SA08.mp4` |
| A | SA09 | 시험을 잘 봤어요 | `sentences/T1/SA09.mp4` |
| A | SA10 | 창밖이 시끄러워요 | `sentences/T1/SA10.mp4` |
| A | SA11 | 잘 먹겠습니다 | `sentences/T1/SA11.mp4` |
| A | SA12 | 글씨가 너무 작아요 | `sentences/T1/SA12.mp4` |
| A | SA13 | 꽃이 활짝 피었어요 | `sentences/T1/SA13.mp4` |
| A | SA14 | 사진을 보내 주세요 | `sentences/T1/SA14.mp4` |
| A | SA15 | 열쇠를 찾고 있어요 | `sentences/T1/SA15.mp4` |
| A | SA16 | 여기 앉아도 괜찮아요 | `sentences/T1/SA16.mp4` |
| A | SA17 | 옷이 너무 작아졌어요 | `sentences/T1/SA17.mp4` |
| A | SA18 | 생선을 좋아하나요 | `sentences/T1/SA18.mp4` |
| A | SA19 | 소리가 잘 안 들려요 | `sentences/T1/SA19.mp4` |
| A | SA20 | 고기를 구워 먹었어요 | `sentences/T1/SA20.mp4` |
| A | SA21 | 그림을 그리고 있어요 | `sentences/T1/SA21.mp4` |
| A | SA22 | 아빠가 차를 고쳤어요 | `sentences/T1/SA22.mp4` |
| A | SA23 | 아침을 거르지 마세요 | `sentences/T1/SA23.mp4` |
| A | SA24 | 공을 멀리 던졌어요 | `sentences/T1/SA24.mp4` |
| A | SA25 | 기차가 곧 출발해요 | `sentences/T1/SA25.mp4` |
| A | SA26 | 냉장고에 넣어 두세요 | `sentences/T1/SA26.mp4` |
| A | SA27 | 노래를 부르고 싶어요 | `sentences/T1/SA27.mp4` |
| A | SA28 | 어제 늦게 잠들었어요 | `sentences/T1/SA28.mp4` |
| A | SA29 | 표를 미리 사 두었어요 | `sentences/T1/SA29.mp4` |
| A | SA30 | 내일 다시 연락할게요 | `sentences/T1/SA30.mp4` |
| A | SA31 | 늦어서 정말 미안해요 | `sentences/T1/SA31.mp4` |
| A | SA32 | 거울을 깨끗이 닦았어요 | `sentences/T1/SA32.mp4` |
| A | SA33 | 바다에 놀러 가고 싶어요 | `sentences/T1/SA33.mp4` |
| A | SA34 | 머리를 짧게 잘랐어요 | `sentences/T1/SA34.mp4` |
| A | SA35 | 설거지는 제가 할게요 | `sentences/T1/SA35.mp4` |
| A | SA36 | 저도 그렇게 생각해요 | `sentences/T1/SA36.mp4` |
| A | SA37 | 이번 주는 정말 바빠요 | `sentences/T1/SA37.mp4` |
| A | SA38 | 현관 앞에 상자가 있어요 | `sentences/T1/SA38.mp4` |
| A | SA39 | 저녁에 산책할까요 | `sentences/T1/SA39.mp4` |
| A | SA40 | 별이 반짝반짝 빛나요 | `sentences/T1/SA40.mp4` |
| B | SB01 | 같이 사진 찍어요 | `sentences/T1/SB01.mp4` |
| B | SB02 | 만나서 반가워요 | `sentences/T1/SB02.mp4` |
| B | SB03 | 책을 빌려 왔어요 | `sentences/T1/SB03.mp4` |
| B | SB04 | 기분이 아주 좋아요 | `sentences/T1/SB04.mp4` |
| B | SB05 | 화장실이 어디예요 | `sentences/T1/SB05.mp4` |
| B | SB06 | 금방 돌아올게요 | `sentences/T1/SB06.mp4` |
| B | SB07 | 고양이가 잠을 자요 | `sentences/T1/SB07.mp4` |
| B | SB08 | 다음 주에 또 만나요 | `sentences/T1/SB08.mp4` |
| B | SB09 | 바람이 많이 불어요 | `sentences/T1/SB09.mp4` |
| B | SB10 | 집에 손님이 왔어요 | `sentences/T1/SB10.mp4` |
| B | SB11 | 제 말 잘 들리세요 | `sentences/T1/SB11.mp4` |
| B | SB12 | 그 사람을 잘 알아요 | `sentences/T1/SB12.mp4` |
| B | SB13 | 화분에 물을 줬어요 | `sentences/T1/SB13.mp4` |
| B | SB14 | 사전을 찾아봤어요 | `sentences/T1/SB14.mp4` |
| B | SB15 | 반찬이 정말 많아요 | `sentences/T1/SB15.mp4` |
| B | SB16 | 병원에 가 봐야겠어요 | `sentences/T1/SB16.mp4` |
| B | SB17 | 왜 그렇게 웃고 있어요 | `sentences/T1/SB17.mp4` |
| B | SB18 | 비가 그칠 것 같아요 | `sentences/T1/SB18.mp4` |
| B | SB19 | 엄마한테 혼났어요 | `sentences/T1/SB19.mp4` |
| B | SB20 | 축구를 하러 나가요 | `sentences/T1/SB20.mp4` |
| B | SB21 | 길을 잃어서 헤맸어요 | `sentences/T1/SB21.mp4` |
| B | SB22 | 아기가 방긋 웃었어요 | `sentences/T1/SB22.mp4` |
| B | SB23 | 안경을 잃어버렸어요 | `sentences/T1/SB23.mp4` |
| B | SB24 | 해가 벌써 지고 있어요 | `sentences/T1/SB24.mp4` |
| B | SB25 | 문자를 보내 줄게요 | `sentences/T1/SB25.mp4` |
| B | SB26 | 운동화 끈이 풀렸어요 | `sentences/T1/SB26.mp4` |
| B | SB27 | 방이 생각보다 추워요 | `sentences/T1/SB27.mp4` |
| B | SB28 | 수업이 일찍 끝났어요 | `sentences/T1/SB28.mp4` |
| B | SB29 | 자전거를 타고 왔어요 | `sentences/T1/SB29.mp4` |
| B | SB30 | 일이 아직 많이 남았어요 | `sentences/T1/SB30.mp4` |
| B | SB31 | 동생과 같이 놀았어요 | `sentences/T1/SB31.mp4` |
| B | SB32 | 점심 먹으러 같이 가요 | `sentences/T1/SB32.mp4` |
| B | SB33 | 주말에 산에 올라갔어요 | `sentences/T1/SB33.mp4` |
| B | SB34 | 국이 조금 짠 것 같아요 | `sentences/T1/SB34.mp4` |
| B | SB35 | 시간이 정말 빨리 가요 | `sentences/T1/SB35.mp4` |
| B | SB36 | 모래성을 쌓았어요 | `sentences/T1/SB36.mp4` |
| B | SB37 | 방을 깨끗하게 치웠어요 | `sentences/T1/SB37.mp4` |
| B | SB38 | 학교 앞에서 기다릴게요 | `sentences/T1/SB38.mp4` |
| B | SB39 | 연필을 빌려줄 수 있어요 | `sentences/T1/SB39.mp4` |
| B | SB40 | 친구에게 편지를 썼어요 | `sentences/T1/SB40.mp4` |
| C | SC01 | 괜찮아질 거예요 | `sentences/T1/SC01.mp4` |
| C | SC02 | 길이 많이 막혀요 | `sentences/T1/SC02.mp4` |
| C | SC03 | 가을이 벌써 왔어요 | `sentences/T1/SC03.mp4` |
| C | SC04 | 겨울에는 눈이 와요 | `sentences/T1/SC04.mp4` |
| C | SC05 | 회의가 길어졌어요 | `sentences/T1/SC05.mp4` |
| C | SC06 | 걱정하지 마세요 | `sentences/T1/SC06.mp4` |
| C | SC07 | 너무 피곤해 보여요 | `sentences/T1/SC07.mp4` |
| C | SC08 | 다리가 조금 아파요 | `sentences/T1/SC08.mp4` |
| C | SC09 | 아침에 운동을 해요 | `sentences/T1/SC09.mp4` |
| C | SC10 | 지갑을 두고 왔어요 | `sentences/T1/SC10.mp4` |
| C | SC11 | 편지를 써 볼게요 | `sentences/T1/SC11.mp4` |
| C | SC12 | 과일을 깎아 줄게요 | `sentences/T1/SC12.mp4` |
| C | SC13 | 모자를 쓰고 나가요 | `sentences/T1/SC13.mp4` |
| C | SC14 | 빨래를 널어야 해요 | `sentences/T1/SC14.mp4` |
| C | SC15 | 줄넘기를 했어요 | `sentences/T1/SC15.mp4` |
| C | SC16 | 바둑을 배우고 있어요 | `sentences/T1/SC16.mp4` |
| C | SC17 | 그 노래 정말 좋아요 | `sentences/T1/SC17.mp4` |
| C | SC18 | 목도리가 따뜻해요 | `sentences/T1/SC18.mp4` |
| C | SC19 | 열심히 연습했어요 | `sentences/T1/SC19.mp4` |
| C | SC20 | 오늘은 일찍 잘게요 | `sentences/T1/SC20.mp4` |
| C | SC21 | 김치가 아주 맛있어요 | `sentences/T1/SC21.mp4` |
| C | SC22 | 동생이 많이 울었어요 | `sentences/T1/SC22.mp4` |
| C | SC23 | 오늘은 쉬는 날이에요 | `sentences/T1/SC23.mp4` |
| C | SC24 | 조용히 해 주시겠어요 | `sentences/T1/SC24.mp4` |
| C | SC25 | 주머니에 동전이 있어요 | `sentences/T1/SC25.mp4` |
| C | SC26 | 숙제를 다 끝냈어요 | `sentences/T1/SC26.mp4` |
| C | SC27 | 버섯을 볶아 먹었어요 | `sentences/T1/SC27.mp4` |
| C | SC28 | 그건 잘 모르겠어요 | `sentences/T1/SC28.mp4` |
| C | SC29 | 옆자리에 앉아도 될까요 | `sentences/T1/SC29.mp4` |
| C | SC30 | 옆집 아저씨가 오셨어요 | `sentences/T1/SC30.mp4` |
| C | SC31 | 선생님께 물어봤어요 | `sentences/T1/SC31.mp4` |
| C | SC32 | 장갑을 끼고 나가세요 | `sentences/T1/SC32.mp4` |
| C | SC33 | 지하철에 사람이 많아요 | `sentences/T1/SC33.mp4` |
| C | SC34 | 할머니 댁에 다녀왔어요 | `sentences/T1/SC34.mp4` |
| C | SC35 | 떡볶이가 너무 매워요 | `sentences/T1/SC35.mp4` |
| C | SC36 | 은행에 들렀다 갈게요 | `sentences/T1/SC36.mp4` |
| C | SC37 | 시장에서 사과를 샀어요 | `sentences/T1/SC37.mp4` |
| C | SC38 | 엄마가 저녁을 차렸어요 | `sentences/T1/SC38.mp4` |
| C | SC39 | 열이 조금 있는 것 같아요 | `sentences/T1/SC39.mp4` |
| C | SC40 | 오늘 저녁은 뭐 먹을까요 | `sentences/T1/SC40.mp4` |
| 예비 | SR01 | 냄비에 물이 끓어요 | `sentences/T1/SR01.mp4` |
| 예비 | SR02 | 오늘 많이 걸었어요 | `sentences/T1/SR02.mp4` |
| 예비 | SR03 | 동생이 키가 컸어요 | `sentences/T1/SR03.mp4` |
| 예비 | SR04 | 우체국에 다녀올게요 | `sentences/T1/SR04.mp4` |
| 예비 | SR05 | 신호등이 바뀌었어요 | `sentences/T1/SR05.mp4` |
| 예비 | SR06 | 목소리가 참 좋네요 | `sentences/T1/SR06.mp4` |
| 예비 | SR07 | 생일 정말 축하해요 | `sentences/T1/SR07.mp4` |
| 예비 | SR08 | 햇볕이 정말 따가워요 | `sentences/T1/SR08.mp4` |
| 예비 | SR09 | 강아지가 밖에서 짖어요 | `sentences/T1/SR09.mp4` |
| 예비 | SR10 | 할아버지께 인사했어요 | `sentences/T1/SR10.mp4` |
| 예비 | SR11 | 손톱을 짧게 깎았어요 | `sentences/T1/SR11.mp4` |
| 예비 | SR12 | 길에서 친구를 만났어요 | `sentences/T1/SR12.mp4` |

### 소음 속 문장 (72클립, 소리 필수)

| 폼 | 번호 | 대본 | 파일 |
|---|---|---|---|
| A | VA01 | 사이즈가 안 맞아요 | `av/T1/VA01.mp4` |
| A | VA02 | 귤이 정말 달아요 | `av/T1/VA02.mp4` |
| A | VA03 | 날씨가 많이 추워요 | `av/T1/VA03.mp4` |
| A | VA04 | 오후에 비가 그쳤어요 | `av/T1/VA04.mp4` |
| A | VA05 | 잠깐 쉬었다 해요 | `av/T1/VA05.mp4` |
| A | VA06 | 기다려 줘서 고마워요 | `av/T1/VA06.mp4` |
| A | VA07 | 라디오 소리가 작아요 | `av/T1/VA07.mp4` |
| A | VA08 | 이따가 연락할게요 | `av/T1/VA08.mp4` |
| A | VA09 | 이어폰을 놓고 왔어요 | `av/T1/VA09.mp4` |
| A | VA10 | 마스크를 쓰고 왔어요 | `av/T1/VA10.mp4` |
| A | VA11 | 배터리가 다 닳았어요 | `av/T1/VA11.mp4` |
| A | VA12 | 아이스크림이 녹았어요 | `av/T1/VA12.mp4` |
| A | VA13 | 택배가 아직 안 왔어요 | `av/T1/VA13.mp4` |
| A | VA14 | 손님이 많아서 바빠요 | `av/T1/VA14.mp4` |
| A | VA15 | 식당 예약을 바꿨어요 | `av/T1/VA15.mp4` |
| A | VA16 | 컴퓨터가 자꾸 꺼져요 | `av/T1/VA16.mp4` |
| A | VA17 | 학원 끝나고 갈게요 | `av/T1/VA17.mp4` |
| A | VA18 | 문자를 확인해 보세요 | `av/T1/VA18.mp4` |
| A | VA19 | 아빠가 출장을 가셨어요 | `av/T1/VA19.mp4` |
| A | VA20 | 간식을 조금 남겼어요 | `av/T1/VA20.mp4` |
| B | VB01 | 아이가 잠들었어요 | `av/T1/VB01.mp4` |
| B | VB02 | 같이 점심 먹어요 | `av/T1/VB02.mp4` |
| B | VB03 | 내일은 비가 온대요 | `av/T1/VB03.mp4` |
| B | VB04 | 오늘 수영장에 가요 | `av/T1/VB04.mp4` |
| B | VB05 | 전화를 안 받아요 | `av/T1/VB05.mp4` |
| B | VB06 | 국이 조금 싱거워요 | `av/T1/VB06.mp4` |
| B | VB07 | 방학이 곧 끝나요 | `av/T1/VB07.mp4` |
| B | VB08 | 연필 좀 빌려줘요 | `av/T1/VB08.mp4` |
| B | VB09 | 창밖에 눈이 내려요 | `av/T1/VB09.mp4` |
| B | VB10 | 길을 건너면 있어요 | `av/T1/VB10.mp4` |
| B | VB11 | 버스가 곧 도착해요 | `av/T1/VB11.mp4` |
| B | VB12 | 아까 보낸 메일 봤어요 | `av/T1/VB12.mp4` |
| B | VB13 | 기차표가 다 팔렸어요 | `av/T1/VB13.mp4` |
| B | VB14 | 버스를 잘못 탔어요 | `av/T1/VB14.mp4` |
| B | VB15 | 이번에는 제가 낼게요 | `av/T1/VB15.mp4` |
| B | VB16 | 축구 경기를 봤어요 | `av/T1/VB16.mp4` |
| B | VB17 | 회의가 늦게 끝났어요 | `av/T1/VB17.mp4` |
| B | VB18 | 주말에 등산을 갔어요 | `av/T1/VB18.mp4` |
| B | VB19 | 양말을 거꾸로 신었어요 | `av/T1/VB19.mp4` |
| B | VB20 | 편의점에서 빵을 샀어요 | `av/T1/VB20.mp4` |
| C | VC01 | 옷이 조금 커 보여요 | `av/T1/VC01.mp4` |
| C | VC02 | 감기약을 사 왔어요 | `av/T1/VC02.mp4` |
| C | VC03 | 병원 예약을 했어요 | `av/T1/VC03.mp4` |
| C | VC04 | 에어컨을 켜 줄래요 | `av/T1/VC04.mp4` |
| C | VC05 | 주차할 곳이 없어요 | `av/T1/VC05.mp4` |
| C | VC06 | 교복이 조금 작아요 | `av/T1/VC06.mp4` |
| C | VC07 | 빵이 아직 따뜻해요 | `av/T1/VC07.mp4` |
| C | VC08 | 연극을 보러 갔어요 | `av/T1/VC08.mp4` |
| C | VC09 | 휴일에도 일을 했어요 | `av/T1/VC09.mp4` |
| C | VC10 | 교실 불을 꺼 주세요 | `av/T1/VC10.mp4` |
| C | VC11 | 비행기가 늦게 떠요 | `av/T1/VC11.mp4` |
| C | VC12 | 시계가 조금 빨라요 | `av/T1/VC12.mp4` |
| C | VC13 | 냄새가 정말 좋아요 | `av/T1/VC13.mp4` |
| C | VC14 | 버스 카드를 찍으세요 | `av/T1/VC14.mp4` |
| C | VC15 | 저녁에 운동하러 가요 | `av/T1/VC15.mp4` |
| C | VC16 | 책을 두 권 빌렸어요 | `av/T1/VC16.mp4` |
| C | VC17 | 나머지는 내일 할게요 | `av/T1/VC17.mp4` |
| C | VC18 | 오늘 회의는 취소됐어요 | `av/T1/VC18.mp4` |
| C | VC19 | 재미있는 책을 읽었어요 | `av/T1/VC19.mp4` |
| C | VC20 | 주소를 다시 알려 주세요 | `av/T1/VC20.mp4` |
| 예비 | VR01 | 수영을 배우고 싶어요 | `av/T1/VR01.mp4` |
| 예비 | VR02 | 배가 너무 불러요 | `av/T1/VR02.mp4` |
| 예비 | VR03 | 화요일에 시간 있어요 | `av/T1/VR03.mp4` |
| 예비 | VR04 | 주스를 쏟고 말았어요 | `av/T1/VR04.mp4` |
| 예비 | VR05 | 책가방이 너무 커요 | `av/T1/VR05.mp4` |
| 예비 | VR06 | 동물원에 가 봤어요 | `av/T1/VR06.mp4` |
| 예비 | VR07 | 옆집 개가 짖어요 | `av/T1/VR07.mp4` |
| 예비 | VR08 | 목요일까지 끝낼게요 | `av/T1/VR08.mp4` |
| 예비 | VR09 | 키가 많이 컸네요 | `av/T1/VR09.mp4` |
| 예비 | VR10 | 밖이 벌써 어두워요 | `av/T1/VR10.mp4` |
| 예비 | VR11 | 피자를 시켜 먹었어요 | `av/T1/VR11.mp4` |
| 예비 | VR12 | 물병을 채워 왔어요 | `av/T1/VR12.mp4` |

### SNR 맞추기 문장 (24클립, 소리 필수)

| 폼 | 번호 | 대본 | 파일 |
|---|---|---|---|
| - | VK01 | 이번 역에서 내려요 | `av/T1/VK01.mp4` |
| - | VK02 | 컵을 깨뜨렸어요 | `av/T1/VK02.mp4` |
| - | VK03 | 사진이 잘 나왔어요 | `av/T1/VK03.mp4` |
| - | VK04 | 새 신발이 편해요 | `av/T1/VK04.mp4` |
| - | VK05 | 할 일이 너무 많아요 | `av/T1/VK05.mp4` |
| - | VK06 | 강의실이 너무 더워요 | `av/T1/VK06.mp4` |
| - | VK07 | 소리 좀 줄여 주세요 | `av/T1/VK07.mp4` |
| - | VK08 | 숙소를 예약했어요 | `av/T1/VK08.mp4` |
| - | VK09 | 거스름돈 여기 있어요 | `av/T1/VK09.mp4` |
| - | VK10 | 과일을 씻어서 먹어요 | `av/T1/VK10.mp4` |
| - | VK11 | 선물이 마음에 들어요 | `av/T1/VK11.mp4` |
| - | VK12 | 시간이 금방 갔어요 | `av/T1/VK12.mp4` |
| - | VK13 | 밤하늘에 별이 많아요 | `av/T1/VK13.mp4` |
| - | VK14 | 버스 정류장이 멀어요 | `av/T1/VK14.mp4` |
| - | VK15 | 지하철이 너무 붐벼요 | `av/T1/VK15.mp4` |
| - | VK16 | 차가 막혀서 늦었어요 | `av/T1/VK16.mp4` |
| - | VK17 | 동생이 피아노를 배워요 | `av/T1/VK17.mp4` |
| - | VK18 | 비밀번호를 잊었어요 | `av/T1/VK18.mp4` |
| - | VK19 | 저는 매운 걸 못 먹어요 | `av/T1/VK19.mp4` |
| - | VK20 | 주문하신 음료 나왔어요 | `av/T1/VK20.mp4` |
| - | VK21 | 나중에 다시 전화할게요 | `av/T1/VK21.mp4` |
| - | VK22 | 전기가 갑자기 나갔어요 | `av/T1/VK22.mp4` |
| - | VK23 | 휴대폰 충전이 필요해요 | `av/T1/VK23.mp4` |
| - | VK24 | 선생님께 칭찬받았어요 | `av/T1/VK24.mp4` |

## 화자 T2 (300클립)

### 실제 얼굴 낱말 (72클립, 소리 녹음만)

| 폼 | 번호 | 대본 | 파일 |
|---|---|---|---|
| A | A1 | 이 | `words/T2/A1.mp4` |
| A | A2 | 호피 | `words/T2/A2.mp4` |
| A | A3 | 기쁨 | `words/T2/A3.mp4` |
| A | A4 | 무지개 | `words/T2/A4.mp4` |
| A | A5 | 지붕 | `words/T2/A5.mp4` |
| A | A6 | 포차 | `words/T2/A6.mp4` |
| A | A7 | 가방 | `words/T2/A7.mp4` |
| A | A8 | 복 | `words/T2/A8.mp4` |
| A | A9 | 연못 | `words/T2/A9.mp4` |
| A | A10 | 삼촌 | `words/T2/A10.mp4` |
| A | A11 | 동무 | `words/T2/A11.mp4` |
| A | A12 | 세탁기 | `words/T2/A12.mp4` |
| A | A13 | 빨간 | `words/T2/A13.mp4` |
| A | A14 | 기린 | `words/T2/A14.mp4` |
| A | A15 | 가지 | `words/T2/A15.mp4` |
| A | A16 | 책상 | `words/T2/A16.mp4` |
| A | A17 | 공원 | `words/T2/A17.mp4` |
| A | A18 | 문 | `words/T2/A18.mp4` |
| A | A19 | 짐 | `words/T2/A19.mp4` |
| A | A20 | 장문 | `words/T2/A20.mp4` |
| A | A21 | 계란 | `words/T2/A21.mp4` |
| A | A22 | 폭소 | `words/T2/A22.mp4` |
| A | A23 | 칸 | `words/T2/A23.mp4` |
| A | A24 | 딸 | `words/T2/A24.mp4` |
| B | B1 | 우유 | `words/T2/B1.mp4` |
| B | B2 | 볶음밥 | `words/T2/B2.mp4` |
| B | B3 | 외로움 | `words/T2/B3.mp4` |
| B | B4 | 빗물 | `words/T2/B4.mp4` |
| B | B5 | 입술 | `words/T2/B5.mp4` |
| B | B6 | 파치 | `words/T2/B6.mp4` |
| B | B7 | 수박 | `words/T2/B7.mp4` |
| B | B8 | 숨 | `words/T2/B8.mp4` |
| B | B9 | 칠판 | `words/T2/B9.mp4` |
| B | B10 | 눈물 | `words/T2/B10.mp4` |
| B | B11 | 문제 | `words/T2/B11.mp4` |
| B | B12 | 하늘 | `words/T2/B12.mp4` |
| B | B13 | 발간 | `words/T2/B13.mp4` |
| B | B14 | 국자 | `words/T2/B14.mp4` |
| B | B15 | 가치 | `words/T2/B15.mp4` |
| B | B16 | 닭 | `words/T2/B16.mp4` |
| B | B17 | 수건 | `words/T2/B17.mp4` |
| B | B18 | 반 | `words/T2/B18.mp4` |
| B | B19 | 삼 | `words/T2/B19.mp4` |
| B | B20 | 토 | `words/T2/B20.mp4` |
| B | B21 | 계산 | `words/T2/B21.mp4` |
| B | B22 | 라면 | `words/T2/B22.mp4` |
| B | B23 | 간 | `words/T2/B23.mp4` |
| B | B24 | 돈 | `words/T2/B24.mp4` |
| C | C1 | 무 | `words/T2/C1.mp4` |
| C | C2 | 호미 | `words/T2/C2.mp4` |
| C | C3 | 램프 | `words/T2/C3.mp4` |
| C | C4 | 바가지 | `words/T2/C4.mp4` |
| C | C5 | 감자 | `words/T2/C5.mp4` |
| C | C6 | 나무 | `words/T2/C6.mp4` |
| C | C7 | 가망 | `words/T2/C7.mp4` |
| C | C8 | 목 | `words/T2/C8.mp4` |
| C | C9 | 가위 | `words/T2/C9.mp4` |
| C | C10 | 강물 | `words/T2/C10.mp4` |
| C | C11 | 농부 | `words/T2/C11.mp4` |
| C | C12 | 도시락 | `words/T2/C12.mp4` |
| C | C13 | 가늠 | `words/T2/C13.mp4` |
| C | C14 | 국수 | `words/T2/C14.mp4` |
| C | C15 | 까치 | `words/T2/C15.mp4` |
| C | C16 | 공책 | `words/T2/C16.mp4` |
| C | C17 | 손녀 | `words/T2/C17.mp4` |
| C | C18 | 남 | `words/T2/C18.mp4` |
| C | C19 | 납 | `words/T2/C19.mp4` |
| C | C20 | 작문 | `words/T2/C20.mp4` |
| C | C21 | 계단 | `words/T2/C21.mp4` |
| C | C22 | 그릇 | `words/T2/C22.mp4` |
| C | C23 | 갓 | `words/T2/C23.mp4` |
| C | C24 | 날 | `words/T2/C24.mp4` |

### 개방형 문장 (132클립, 소리 녹음만)

| 폼 | 번호 | 대본 | 파일 |
|---|---|---|---|
| A | SA01 | 감기에 걸렸어요 | `sentences/T2/SA01.mp4` |
| A | SA02 | 새 옷을 입어 봤어요 | `sentences/T2/SA02.mp4` |
| A | SA03 | 시계가 멈췄어요 | `sentences/T2/SA03.mp4` |
| A | SA04 | 무슨 일이 있었어요 | `sentences/T2/SA04.mp4` |
| A | SA05 | 물이 너무 뜨거워요 | `sentences/T2/SA05.mp4` |
| A | SA06 | 눈이 펑펑 내려요 | `sentences/T2/SA06.mp4` |
| A | SA07 | 선물을 받았어요 | `sentences/T2/SA07.mp4` |
| A | SA08 | 매일 걸어서 다녀요 | `sentences/T2/SA08.mp4` |
| A | SA09 | 시험을 잘 봤어요 | `sentences/T2/SA09.mp4` |
| A | SA10 | 창밖이 시끄러워요 | `sentences/T2/SA10.mp4` |
| A | SA11 | 잘 먹겠습니다 | `sentences/T2/SA11.mp4` |
| A | SA12 | 글씨가 너무 작아요 | `sentences/T2/SA12.mp4` |
| A | SA13 | 꽃이 활짝 피었어요 | `sentences/T2/SA13.mp4` |
| A | SA14 | 사진을 보내 주세요 | `sentences/T2/SA14.mp4` |
| A | SA15 | 열쇠를 찾고 있어요 | `sentences/T2/SA15.mp4` |
| A | SA16 | 여기 앉아도 괜찮아요 | `sentences/T2/SA16.mp4` |
| A | SA17 | 옷이 너무 작아졌어요 | `sentences/T2/SA17.mp4` |
| A | SA18 | 생선을 좋아하나요 | `sentences/T2/SA18.mp4` |
| A | SA19 | 소리가 잘 안 들려요 | `sentences/T2/SA19.mp4` |
| A | SA20 | 고기를 구워 먹었어요 | `sentences/T2/SA20.mp4` |
| A | SA21 | 그림을 그리고 있어요 | `sentences/T2/SA21.mp4` |
| A | SA22 | 아빠가 차를 고쳤어요 | `sentences/T2/SA22.mp4` |
| A | SA23 | 아침을 거르지 마세요 | `sentences/T2/SA23.mp4` |
| A | SA24 | 공을 멀리 던졌어요 | `sentences/T2/SA24.mp4` |
| A | SA25 | 기차가 곧 출발해요 | `sentences/T2/SA25.mp4` |
| A | SA26 | 냉장고에 넣어 두세요 | `sentences/T2/SA26.mp4` |
| A | SA27 | 노래를 부르고 싶어요 | `sentences/T2/SA27.mp4` |
| A | SA28 | 어제 늦게 잠들었어요 | `sentences/T2/SA28.mp4` |
| A | SA29 | 표를 미리 사 두었어요 | `sentences/T2/SA29.mp4` |
| A | SA30 | 내일 다시 연락할게요 | `sentences/T2/SA30.mp4` |
| A | SA31 | 늦어서 정말 미안해요 | `sentences/T2/SA31.mp4` |
| A | SA32 | 거울을 깨끗이 닦았어요 | `sentences/T2/SA32.mp4` |
| A | SA33 | 바다에 놀러 가고 싶어요 | `sentences/T2/SA33.mp4` |
| A | SA34 | 머리를 짧게 잘랐어요 | `sentences/T2/SA34.mp4` |
| A | SA35 | 설거지는 제가 할게요 | `sentences/T2/SA35.mp4` |
| A | SA36 | 저도 그렇게 생각해요 | `sentences/T2/SA36.mp4` |
| A | SA37 | 이번 주는 정말 바빠요 | `sentences/T2/SA37.mp4` |
| A | SA38 | 현관 앞에 상자가 있어요 | `sentences/T2/SA38.mp4` |
| A | SA39 | 저녁에 산책할까요 | `sentences/T2/SA39.mp4` |
| A | SA40 | 별이 반짝반짝 빛나요 | `sentences/T2/SA40.mp4` |
| B | SB01 | 같이 사진 찍어요 | `sentences/T2/SB01.mp4` |
| B | SB02 | 만나서 반가워요 | `sentences/T2/SB02.mp4` |
| B | SB03 | 책을 빌려 왔어요 | `sentences/T2/SB03.mp4` |
| B | SB04 | 기분이 아주 좋아요 | `sentences/T2/SB04.mp4` |
| B | SB05 | 화장실이 어디예요 | `sentences/T2/SB05.mp4` |
| B | SB06 | 금방 돌아올게요 | `sentences/T2/SB06.mp4` |
| B | SB07 | 고양이가 잠을 자요 | `sentences/T2/SB07.mp4` |
| B | SB08 | 다음 주에 또 만나요 | `sentences/T2/SB08.mp4` |
| B | SB09 | 바람이 많이 불어요 | `sentences/T2/SB09.mp4` |
| B | SB10 | 집에 손님이 왔어요 | `sentences/T2/SB10.mp4` |
| B | SB11 | 제 말 잘 들리세요 | `sentences/T2/SB11.mp4` |
| B | SB12 | 그 사람을 잘 알아요 | `sentences/T2/SB12.mp4` |
| B | SB13 | 화분에 물을 줬어요 | `sentences/T2/SB13.mp4` |
| B | SB14 | 사전을 찾아봤어요 | `sentences/T2/SB14.mp4` |
| B | SB15 | 반찬이 정말 많아요 | `sentences/T2/SB15.mp4` |
| B | SB16 | 병원에 가 봐야겠어요 | `sentences/T2/SB16.mp4` |
| B | SB17 | 왜 그렇게 웃고 있어요 | `sentences/T2/SB17.mp4` |
| B | SB18 | 비가 그칠 것 같아요 | `sentences/T2/SB18.mp4` |
| B | SB19 | 엄마한테 혼났어요 | `sentences/T2/SB19.mp4` |
| B | SB20 | 축구를 하러 나가요 | `sentences/T2/SB20.mp4` |
| B | SB21 | 길을 잃어서 헤맸어요 | `sentences/T2/SB21.mp4` |
| B | SB22 | 아기가 방긋 웃었어요 | `sentences/T2/SB22.mp4` |
| B | SB23 | 안경을 잃어버렸어요 | `sentences/T2/SB23.mp4` |
| B | SB24 | 해가 벌써 지고 있어요 | `sentences/T2/SB24.mp4` |
| B | SB25 | 문자를 보내 줄게요 | `sentences/T2/SB25.mp4` |
| B | SB26 | 운동화 끈이 풀렸어요 | `sentences/T2/SB26.mp4` |
| B | SB27 | 방이 생각보다 추워요 | `sentences/T2/SB27.mp4` |
| B | SB28 | 수업이 일찍 끝났어요 | `sentences/T2/SB28.mp4` |
| B | SB29 | 자전거를 타고 왔어요 | `sentences/T2/SB29.mp4` |
| B | SB30 | 일이 아직 많이 남았어요 | `sentences/T2/SB30.mp4` |
| B | SB31 | 동생과 같이 놀았어요 | `sentences/T2/SB31.mp4` |
| B | SB32 | 점심 먹으러 같이 가요 | `sentences/T2/SB32.mp4` |
| B | SB33 | 주말에 산에 올라갔어요 | `sentences/T2/SB33.mp4` |
| B | SB34 | 국이 조금 짠 것 같아요 | `sentences/T2/SB34.mp4` |
| B | SB35 | 시간이 정말 빨리 가요 | `sentences/T2/SB35.mp4` |
| B | SB36 | 모래성을 쌓았어요 | `sentences/T2/SB36.mp4` |
| B | SB37 | 방을 깨끗하게 치웠어요 | `sentences/T2/SB37.mp4` |
| B | SB38 | 학교 앞에서 기다릴게요 | `sentences/T2/SB38.mp4` |
| B | SB39 | 연필을 빌려줄 수 있어요 | `sentences/T2/SB39.mp4` |
| B | SB40 | 친구에게 편지를 썼어요 | `sentences/T2/SB40.mp4` |
| C | SC01 | 괜찮아질 거예요 | `sentences/T2/SC01.mp4` |
| C | SC02 | 길이 많이 막혀요 | `sentences/T2/SC02.mp4` |
| C | SC03 | 가을이 벌써 왔어요 | `sentences/T2/SC03.mp4` |
| C | SC04 | 겨울에는 눈이 와요 | `sentences/T2/SC04.mp4` |
| C | SC05 | 회의가 길어졌어요 | `sentences/T2/SC05.mp4` |
| C | SC06 | 걱정하지 마세요 | `sentences/T2/SC06.mp4` |
| C | SC07 | 너무 피곤해 보여요 | `sentences/T2/SC07.mp4` |
| C | SC08 | 다리가 조금 아파요 | `sentences/T2/SC08.mp4` |
| C | SC09 | 아침에 운동을 해요 | `sentences/T2/SC09.mp4` |
| C | SC10 | 지갑을 두고 왔어요 | `sentences/T2/SC10.mp4` |
| C | SC11 | 편지를 써 볼게요 | `sentences/T2/SC11.mp4` |
| C | SC12 | 과일을 깎아 줄게요 | `sentences/T2/SC12.mp4` |
| C | SC13 | 모자를 쓰고 나가요 | `sentences/T2/SC13.mp4` |
| C | SC14 | 빨래를 널어야 해요 | `sentences/T2/SC14.mp4` |
| C | SC15 | 줄넘기를 했어요 | `sentences/T2/SC15.mp4` |
| C | SC16 | 바둑을 배우고 있어요 | `sentences/T2/SC16.mp4` |
| C | SC17 | 그 노래 정말 좋아요 | `sentences/T2/SC17.mp4` |
| C | SC18 | 목도리가 따뜻해요 | `sentences/T2/SC18.mp4` |
| C | SC19 | 열심히 연습했어요 | `sentences/T2/SC19.mp4` |
| C | SC20 | 오늘은 일찍 잘게요 | `sentences/T2/SC20.mp4` |
| C | SC21 | 김치가 아주 맛있어요 | `sentences/T2/SC21.mp4` |
| C | SC22 | 동생이 많이 울었어요 | `sentences/T2/SC22.mp4` |
| C | SC23 | 오늘은 쉬는 날이에요 | `sentences/T2/SC23.mp4` |
| C | SC24 | 조용히 해 주시겠어요 | `sentences/T2/SC24.mp4` |
| C | SC25 | 주머니에 동전이 있어요 | `sentences/T2/SC25.mp4` |
| C | SC26 | 숙제를 다 끝냈어요 | `sentences/T2/SC26.mp4` |
| C | SC27 | 버섯을 볶아 먹었어요 | `sentences/T2/SC27.mp4` |
| C | SC28 | 그건 잘 모르겠어요 | `sentences/T2/SC28.mp4` |
| C | SC29 | 옆자리에 앉아도 될까요 | `sentences/T2/SC29.mp4` |
| C | SC30 | 옆집 아저씨가 오셨어요 | `sentences/T2/SC30.mp4` |
| C | SC31 | 선생님께 물어봤어요 | `sentences/T2/SC31.mp4` |
| C | SC32 | 장갑을 끼고 나가세요 | `sentences/T2/SC32.mp4` |
| C | SC33 | 지하철에 사람이 많아요 | `sentences/T2/SC33.mp4` |
| C | SC34 | 할머니 댁에 다녀왔어요 | `sentences/T2/SC34.mp4` |
| C | SC35 | 떡볶이가 너무 매워요 | `sentences/T2/SC35.mp4` |
| C | SC36 | 은행에 들렀다 갈게요 | `sentences/T2/SC36.mp4` |
| C | SC37 | 시장에서 사과를 샀어요 | `sentences/T2/SC37.mp4` |
| C | SC38 | 엄마가 저녁을 차렸어요 | `sentences/T2/SC38.mp4` |
| C | SC39 | 열이 조금 있는 것 같아요 | `sentences/T2/SC39.mp4` |
| C | SC40 | 오늘 저녁은 뭐 먹을까요 | `sentences/T2/SC40.mp4` |
| 예비 | SR01 | 냄비에 물이 끓어요 | `sentences/T2/SR01.mp4` |
| 예비 | SR02 | 오늘 많이 걸었어요 | `sentences/T2/SR02.mp4` |
| 예비 | SR03 | 동생이 키가 컸어요 | `sentences/T2/SR03.mp4` |
| 예비 | SR04 | 우체국에 다녀올게요 | `sentences/T2/SR04.mp4` |
| 예비 | SR05 | 신호등이 바뀌었어요 | `sentences/T2/SR05.mp4` |
| 예비 | SR06 | 목소리가 참 좋네요 | `sentences/T2/SR06.mp4` |
| 예비 | SR07 | 생일 정말 축하해요 | `sentences/T2/SR07.mp4` |
| 예비 | SR08 | 햇볕이 정말 따가워요 | `sentences/T2/SR08.mp4` |
| 예비 | SR09 | 강아지가 밖에서 짖어요 | `sentences/T2/SR09.mp4` |
| 예비 | SR10 | 할아버지께 인사했어요 | `sentences/T2/SR10.mp4` |
| 예비 | SR11 | 손톱을 짧게 깎았어요 | `sentences/T2/SR11.mp4` |
| 예비 | SR12 | 길에서 친구를 만났어요 | `sentences/T2/SR12.mp4` |

### 소음 속 문장 (72클립, 소리 필수)

| 폼 | 번호 | 대본 | 파일 |
|---|---|---|---|
| A | VA01 | 사이즈가 안 맞아요 | `av/T2/VA01.mp4` |
| A | VA02 | 귤이 정말 달아요 | `av/T2/VA02.mp4` |
| A | VA03 | 날씨가 많이 추워요 | `av/T2/VA03.mp4` |
| A | VA04 | 오후에 비가 그쳤어요 | `av/T2/VA04.mp4` |
| A | VA05 | 잠깐 쉬었다 해요 | `av/T2/VA05.mp4` |
| A | VA06 | 기다려 줘서 고마워요 | `av/T2/VA06.mp4` |
| A | VA07 | 라디오 소리가 작아요 | `av/T2/VA07.mp4` |
| A | VA08 | 이따가 연락할게요 | `av/T2/VA08.mp4` |
| A | VA09 | 이어폰을 놓고 왔어요 | `av/T2/VA09.mp4` |
| A | VA10 | 마스크를 쓰고 왔어요 | `av/T2/VA10.mp4` |
| A | VA11 | 배터리가 다 닳았어요 | `av/T2/VA11.mp4` |
| A | VA12 | 아이스크림이 녹았어요 | `av/T2/VA12.mp4` |
| A | VA13 | 택배가 아직 안 왔어요 | `av/T2/VA13.mp4` |
| A | VA14 | 손님이 많아서 바빠요 | `av/T2/VA14.mp4` |
| A | VA15 | 식당 예약을 바꿨어요 | `av/T2/VA15.mp4` |
| A | VA16 | 컴퓨터가 자꾸 꺼져요 | `av/T2/VA16.mp4` |
| A | VA17 | 학원 끝나고 갈게요 | `av/T2/VA17.mp4` |
| A | VA18 | 문자를 확인해 보세요 | `av/T2/VA18.mp4` |
| A | VA19 | 아빠가 출장을 가셨어요 | `av/T2/VA19.mp4` |
| A | VA20 | 간식을 조금 남겼어요 | `av/T2/VA20.mp4` |
| B | VB01 | 아이가 잠들었어요 | `av/T2/VB01.mp4` |
| B | VB02 | 같이 점심 먹어요 | `av/T2/VB02.mp4` |
| B | VB03 | 내일은 비가 온대요 | `av/T2/VB03.mp4` |
| B | VB04 | 오늘 수영장에 가요 | `av/T2/VB04.mp4` |
| B | VB05 | 전화를 안 받아요 | `av/T2/VB05.mp4` |
| B | VB06 | 국이 조금 싱거워요 | `av/T2/VB06.mp4` |
| B | VB07 | 방학이 곧 끝나요 | `av/T2/VB07.mp4` |
| B | VB08 | 연필 좀 빌려줘요 | `av/T2/VB08.mp4` |
| B | VB09 | 창밖에 눈이 내려요 | `av/T2/VB09.mp4` |
| B | VB10 | 길을 건너면 있어요 | `av/T2/VB10.mp4` |
| B | VB11 | 버스가 곧 도착해요 | `av/T2/VB11.mp4` |
| B | VB12 | 아까 보낸 메일 봤어요 | `av/T2/VB12.mp4` |
| B | VB13 | 기차표가 다 팔렸어요 | `av/T2/VB13.mp4` |
| B | VB14 | 버스를 잘못 탔어요 | `av/T2/VB14.mp4` |
| B | VB15 | 이번에는 제가 낼게요 | `av/T2/VB15.mp4` |
| B | VB16 | 축구 경기를 봤어요 | `av/T2/VB16.mp4` |
| B | VB17 | 회의가 늦게 끝났어요 | `av/T2/VB17.mp4` |
| B | VB18 | 주말에 등산을 갔어요 | `av/T2/VB18.mp4` |
| B | VB19 | 양말을 거꾸로 신었어요 | `av/T2/VB19.mp4` |
| B | VB20 | 편의점에서 빵을 샀어요 | `av/T2/VB20.mp4` |
| C | VC01 | 옷이 조금 커 보여요 | `av/T2/VC01.mp4` |
| C | VC02 | 감기약을 사 왔어요 | `av/T2/VC02.mp4` |
| C | VC03 | 병원 예약을 했어요 | `av/T2/VC03.mp4` |
| C | VC04 | 에어컨을 켜 줄래요 | `av/T2/VC04.mp4` |
| C | VC05 | 주차할 곳이 없어요 | `av/T2/VC05.mp4` |
| C | VC06 | 교복이 조금 작아요 | `av/T2/VC06.mp4` |
| C | VC07 | 빵이 아직 따뜻해요 | `av/T2/VC07.mp4` |
| C | VC08 | 연극을 보러 갔어요 | `av/T2/VC08.mp4` |
| C | VC09 | 휴일에도 일을 했어요 | `av/T2/VC09.mp4` |
| C | VC10 | 교실 불을 꺼 주세요 | `av/T2/VC10.mp4` |
| C | VC11 | 비행기가 늦게 떠요 | `av/T2/VC11.mp4` |
| C | VC12 | 시계가 조금 빨라요 | `av/T2/VC12.mp4` |
| C | VC13 | 냄새가 정말 좋아요 | `av/T2/VC13.mp4` |
| C | VC14 | 버스 카드를 찍으세요 | `av/T2/VC14.mp4` |
| C | VC15 | 저녁에 운동하러 가요 | `av/T2/VC15.mp4` |
| C | VC16 | 책을 두 권 빌렸어요 | `av/T2/VC16.mp4` |
| C | VC17 | 나머지는 내일 할게요 | `av/T2/VC17.mp4` |
| C | VC18 | 오늘 회의는 취소됐어요 | `av/T2/VC18.mp4` |
| C | VC19 | 재미있는 책을 읽었어요 | `av/T2/VC19.mp4` |
| C | VC20 | 주소를 다시 알려 주세요 | `av/T2/VC20.mp4` |
| 예비 | VR01 | 수영을 배우고 싶어요 | `av/T2/VR01.mp4` |
| 예비 | VR02 | 배가 너무 불러요 | `av/T2/VR02.mp4` |
| 예비 | VR03 | 화요일에 시간 있어요 | `av/T2/VR03.mp4` |
| 예비 | VR04 | 주스를 쏟고 말았어요 | `av/T2/VR04.mp4` |
| 예비 | VR05 | 책가방이 너무 커요 | `av/T2/VR05.mp4` |
| 예비 | VR06 | 동물원에 가 봤어요 | `av/T2/VR06.mp4` |
| 예비 | VR07 | 옆집 개가 짖어요 | `av/T2/VR07.mp4` |
| 예비 | VR08 | 목요일까지 끝낼게요 | `av/T2/VR08.mp4` |
| 예비 | VR09 | 키가 많이 컸네요 | `av/T2/VR09.mp4` |
| 예비 | VR10 | 밖이 벌써 어두워요 | `av/T2/VR10.mp4` |
| 예비 | VR11 | 피자를 시켜 먹었어요 | `av/T2/VR11.mp4` |
| 예비 | VR12 | 물병을 채워 왔어요 | `av/T2/VR12.mp4` |

### SNR 맞추기 문장 (24클립, 소리 필수)

| 폼 | 번호 | 대본 | 파일 |
|---|---|---|---|
| - | VK01 | 이번 역에서 내려요 | `av/T2/VK01.mp4` |
| - | VK02 | 컵을 깨뜨렸어요 | `av/T2/VK02.mp4` |
| - | VK03 | 사진이 잘 나왔어요 | `av/T2/VK03.mp4` |
| - | VK04 | 새 신발이 편해요 | `av/T2/VK04.mp4` |
| - | VK05 | 할 일이 너무 많아요 | `av/T2/VK05.mp4` |
| - | VK06 | 강의실이 너무 더워요 | `av/T2/VK06.mp4` |
| - | VK07 | 소리 좀 줄여 주세요 | `av/T2/VK07.mp4` |
| - | VK08 | 숙소를 예약했어요 | `av/T2/VK08.mp4` |
| - | VK09 | 거스름돈 여기 있어요 | `av/T2/VK09.mp4` |
| - | VK10 | 과일을 씻어서 먹어요 | `av/T2/VK10.mp4` |
| - | VK11 | 선물이 마음에 들어요 | `av/T2/VK11.mp4` |
| - | VK12 | 시간이 금방 갔어요 | `av/T2/VK12.mp4` |
| - | VK13 | 밤하늘에 별이 많아요 | `av/T2/VK13.mp4` |
| - | VK14 | 버스 정류장이 멀어요 | `av/T2/VK14.mp4` |
| - | VK15 | 지하철이 너무 붐벼요 | `av/T2/VK15.mp4` |
| - | VK16 | 차가 막혀서 늦었어요 | `av/T2/VK16.mp4` |
| - | VK17 | 동생이 피아노를 배워요 | `av/T2/VK17.mp4` |
| - | VK18 | 비밀번호를 잊었어요 | `av/T2/VK18.mp4` |
| - | VK19 | 저는 매운 걸 못 먹어요 | `av/T2/VK19.mp4` |
| - | VK20 | 주문하신 음료 나왔어요 | `av/T2/VK20.mp4` |
| - | VK21 | 나중에 다시 전화할게요 | `av/T2/VK21.mp4` |
| - | VK22 | 전기가 갑자기 나갔어요 | `av/T2/VK22.mp4` |
| - | VK23 | 휴대폰 충전이 필요해요 | `av/T2/VK23.mp4` |
| - | VK24 | 선생님께 칭찬받았어요 | `av/T2/VK24.mp4` |

## 화자 T3 (72클립)

### 실제 얼굴 낱말 (72클립, 소리 녹음만)

| 폼 | 번호 | 대본 | 파일 |
|---|---|---|---|
| A | A1 | 이 | `words/T3/A1.mp4` |
| A | A2 | 호피 | `words/T3/A2.mp4` |
| A | A3 | 기쁨 | `words/T3/A3.mp4` |
| A | A4 | 무지개 | `words/T3/A4.mp4` |
| A | A5 | 지붕 | `words/T3/A5.mp4` |
| A | A6 | 포차 | `words/T3/A6.mp4` |
| A | A7 | 가방 | `words/T3/A7.mp4` |
| A | A8 | 복 | `words/T3/A8.mp4` |
| A | A9 | 연못 | `words/T3/A9.mp4` |
| A | A10 | 삼촌 | `words/T3/A10.mp4` |
| A | A11 | 동무 | `words/T3/A11.mp4` |
| A | A12 | 세탁기 | `words/T3/A12.mp4` |
| A | A13 | 빨간 | `words/T3/A13.mp4` |
| A | A14 | 기린 | `words/T3/A14.mp4` |
| A | A15 | 가지 | `words/T3/A15.mp4` |
| A | A16 | 책상 | `words/T3/A16.mp4` |
| A | A17 | 공원 | `words/T3/A17.mp4` |
| A | A18 | 문 | `words/T3/A18.mp4` |
| A | A19 | 짐 | `words/T3/A19.mp4` |
| A | A20 | 장문 | `words/T3/A20.mp4` |
| A | A21 | 계란 | `words/T3/A21.mp4` |
| A | A22 | 폭소 | `words/T3/A22.mp4` |
| A | A23 | 칸 | `words/T3/A23.mp4` |
| A | A24 | 딸 | `words/T3/A24.mp4` |
| B | B1 | 우유 | `words/T3/B1.mp4` |
| B | B2 | 볶음밥 | `words/T3/B2.mp4` |
| B | B3 | 외로움 | `words/T3/B3.mp4` |
| B | B4 | 빗물 | `words/T3/B4.mp4` |
| B | B5 | 입술 | `words/T3/B5.mp4` |
| B | B6 | 파치 | `words/T3/B6.mp4` |
| B | B7 | 수박 | `words/T3/B7.mp4` |
| B | B8 | 숨 | `words/T3/B8.mp4` |
| B | B9 | 칠판 | `words/T3/B9.mp4` |
| B | B10 | 눈물 | `words/T3/B10.mp4` |
| B | B11 | 문제 | `words/T3/B11.mp4` |
| B | B12 | 하늘 | `words/T3/B12.mp4` |
| B | B13 | 발간 | `words/T3/B13.mp4` |
| B | B14 | 국자 | `words/T3/B14.mp4` |
| B | B15 | 가치 | `words/T3/B15.mp4` |
| B | B16 | 닭 | `words/T3/B16.mp4` |
| B | B17 | 수건 | `words/T3/B17.mp4` |
| B | B18 | 반 | `words/T3/B18.mp4` |
| B | B19 | 삼 | `words/T3/B19.mp4` |
| B | B20 | 토 | `words/T3/B20.mp4` |
| B | B21 | 계산 | `words/T3/B21.mp4` |
| B | B22 | 라면 | `words/T3/B22.mp4` |
| B | B23 | 간 | `words/T3/B23.mp4` |
| B | B24 | 돈 | `words/T3/B24.mp4` |
| C | C1 | 무 | `words/T3/C1.mp4` |
| C | C2 | 호미 | `words/T3/C2.mp4` |
| C | C3 | 램프 | `words/T3/C3.mp4` |
| C | C4 | 바가지 | `words/T3/C4.mp4` |
| C | C5 | 감자 | `words/T3/C5.mp4` |
| C | C6 | 나무 | `words/T3/C6.mp4` |
| C | C7 | 가망 | `words/T3/C7.mp4` |
| C | C8 | 목 | `words/T3/C8.mp4` |
| C | C9 | 가위 | `words/T3/C9.mp4` |
| C | C10 | 강물 | `words/T3/C10.mp4` |
| C | C11 | 농부 | `words/T3/C11.mp4` |
| C | C12 | 도시락 | `words/T3/C12.mp4` |
| C | C13 | 가늠 | `words/T3/C13.mp4` |
| C | C14 | 국수 | `words/T3/C14.mp4` |
| C | C15 | 까치 | `words/T3/C15.mp4` |
| C | C16 | 공책 | `words/T3/C16.mp4` |
| C | C17 | 손녀 | `words/T3/C17.mp4` |
| C | C18 | 남 | `words/T3/C18.mp4` |
| C | C19 | 납 | `words/T3/C19.mp4` |
| C | C20 | 작문 | `words/T3/C20.mp4` |
| C | C21 | 계단 | `words/T3/C21.mp4` |
| C | C22 | 그릇 | `words/T3/C22.mp4` |
| C | C23 | 갓 | `words/T3/C23.mp4` |
| C | C24 | 날 | `words/T3/C24.mp4` |

## 화자 T4 (72클립)

### 실제 얼굴 낱말 (72클립, 소리 녹음만)

| 폼 | 번호 | 대본 | 파일 |
|---|---|---|---|
| A | A1 | 이 | `words/T4/A1.mp4` |
| A | A2 | 호피 | `words/T4/A2.mp4` |
| A | A3 | 기쁨 | `words/T4/A3.mp4` |
| A | A4 | 무지개 | `words/T4/A4.mp4` |
| A | A5 | 지붕 | `words/T4/A5.mp4` |
| A | A6 | 포차 | `words/T4/A6.mp4` |
| A | A7 | 가방 | `words/T4/A7.mp4` |
| A | A8 | 복 | `words/T4/A8.mp4` |
| A | A9 | 연못 | `words/T4/A9.mp4` |
| A | A10 | 삼촌 | `words/T4/A10.mp4` |
| A | A11 | 동무 | `words/T4/A11.mp4` |
| A | A12 | 세탁기 | `words/T4/A12.mp4` |
| A | A13 | 빨간 | `words/T4/A13.mp4` |
| A | A14 | 기린 | `words/T4/A14.mp4` |
| A | A15 | 가지 | `words/T4/A15.mp4` |
| A | A16 | 책상 | `words/T4/A16.mp4` |
| A | A17 | 공원 | `words/T4/A17.mp4` |
| A | A18 | 문 | `words/T4/A18.mp4` |
| A | A19 | 짐 | `words/T4/A19.mp4` |
| A | A20 | 장문 | `words/T4/A20.mp4` |
| A | A21 | 계란 | `words/T4/A21.mp4` |
| A | A22 | 폭소 | `words/T4/A22.mp4` |
| A | A23 | 칸 | `words/T4/A23.mp4` |
| A | A24 | 딸 | `words/T4/A24.mp4` |
| B | B1 | 우유 | `words/T4/B1.mp4` |
| B | B2 | 볶음밥 | `words/T4/B2.mp4` |
| B | B3 | 외로움 | `words/T4/B3.mp4` |
| B | B4 | 빗물 | `words/T4/B4.mp4` |
| B | B5 | 입술 | `words/T4/B5.mp4` |
| B | B6 | 파치 | `words/T4/B6.mp4` |
| B | B7 | 수박 | `words/T4/B7.mp4` |
| B | B8 | 숨 | `words/T4/B8.mp4` |
| B | B9 | 칠판 | `words/T4/B9.mp4` |
| B | B10 | 눈물 | `words/T4/B10.mp4` |
| B | B11 | 문제 | `words/T4/B11.mp4` |
| B | B12 | 하늘 | `words/T4/B12.mp4` |
| B | B13 | 발간 | `words/T4/B13.mp4` |
| B | B14 | 국자 | `words/T4/B14.mp4` |
| B | B15 | 가치 | `words/T4/B15.mp4` |
| B | B16 | 닭 | `words/T4/B16.mp4` |
| B | B17 | 수건 | `words/T4/B17.mp4` |
| B | B18 | 반 | `words/T4/B18.mp4` |
| B | B19 | 삼 | `words/T4/B19.mp4` |
| B | B20 | 토 | `words/T4/B20.mp4` |
| B | B21 | 계산 | `words/T4/B21.mp4` |
| B | B22 | 라면 | `words/T4/B22.mp4` |
| B | B23 | 간 | `words/T4/B23.mp4` |
| B | B24 | 돈 | `words/T4/B24.mp4` |
| C | C1 | 무 | `words/T4/C1.mp4` |
| C | C2 | 호미 | `words/T4/C2.mp4` |
| C | C3 | 램프 | `words/T4/C3.mp4` |
| C | C4 | 바가지 | `words/T4/C4.mp4` |
| C | C5 | 감자 | `words/T4/C5.mp4` |
| C | C6 | 나무 | `words/T4/C6.mp4` |
| C | C7 | 가망 | `words/T4/C7.mp4` |
| C | C8 | 목 | `words/T4/C8.mp4` |
| C | C9 | 가위 | `words/T4/C9.mp4` |
| C | C10 | 강물 | `words/T4/C10.mp4` |
| C | C11 | 농부 | `words/T4/C11.mp4` |
| C | C12 | 도시락 | `words/T4/C12.mp4` |
| C | C13 | 가늠 | `words/T4/C13.mp4` |
| C | C14 | 국수 | `words/T4/C14.mp4` |
| C | C15 | 까치 | `words/T4/C15.mp4` |
| C | C16 | 공책 | `words/T4/C16.mp4` |
| C | C17 | 손녀 | `words/T4/C17.mp4` |
| C | C18 | 남 | `words/T4/C18.mp4` |
| C | C19 | 납 | `words/T4/C19.mp4` |
| C | C20 | 작문 | `words/T4/C20.mp4` |
| C | C21 | 계단 | `words/T4/C21.mp4` |
| C | C22 | 그릇 | `words/T4/C22.mp4` |
| C | C23 | 갓 | `words/T4/C23.mp4` |
| C | C24 | 날 | `words/T4/C24.mp4` |

## 합계

전체 744클립: 실제 얼굴 낱말 288, 개방형 문장 264, 소음 속 문장 144, SNR 맞추기 문장 48.
잡담 잡음 파일 `noise/babble.wav`(8명 이상 섞은 모노 48kHz) 하나가 따로 필요하다.
