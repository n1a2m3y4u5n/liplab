"""청인 예비 파일럿(P3) 검사 목록 파일 만들기(docs/pilot/battery.md).

backend/data/pilot/battery_manifest.json을 만든다. 이미 있으면 덮어쓰지 않는다(--force). 촬영 목록을 동결한 뒤에는
이 스크립트를 다시 돌리지 않고 목록 파일을 직접 고친 다음 version을 올린다.

- 실제 얼굴 낱말: 폼 A·B는 동결 표준검사 v2(촬영 키트 48낱말) 그대로, 폼 C는 난이도를 맞춰 새로 고른다(pilot_battery.build_word_form_c).
- 개방형 문장: 폼 배정은 FORM_SENTENCES에 적어 둔다(10/6 초안을 음소 수 뱀 순서로 나눈 뒤 10/7 내용 1차 검토
  docs/review/pilot-sentences.tsv의 교체를 반영한 것). 모든 문장이 조건(6~10음절, 채점 음소 14~26, 숫자·영문 없음, 검사 낱말을 쓰지
  않음)과 유사도 점검(similarity_reasons: 훈련 문장, 같은 폼·다른 폼의 검사 문장과 너무 가깝지 않음)을 통과해야 목록을 쓴다.
  예비 문장은 후보 문장(CANDIDATES) 가운데 같은 점검을 모두 통과한 것에서 음소 수가 고르게 고른다. 문장은 촬영 전에 사람이 검토해
  동결한다.
- 무의미 낱말: 짝 맞추기 학습(C10, backend/nonsense_words.py)이 남겨 둔 두 목록을 폼 A·B로, 같은 생성기로 하나 더 만든 목록을
  폼 C로 쓴다(pilot_battery.nonsense_forms). 학습 목록 48낱말과 겹치지 않는다.
- 소음 속 문장·SNR 계단 문장: 문장과 음성이 촬영 뒤에 정해지므로 자리만 만든다(text, speech_rms_dbfs가 null).

    python3 scripts/build_pilot_manifest.py            # 만들기(있으면 멈춤)
    python3 scripts/build_pilot_manifest.py --force    # 다시 만들기
    python3 scripts/build_pilot_manifest.py --check    # 폼 문장 점검 결과와 후보 문장이 걸러진 사유만 보기
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "backend")
sys.path.insert(0, BACKEND)

import pilot_battery as pb  # noqa: E402

WORD_C_SEED = 20261006
N_SENTENCE = 40
N_RESERVE = 12
N_AV = 20
N_SNR = 24

# 개방형 문장 후보(초안, 2026-10-06). 일상 대화 문장, 6~10음절, 숫자·외래어 없음. 촬영 전에 사람이 검토해 바꿀 수 있다.
# '새 옷을 입어 봤어요'부터 일곱은 10/7 내용 1차 검토가 제안한 새 문장 다섯과 고친 문장 둘(제 말 잘 들리세요, 선생님께
# 물어봤어요)이다. '엄마한테 혼났어요'부터 스물넷은 같은 날 유사도 점검으로 교체 자리 둘과 예비 12개가 모자라 Claude Code가 더 쓴
# 문장이다(모든 점검과 경계 점검을 통과한 것만 남김, 사람 검토 전).
CANDIDATES = """
오늘 날씨가 참 좋네요
내일 아침에 일찍 만나요
점심 먹으러 같이 가요
창문 좀 열어 주세요
물 한 잔 마시고 싶어요
어제 늦게 잠들었어요
주말에 산에 올라갔어요
손을 깨끗이 씻으세요
엄마가 저녁을 차렸어요
동생이 많이 울었어요
친구랑 영화를 봤어요
길이 많이 막혀요
오늘은 일찍 잘게요
고양이가 잠을 자요
강아지가 짖어요
숙제를 다 끝냈어요
방을 깨끗하게 치웠어요
밥을 천천히 먹어요
바람이 많이 불어요
비가 그칠 것 같아요
눈이 펑펑 내려요
시장에서 사과를 샀어요
할머니 댁에 다녀왔어요
아빠가 차를 고쳤어요
다리가 좀 아파요
머리를 짧게 잘랐어요
신발을 새로 샀어요
옷이 너무 작아요
조용히 해 주세요
천천히 말해 주세요
다시 한번 말해 줄래요
지금 몇 시예요
화장실이 어디예요
여기 앉아도 돼요
같이 사진 찍어요
배가 너무 고파요
목이 너무 말라요
학교 앞에서 기다릴게요
선생님께 여쭤봤어요
수업이 일찍 끝났어요
시험을 잘 봤어요
책을 빌려 왔어요
그 노래 정말 좋아요
기차가 곧 출발해요
우산을 챙겨 가세요
감기에 걸렸어요
약을 먹고 푹 쉬세요
병원에 가 봐야겠어요
열이 조금 나요
이불을 덮고 자요
불 좀 꺼 주세요
냉장고에 넣어 두세요
설거지는 제가 할게요
빨래를 널어야 해요
쓰레기를 버려 주세요
화분에 물을 줬어요
꽃이 활짝 피었어요
나무 그늘에서 쉬어요
바다에 놀러 가고 싶어요
모래성을 쌓았어요
별이 반짝반짝 빛나요
달이 참 밝네요
해가 지고 있어요
아침에 운동을 해요
매일 걸어서 다녀요
자전거를 타고 왔어요
지하철에 사람이 많아요
표를 미리 사 두었어요
늦어서 정말 미안해요
도와줘서 고마워요
만나서 반가워요
다음에 또 만나요
조심히 들어가세요
잘 먹겠습니다
맛있게 드세요
국이 조금 짠 것 같아요
김치가 아주 맛있어요
고기를 구워 먹었어요
생선을 좋아하나요
과일을 깎아 줄게요
떡볶이가 너무 매워요
국수를 먹으러 가요
물이 너무 뜨거워요
방이 좀 추워요
창밖이 시끄러워요
전화가 안 돼요
문자를 보내 줄게요
사진을 보내 주세요
이름이 뭐예요
어디에 사세요
무슨 일 있어요
왜 그렇게 웃어요
기분이 아주 좋아요
너무 피곤해 보여요
걱정하지 마세요
괜찮아질 거예요
저도 그렇게 생각해요
그건 잘 모르겠어요
생일 축하해요
선물을 받았어요
편지를 써 볼게요
그림을 그리고 있어요
노래를 부르고 싶어요
춤을 잘 추네요
바둑을 배우고 있어요
축구를 하러 나가요
공을 멀리 던졌어요
줄넘기를 했어요
땀이 많이 나요
손이 차가워요
발이 너무 아파요
안경을 잃어버렸어요
열쇠를 찾고 있어요
지갑을 두고 왔어요
시계가 멈췄어요
모자를 쓰고 나가요
장갑을 끼세요
목도리가 따뜻해요
이제 집에 갈게요
집에 손님이 왔어요
아기가 웃고 있어요
동네를 천천히 걸었어요
옆집 아저씨가 오셨어요
계단으로 올라가요
현관 앞에 상자가 있어요
의자에 앉으세요
거울을 닦았어요
불이 꺼져 있어요
오늘은 쉬는 날이에요
일이 너무 많아요
회의가 길어졌어요
내일 다시 올게요
잠깐만 기다려 주세요
금방 돌아올게요
어서 들어오세요
많이 기다렸지요
소리가 잘 안 들려요
글씨가 너무 작아요
사전을 찾아봤어요
그 사람을 알아요
저녁에 산책할까요
가을이 오고 있어요
겨울에는 눈이 와요
머리가 조금 아파요
엄마랑 시장에 갔어요
친구에게 편지를 썼어요
아침을 거르지 마세요
밤에 잠이 안 와요
동생과 같이 놀았어요
강아지가 밖에서 짖어요
다리가 조금 아파요
옷이 너무 작아졌어요
조용히 해 주시겠어요
여기 앉아도 괜찮아요
배가 많이 고파요
열이 조금 있는 것 같아요
해가 벌써 지고 있어요
다음 주에 또 만나요
맛있게 많이 드세요
방이 생각보다 추워요
전화가 잘 안 들려요
무슨 일이 있었어요
왜 그렇게 웃고 있어요
생일 정말 축하해요
땀이 많이 났어요
손이 너무 차가워요
장갑을 끼고 나가세요
아기가 방긋 웃었어요
거울을 깨끗이 닦았어요
일이 아직 많이 남았어요
내일 다시 연락할게요
그 사람을 잘 알아요
가을이 벌써 왔어요
밤에 잠이 잘 안 와요
버섯을 볶아 먹었어요
엄마가 빨래를 개고 있어요
아이들이 운동장에서 놀아요
길을 잃어서 헤맸어요
은행에 들렀다 갈게요
시간이 정말 빨리 가요
옆자리에 앉아도 될까요
내 말 잘 들리세요
연필을 빌려줄 수 있어요
오늘 저녁은 뭐 먹을까요
감자를 삶아 먹었어요
할아버지가 낮잠을 주무세요
동생이 감기에 걸렸어요
날씨가 갑자기 추워졌어요
새 옷을 입어 봤어요
이번 주는 정말 바빠요
반찬이 정말 많아요
운동화 끈이 풀렸어요
주머니에 동전이 있어요
제 말 잘 들리세요
선생님께 물어봤어요
엄마한테 혼났어요
열심히 연습했어요
나뭇잎이 떨어져요
냄비에 물이 끓어요
버스가 늦게 왔어요
오늘 많이 걸었어요
동생이 키가 컸어요
방학이 곧 끝나요
옷에 얼룩이 묻었어요
우체국에 다녀올게요
고모가 놀러 오셨어요
신호등이 바뀌었어요
어깨가 너무 뻐근해요
목소리가 참 좋네요
빵을 맛있게 구웠어요
고양이를 쓰다듬었어요
그 영화 정말 재밌어요
할아버지께 인사했어요
햇볕이 정말 따가워요
휴지 좀 가져다줄래요
강아지랑 산책했어요
손톱을 짧게 깎았어요
숟가락을 떨어뜨렸어요
길에서 친구를 만났어요
"""

_PARTICLES = ("", "을", "를", "이", "가", "은", "는", "도", "에", "에서", "으로", "로", "만", "과", "와", "랑", "이랑", "의")


# 개방형 문장 폼 배정(2026-10-07). 10/6 초안(후보를 음소 수 뱀 순서로 나눈 것)의 자리를 그대로 두고, 내용 1차 검토
# (docs/review/pilot-sentences.tsv, README 3.4절)의 교체 16자리와 유사도 점검이 더 찾은 2자리(SB19, SC19)를 바꿨다. 자리 번호는
# 목록 순서대로 S{폼}01~40이다. 바꾼 자리와 까닭은 docs/pilot/battery.md 8.1절.
FORM_SENTENCES = {
    "A": [
        "감기에 걸렸어요", "새 옷을 입어 봤어요", "시계가 멈췄어요", "무슨 일이 있었어요", "물이 너무 뜨거워요",
        "눈이 펑펑 내려요", "선물을 받았어요", "매일 걸어서 다녀요", "시험을 잘 봤어요", "창밖이 시끄러워요",
        "잘 먹겠습니다", "글씨가 너무 작아요", "꽃이 활짝 피었어요", "사진을 보내 주세요", "열쇠를 찾고 있어요",
        "여기 앉아도 괜찮아요", "옷이 너무 작아졌어요", "생선을 좋아하나요", "소리가 잘 안 들려요", "고기를 구워 먹었어요",
        "그림을 그리고 있어요", "아빠가 차를 고쳤어요", "아침을 거르지 마세요", "공을 멀리 던졌어요", "기차가 곧 출발해요",
        "냉장고에 넣어 두세요", "노래를 부르고 싶어요", "어제 늦게 잠들었어요", "표를 미리 사 두었어요", "내일 다시 연락할게요",
        "늦어서 정말 미안해요", "거울을 깨끗이 닦았어요", "바다에 놀러 가고 싶어요", "머리를 짧게 잘랐어요", "설거지는 제가 할게요",
        "저도 그렇게 생각해요", "이번 주는 정말 바빠요", "현관 앞에 상자가 있어요", "저녁에 산책할까요", "별이 반짝반짝 빛나요",
    ],
    "B": [
        "같이 사진 찍어요", "만나서 반가워요", "책을 빌려 왔어요", "기분이 아주 좋아요", "화장실이 어디예요",
        "금방 돌아올게요", "고양이가 잠을 자요", "다음 주에 또 만나요", "바람이 많이 불어요", "집에 손님이 왔어요",
        "제 말 잘 들리세요", "그 사람을 잘 알아요", "화분에 물을 줬어요", "사전을 찾아봤어요", "반찬이 정말 많아요",
        "병원에 가 봐야겠어요", "왜 그렇게 웃고 있어요", "비가 그칠 것 같아요", "엄마한테 혼났어요", "축구를 하러 나가요",
        "길을 잃어서 헤맸어요", "아기가 방긋 웃었어요", "안경을 잃어버렸어요", "해가 벌써 지고 있어요", "문자를 보내 줄게요",
        "운동화 끈이 풀렸어요", "방이 생각보다 추워요", "수업이 일찍 끝났어요", "자전거를 타고 왔어요", "일이 아직 많이 남았어요",
        "동생과 같이 놀았어요", "점심 먹으러 같이 가요", "주말에 산에 올라갔어요", "국이 조금 짠 것 같아요", "시간이 정말 빨리 가요",
        "모래성을 쌓았어요", "방을 깨끗하게 치웠어요", "학교 앞에서 기다릴게요", "연필을 빌려줄 수 있어요", "친구에게 편지를 썼어요",
    ],
    "C": [
        "괜찮아질 거예요", "길이 많이 막혀요", "가을이 벌써 왔어요", "겨울에는 눈이 와요", "회의가 길어졌어요",
        "걱정하지 마세요", "너무 피곤해 보여요", "다리가 조금 아파요", "아침에 운동을 해요", "지갑을 두고 왔어요",
        "편지를 써 볼게요", "과일을 깎아 줄게요", "모자를 쓰고 나가요", "빨래를 널어야 해요", "줄넘기를 했어요",
        "바둑을 배우고 있어요", "그 노래 정말 좋아요", "목도리가 따뜻해요", "열심히 연습했어요", "오늘은 일찍 잘게요",
        "김치가 아주 맛있어요", "동생이 많이 울었어요", "오늘은 쉬는 날이에요", "조용히 해 주시겠어요", "주머니에 동전이 있어요",
        "숙제를 다 끝냈어요", "버섯을 볶아 먹었어요", "그건 잘 모르겠어요", "옆자리에 앉아도 될까요", "옆집 아저씨가 오셨어요",
        "선생님께 물어봤어요", "장갑을 끼고 나가세요", "지하철에 사람이 많아요", "할머니 댁에 다녀왔어요", "떡볶이가 너무 매워요",
        "은행에 들렀다 갈게요", "시장에서 사과를 샀어요", "엄마가 저녁을 차렸어요", "열이 조금 있는 것 같아요", "오늘 저녁은 뭐 먹을까요",
    ],
}


def _norm(s: str) -> str:
    """비교용: 한글 음절만(띄어쓰기·문장 부호를 버림)."""
    return re.sub(r"[^가-힣]", "", s or "")


def training_sentences() -> dict:
    """학습자가 훈련에서 보거나 따라 말하는 문장 {문장: 출처}. 검사 문장이 이것과 너무 가까우면 B 회차 점수가 학습한 문장을
    알아본 몫만큼 부풀므로(훈련은 A2와 B 사이에만 한다) 뺀다.
    - 3단계 상황별 문장의 대체 문장·1단계 상황 기본 문장·말하기 문장(sentence_options.static_pool, 숙달 탐침 문장도 여기서 나온다)
    - 대화 실전의 대체 대사(llm_service.FALLBACK_TURNS·FALLBACK_TURNS_GENERIC)
    - 여러 화자 대화 시나리오의 대체 대사(conversation_scenario._FALLBACK_LINES·_GENERIC_LINES)
    - 서빙하는 문맥 문항(빈칸에 정답을 넣은 문장, 2단계 레슨과 3단계 문맥 추론). CLOSURE_EXCLUDED와 보기가 셋 미만인 것은 뺀다
    LLM이 만들어 운영 서버 DB(ScenarioCache)에 쌓인 문장은 저장소에 없어 보지 못한다(docs/pilot/battery.md 8.1절)."""
    import sentence_options as _so
    import llm_service as _L
    import conversation_scenario as _cs
    import curriculum as _cur
    out = {}
    for s in _so.static_pool():
        out.setdefault(s, "상황·대체·말하기 문장")
    for s in [x for v in _L.FALLBACK_TURNS.values() for x in v] + list(_L.FALLBACK_TURNS_GENERIC):
        out.setdefault(s, "대화 대체 대사")
    for s in [x for v in _cs._FALLBACK_LINES.values() for x in v] + list(_cs._GENERIC_LINES):
        out.setdefault(s, "대화 시나리오 대사")
    ex = getattr(_cur, "CLOSURE_EXCLUDED", {})
    for it in getattr(_cur, "CLOSURE_ITEMS", []) or []:
        if it.get("id") in ex or len(it.get("options") or []) < 3 or "___" not in (it.get("display") or ""):
            continue
        out.setdefault(it["display"].replace("___", it["answer"]), f"문맥 문항 {it['id']}")
    return out


# ── 유사도 점검(2026-10-07) ───────────────────────────────────────────
# 10/6 판은 띄어쓰기를 뺀 완전 일치만 걸러 한두 낱말만 다른 문장(맛있게 많이 드세요 ↔ 맛있게 드세요)이 통과했다. 아래 네 규칙 가운데
# 하나라도 걸리면 '너무 가깝다'로 본다. 기준값은 10/7 검토가 찾은 겹침(교체 16자리 가운데 겹침 때문인 14자리와 예비 SR04)을
# 모두 잡고, 검토가 '가벼움'·'경계'로 둔 경우(물이 너무 뜨거워요 ↔ 솥뚜껑이 너무 뜨거워 0.71, 비가 그칠 것 같아요, 길을 잃어서
# 헤맸어요, 주말에 산에 올라갔어요, 숙제를 다 끝냈어요, 시장에서 사과를 샀어요 등)는 통과하도록 정했다. test_pilot_battery.py가 두
# 쪽을 모두 확인한다.
# R1 포함: 한쪽(한글 음절 SIM_MIN_CONTAINED 이상)이 다른 쪽 안에 그대로 든다(띄어쓰기 무시). 예: 약을 먹고 푹 쉬세요 ⊃ 푹 쉬세요.
# R2 글자 유사도: difflib 비율(2 × 같은 글자 수 / 두 글자 수 합)이 SIM_RATIO 이상. 예: 잠깐만 기다려 주세요 ↔ 잠시만 기다려 주세요 0.89.
# R3 이어진 어절: 똑같은 어절이 차례대로 이어서 나오고, 그 가운데 내용어가 SIM_RUN_CONTENT개 이상. 예: 창문 좀 열어(좀은 기능어).
# R4 통째로 듦: 훈련 문장(검사 문장끼리는 어느 쪽이든)의 내용어 SIM_WHOLE_CONTENT개 이상이 모두 다른 쪽에 있고, 하나 이상은 글자까지
#    같다. 어간이 같으면 같은 낱말로 본다(_same_word: 먹어 ↔ 먹어요, 가세요 ↔ 들어가세요). 예: 머리가 조금 아파요 ⊃ 머리가
#    아파요. 훈련 문장이 긴 쪽일 때(검사 문장 낱말이 모두 긴 훈련 문장에 흩어져 있을 때)는 R4로 보지 않는다. 긴 문장에 흔한 낱말
#    둘이 흩어져 든 경우(감기에 걸렸어요)까지 걸리기 때문이다.
SIM_RATIO = 0.75
SIM_MIN_CONTAINED = 4
SIM_RUN_CONTENT = 2
SIM_WHOLE_CONTENT = 2
# 내용어로 세지 않는 어절(정도·부정 부사, 의존 명사, 지시 관형사). 뜻을 거의 더하지 않아 이것만 겹치면 같은 문장으로 보지 않는다
FUNCTION_WORDS = frozenset({"좀", "잘", "안", "못", "너무", "참", "정말", "아주", "다", "또", "많이", "조금", "더", "꼭",
                            "것", "거", "수", "그", "이", "저"})


def _tokens(s: str) -> list:
    return re.sub(r"[^가-힣\s]", " ", s or "").split()


def _content(s: str) -> list:
    return [t for t in _tokens(s) if t not in FUNCTION_WORDS]


def _same_word(a: str, b: str) -> bool:
    """같은 낱말(어간이 같음)로 보는가. 같은 앞 음절이 짧은 쪽의 절반 이상이고, 그것이 한 음절뿐이면 받침이 있는 음절일 때만
    (먹어 ↔ 먹어요, 덮고 ↔ 덮었어는 같고 아홉 ↔ 아파서는 다름). 또는 두 음절 이상인 짧은 쪽이 긴 쪽의 끝과 같음(가세요 ↔ 들어가세요)."""
    if a == b:
        return True
    k = 0
    while k < min(len(a), len(b)) and a[k] == b[k]:
        k += 1
    if k >= 1 and 2 * k >= min(len(a), len(b)) and (k >= 2 or (ord(a[0]) - 0xAC00) % 28 != 0):
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 2 and long_.endswith(short)


def _whole_inside(inner: str, outer: str) -> bool:
    ci, co = _content(inner), _content(outer)
    if len(ci) < SIM_WHOLE_CONTENT:
        return False
    return all(any(_same_word(a, b) for b in co) for a in ci) and bool(set(ci) & set(co))


def _run_content(a: str, b: str) -> int:
    """똑같은 어절이 이어지는 가장 긴 구간의 내용어 수."""
    ta, tb = _tokens(a), _tokens(b)
    best = 0
    for i in range(len(ta)):
        for j in range(len(tb)):
            n = 0
            while i + n < len(ta) and j + n < len(tb) and ta[i + n] == tb[j + n]:
                n += 1
            if n:
                best = max(best, sum(1 for t in ta[i:i + n] if t not in FUNCTION_WORDS))
    return best


def similarity_reasons(test: str, other: str, both_ways: bool = False) -> list:
    """검사 문장 test가 other(훈련 문장, 또는 both_ways=True면 다른 검사 문장)와 너무 가까운 까닭. 비면 통과."""
    import difflib
    na, nb = _norm(test), _norm(other)
    if not na or not nb:
        return []
    why = []
    short, long_ = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(short) >= SIM_MIN_CONTAINED and short in long_:
        why.append("포함")
    r = difflib.SequenceMatcher(None, na, nb, autojunk=False).ratio()
    if r >= SIM_RATIO:
        why.append(f"글자 유사도 {r:.2f}")
    if _run_content(test, other) >= SIM_RUN_CONTENT:
        why.append("이어진 어절이 같음")
    if _whole_inside(other, test) or (both_ways and _whole_inside(test, other)):
        why.append("낱말이 통째로 듦")
    return why


def is_borderline(test: str, other: str) -> bool:
    """경계(위 네 규칙은 통과): 내용어 둘 이상이 같은 낱말(어간 같음 포함)이다. 10/7 검토가 '경계, 사람 판단'으로 둔 폼 문장
    (길을 잃어서 헤맸어요 ↔ 길을 잘 몰라서 헤맸어 등)이 여기에 든다. 폼 문장은 막지 않고 --check에 보이기만 하며, 예비 문장은
    이것도 뺀다(예비는 문제가 생긴 자리를 바꿀 때 쓰므로 경계 문장을 두지 않는다)."""
    co = _content(other)
    return sum(1 for a in _content(test) if any(_same_word(a, b) for b in co)) >= 2


def training_conflicts(s: str, training: dict) -> list:
    """[(훈련 문장, 출처, 까닭)]"""
    out = []
    for t, src in training.items():
        why = similarity_reasons(s, t)
        if why:
            out.append((t, src, why))
    return out


def _test_words(word_forms) -> set:
    return {it["word"] for f in word_forms.values() for it in f}


def _uses_test_word(sentence: str, words: set) -> str:
    for tok in re.sub(r"[.,?!~]", "", sentence).split():
        for w in words:
            if len(w) >= 2 and tok.startswith(w):
                return w
            if len(w) == 1 and any(tok == w + p for p in _PARTICLES):
                return w
    return ""


def basic_problem(s: str, words: set) -> str:
    """길이·음소·글자·검사 낱말 조건. 비면 통과."""
    n, ph = len(pb.syllables(s)), pb.phoneme_count(s)
    if not (6 <= n <= 10):
        return f"음절 {n}"
    if not (14 <= ph <= 26):
        return f"음소 {ph}"
    if re.search(r"[0-9A-Za-z]", s):
        return "숫자·영문"
    w = _uses_test_word(s, words)
    return f"검사 낱말 '{w}'" if w else ""


def form_problems(forms: dict, words: set, training: dict) -> list:
    """폼 문장 점검. 문제 문장 목록(비면 통과): 개수, 중복, 조건, 훈련 문장과의 유사도, 같은 폼·다른 폼 문장끼리의 유사도."""
    errs = []
    flat = [(f, i, t) for f in pb.FORMS for i, t in enumerate(forms.get(f) or [])]
    for f in pb.FORMS:
        if len(forms.get(f) or []) != N_SENTENCE:
            errs.append(f"폼 {f} 문장 수 {len(forms.get(f) or [])} != {N_SENTENCE}")
    seen = {}
    for f, i, t in flat:
        sid = f"S{f}{i + 1:02d}"
        if _norm(t) in seen:
            errs.append(f"{sid} {t}: {seen[_norm(t)]}와 같은 문장")
        seen.setdefault(_norm(t), sid)
        why = basic_problem(t, words)
        if why:
            errs.append(f"{sid} {t}: {why}")
        for tr, src, w in training_conflicts(t, training):
            errs.append(f"{sid} {t}: 훈련 문장 '{tr}'({src})와 가까움({', '.join(w)})")
    for x in range(len(flat)):
        for y in range(x + 1, len(flat)):
            (fa, ia, ta), (fb, ib, tb) = flat[x], flat[y]
            w = similarity_reasons(ta, tb, both_ways=True)
            if w:
                where = "같은 폼" if fa == fb else "다른 폼"
                errs.append(f"S{fa}{ia + 1:02d} {ta} ~ S{fb}{ib + 1:02d} {tb}: {where} 문장끼리 가까움({', '.join(w)})")
    return errs


def pick_reserve(cands, forms: dict, words: set, training: dict, n: int):
    """예비 문장. 폼에 없는 후보 가운데 조건, 훈련 문장 유사도, 폼 문장 유사도를 모두 통과하고 서로도 가깝지 않은 것을
    음소 수 차례로 줄 세운 뒤 고르게 n개 고른다. (예비, 뺀 후보 [(문장, 까닭)])를 돌려준다."""
    in_forms = [t for f in pb.FORMS for t in forms[f]]
    used = {_norm(t) for t in in_forms}
    pool, rejected, seen = [], [], set()
    for s in cands:
        k = _norm(s)
        if k in used:
            continue
        why = "중복" if k in seen else basic_problem(s, words)
        seen.add(k)
        if not why:
            hit = training_conflicts(s, training)
            if hit:
                why = f"훈련 문장 '{hit[0][0]}'({hit[0][1]})와 가까움({', '.join(hit[0][2])})"
        if not why:
            near = next((t for t in in_forms if similarity_reasons(s, t, both_ways=True)), None)
            if near:
                why = f"폼 문장 '{near}'와 가까움({', '.join(similarity_reasons(s, near, both_ways=True))})"
        if not why:
            near = next((t for t in list(training) + in_forms if is_borderline(s, t) or is_borderline(t, s)), None)
            if near:
                why = f"'{near}'와 경계(내용어 둘 이상이 같음)"
        if why:
            rejected.append((s, why))
        else:
            pool.append(s)
    pool.sort(key=lambda s: (pb.phoneme_count(s), len(pb.syllables(s)), s))
    apart = []
    for s in pool:
        near = next((t for t in apart if similarity_reasons(s, t, both_ways=True) or is_borderline(s, t)
                     or is_borderline(t, s)), None)
        if near:
            rejected.append((s, f"예비 문장 '{near}'와 가까움"))
        else:
            apart.append(s)
    if len(apart) < n:
        raise SystemExit(f"예비로 쓸 수 있는 후보가 {len(apart)}개라 {n}개가 안 된다")
    step = len(apart) / n
    idx = [int(i * step + step / 2) for i in range(n)]
    return [apart[i] for i in idx], rejected


def build():
    import assessment as _asmt
    ff = _asmt.frozen_forms(build_if_missing=False)
    word_forms = {"A": ff["A"], "B": ff["B"], "C": pb.build_word_form_c(WORD_C_SEED)}
    words = _test_words(word_forms)
    cands = [l.strip() for l in CANDIDATES.strip().splitlines() if l.strip()]
    training = training_sentences()
    sforms = FORM_SENTENCES
    problems = form_problems(sforms, words, training)
    reserve, rejected = pick_reserve(cands, sforms, words, training, N_RESERVE)

    def sent_item(prefix, i, s):
        return {"id": f"{prefix}{i + 1:02d}", "text": s, "syllables": len(pb.syllables(s)), "phonemes": pb.phoneme_count(s)}

    nforms = pb.nonsense_forms()
    word_items = {f: [{k: it[k] for k in ("id", "word", "options", "difficulty")} for it in word_forms[f]] for f in pb.FORMS}

    m = {
        "schema": pb.SCHEMA,
        "version": "draft-2026-10-07",
        "status": "draft",
        "note": ("촬영 전 초안. 문장·폼 C 낱말·무의미 낱말은 사람이 검토해 동결한다. 영상·음성 파일은 저장소에 넣지 않고 "
                 "LIPLAB_PILOT_MEDIA_DIR(기본 backend/data/pilot/media) 아래 media_pattern 경로에 둔다. docs/pilot/battery.md"),
        "forms": list(pb.FORMS),
        "orders": list(pb.ORDERS),
        "label_slot": pb.LABEL_SLOT,
        "layers_by_label": {
            "A1": ["nonsense", "word", "sentence", "snr", "av"],
            "A2": ["nonsense", "word", "sentence", "av"],
            "B": ["nonsense", "word", "sentence", "av"],
            "R": ["nonsense", "word", "sentence"],
        },
        "playback": {"speed": 1.0, "max_plays": 2},
        "talkers": {"word": ["T1", "T2", "T3", "T4"], "sentence": ["T1", "T2"], "av": ["T1", "T2"], "snr": ["T1", "T2"]},
        "noise": {"babble": {"file": "noise/babble.wav", "note": "여러 사람 말소리를 섞은 잡담 잡음(8명 이상 권장), 모노 48kHz"}},
        "layers": {
            "word": {
                "title": "실제 얼굴 낱말", "response": "choice4", "modality": "real", "n_per_form": 24,
                "media_pattern": "words/{talker}/{id}.mp4",
                "source": "폼 A·B = 표준검사 forms_v2(촬영 키트 48낱말), 폼 C = build_word_form_c(seed 20261006) 초안",
                "word_c_seed": WORD_C_SEED,
                "items": word_items,
            },
            "sentence": {
                "title": "개방형 문장", "response": "typed", "modality": "avatar", "allowed_modalities": ["real", "avatar"],
                "n_per_form": N_SENTENCE, "syllable_range": [6, 10],
                "media_pattern": "sentences/{talker}/{id}.mp4",
                "items": {f: [sent_item(f"S{f}", i, s) for i, s in enumerate(sforms[f])] for f in pb.FORMS},
                "reserve": [sent_item("SR", i, s) for i, s in enumerate(reserve)],
            },
            "nonsense": {
                "title": "무의미 낱말 자음", "response": "consonant3", "modality": "avatar", "n_per_form": 16,
                "source": "nonsense_words.json 남겨 둔 목록 1·2 = 폼 A·B, 같은 생성기의 세 번째 남겨 둔 목록 = 폼 C",
                "consonant_sets": pb.nonsense_consonant_sets(),
                "items": {f: nforms[i] for i, f in enumerate(pb.FORMS)},
            },
            "av": {
                "title": "소음 속 문장", "response": "typed", "modality": "real", "n_per_form": N_AV, "syllable_range": [6, 10],
                "media_pattern": "av/{talker}/{id}.mp4", "noise": "babble", "blocks": ["A", "AV"],
                "items": {f: [{"id": f"V{f}{i + 1:02d}", "text": None, "speech_rms_dbfs": None} for i in range(N_AV)]
                          for f in pb.FORMS},
            },
            "snr": {
                "title": "SNR 맞추기", "response": "typed", "modality": "audio", "syllable_range": [6, 10],
                "media_pattern": "av/{talker}/{id}.mp4", "noise": "babble",
                "staircase": {"start_db": 0, "step_down_db": 3, "step_up_db": 2, "min_db": -20, "max_db": 10,
                              "reversals": 8, "use_last": 6, "max_trials": 24, "criterion": 0.5},
                "items": [{"id": f"VK{i + 1:02d}", "text": None, "speech_rms_dbfs": None} for i in range(N_SNR)],
            },
        },
    }
    return m, rejected, problems


def main():
    m, rejected, problems = build()
    if "--check" in sys.argv:
        for e in problems:
            print(f"폼 문제: {e}")
        training = training_sentences()
        for f in pb.FORMS:
            for i, t in enumerate(FORM_SENTENCES[f]):
                near = [x for x in training if is_borderline(t, x) or is_borderline(x, t)]
                if near:
                    print(f"경계(사람 판단): S{f}{i + 1:02d} {t} ↔ {' / '.join(near)}")
        for s, why in rejected:
            print(f"뺌: {s} ({why})")
        print(f"폼 문제 {len(problems)}개, 예비 {N_RESERVE}개, 뺀 후보 {len(rejected)}개")
        return
    if problems:
        raise SystemExit("폼 문장 점검 실패:\n" + "\n".join(problems))
    errs = pb.validate_manifest(m)
    if errs:
        raise SystemExit("목록 점검 실패:\n" + "\n".join(errs))
    out = pb.MANIFEST_PATH
    if os.path.exists(out) and "--force" not in sys.argv:
        print(f"이미 있음: {out} (덮어쓰려면 --force)")
        return
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"썼음: {out} (뺀 후보 {len(rejected)}개, sha {pb.manifest_sha(m)})")


if __name__ == "__main__":
    main()
