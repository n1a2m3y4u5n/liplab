"""청인 예비 파일럿(P3) 검사 목록 파일 만들기(docs/pilot/battery.md).

backend/data/pilot/battery_manifest.json을 만든다. 이미 있으면 덮어쓰지 않는다(--force). 촬영 목록을 동결한 뒤에는
이 스크립트를 다시 돌리지 않고 목록 파일을 직접 고친 다음 version을 올린다.

- 실제 얼굴 낱말: 폼 A·B는 동결 표준검사 v2(촬영 키트 48낱말) 그대로, 폼 C는 난이도를 맞춰 새로 고른다(pilot_battery.build_word_form_c).
- 개방형 문장: 아래 후보 문장(초안)에서 조건(6~10음절, 채점 음소 14~26, 숫자·외래어 없음, 훈련 문장·검사 낱말과 겹치지 않음)을
  통과한 것을 음소 수가 고르게 세 폼으로 나누고 남는 것은 예비로 둔다. 문장은 촬영 전에 사람이 검토해 동결한다.
- 무의미 낱말: 짝 맞추기 학습(C10, backend/nonsense_words.py)이 남겨 둔 두 목록을 폼 A·B로, 같은 생성기로 하나 더 만든 목록을
  폼 C로 쓴다(pilot_battery.nonsense_forms). 학습 목록 48낱말과 겹치지 않는다.
- 소음 속 문장·SNR 계단 문장: 문장과 음성이 촬영 뒤에 정해지므로 자리만 만든다(text, speech_rms_dbfs가 null).

    python3 scripts/build_pilot_manifest.py            # 만들기(있으면 멈춤)
    python3 scripts/build_pilot_manifest.py --force    # 다시 만들기
    python3 scripts/build_pilot_manifest.py --check    # 후보 문장 걸러진 사유만 보기
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
"""

_PARTICLES = ("", "을", "를", "이", "가", "은", "는", "도", "에", "에서", "으로", "로", "만", "과", "와", "랑", "이랑", "의")


def _norm(s: str) -> str:
    return re.sub(r"[\s.,?!~]", "", s or "")


def _training_sentences() -> set:
    import sentence_options as _so
    import curriculum as _cur
    out = {_norm(s) for s in _so.static_pool()}
    for it in getattr(_cur, "CLOSURE_ITEMS", []) or []:
        for k in ("sentence", "text", "answer_sentence"):
            if isinstance(it.get(k), str):
                out.add(_norm(it[k]))
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


def filter_sentences(cands, words: set, training: set):
    ok, rejected = [], []
    seen = set()
    for s in cands:
        n, ph = len(pb.syllables(s)), pb.phoneme_count(s)
        why = ""
        if _norm(s) in seen:
            why = "중복"
        elif not (6 <= n <= 10):
            why = f"음절 {n}"
        elif not (14 <= ph <= 26):
            why = f"음소 {ph}"
        elif re.search(r"[0-9A-Za-z]", s):
            why = "숫자·영문"
        elif _norm(s) in training:
            why = "훈련 문장과 같음"
        else:
            w = _uses_test_word(s, words)
            if w:
                why = f"검사 낱말 '{w}'"
        seen.add(_norm(s))
        (rejected if why else ok).append((s, why) if why else s)
    return ok, rejected


def split_forms(sentences, n_per: int, n_reserve: int):
    """음소 수로 정렬해 뱀 순서(A B C C B A …)로 나눈다. 세 폼의 음소 수 분포가 비슷해지고, 남는 것은 예비로 간다."""
    need = n_per * 3
    ordered = sorted(sentences, key=lambda s: (pb.phoneme_count(s), len(pb.syllables(s)), s))
    if len(ordered) < need:
        raise SystemExit(f"조건을 통과한 문장이 {len(ordered)}개라 {need}개가 안 된다")
    # 고르게 솎아 need개를 폼용으로, 나머지를 예비로
    step = len(ordered) / need
    picked_idx = sorted({int(i * step) for i in range(need)})
    picked = [ordered[i] for i in picked_idx]
    reserve = [s for i, s in enumerate(ordered) if i not in set(picked_idx)][:n_reserve]
    forms = {"A": [], "B": [], "C": []}
    snake = "ABCCBA"
    for i, s in enumerate(picked):
        forms[snake[i % 6]].append(s)
    return forms, reserve


def build():
    import assessment as _asmt
    ff = _asmt.frozen_forms(build_if_missing=False)
    word_forms = {"A": ff["A"], "B": ff["B"], "C": pb.build_word_form_c(WORD_C_SEED)}
    words = _test_words(word_forms)
    cands = [l.strip() for l in CANDIDATES.strip().splitlines() if l.strip()]
    ok, rejected = filter_sentences(cands, words, _training_sentences())
    sforms, reserve = split_forms(ok, N_SENTENCE, N_RESERVE)

    def sent_item(prefix, i, s):
        return {"id": f"{prefix}{i + 1:02d}", "text": s, "syllables": len(pb.syllables(s)), "phonemes": pb.phoneme_count(s)}

    nforms = pb.nonsense_forms()
    word_items = {f: [{k: it[k] for k in ("id", "word", "options", "difficulty")} for it in word_forms[f]] for f in pb.FORMS}

    m = {
        "schema": pb.SCHEMA,
        "version": "draft-2026-10-06",
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
    return m, rejected


def main():
    m, rejected = build()
    if "--check" in sys.argv:
        for s, why in rejected:
            print(f"뺌: {s} ({why})")
        return
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
