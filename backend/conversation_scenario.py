"""
다자 대화 시나리오 생성 — 고도화 축 H.

계획서 §3.8: 실제 대화는 화자가 여럿이고 발화 순서가 수시로 바뀌며, 듣는 사람은 '지금 누가
말하는지'부터 가려야 한다. 현행 훈련은 한 화자의 한 문장씩만 다뤄 실제 상황과 거리가 있다.
이 모듈은 여러 화자가 번갈아 말하는 짧은 일상 대화를 생성해, 화자 식별 + 입모양 읽기를 함께
훈련하는 실전 독화의 콘텐츠를 만든다(콘텐츠 대량화 G의 문장을 다화자 상황으로 재조합).
"""
import random
import llm_json
from typing import Dict, List, Optional

from llm_service import anthropic_client

_MODEL = "claude-sonnet-4-6"
_SCENES = ["카페", "병원 대기실", "학교 교실", "가족 저녁 식사", "가게 계산대", "친구 모임"]

# LLM 실패(키 없음·파싱 오류)시 결정론적 폴백 — 500/무한로딩 방지. 장면별 짧은 구어체 대화.
_FALLBACK_LINES = {
    "카페": ["뭐 마실래?", "따뜻한 걸로 줘", "여기 자리 좋다", "그러게 조용하네", "케이크도 먹을까?", "좋아 하나 시키자"],
    "병원 대기실": ["많이 기다렸어?", "삼십 분 됐어", "번호표 뽑았어?", "응 여기 있어", "곧 부를 거야", "다행이다"],
    "학교 교실": ["숙제 했어?", "아직 못 했어", "같이 할까?", "그래 도와줘", "점심 뭐 먹지?", "매점 가자"],
    "가족 저녁 식사": ["밥 다 됐어", "맛있겠다", "국 좀 더 줘", "천천히 먹어", "오늘 어땠어?", "재밌었어요"],
    "가게 계산대": ["이거 얼마예요?", "삼천 원이요", "봉투 주세요", "네 여기요", "카드 될까요?", "그럼요 됩니다"],
    "친구 모임": ["오랜만이야", "잘 지냈어?", "그럭저럭 지냈어", "얼굴 좋아 보여", "다음에 또 보자", "꼭 연락해"],
}
# 학습자가 직접 적은 상황(상황별 시나리오의 '어떤 상황인가요?')처럼 목록에 없는 장면의 폴백 — 어느 자리에나 맞는 인사·안부.
_GENERIC_LINES = ["안녕하세요 반가워요", "네 오랜만이에요", "요즘 어떻게 지내요?", "그럭저럭 지내요", "잠깐 얘기할까요?", "좋아요 그래요"]
MAX_SPEAKERS = 4


def clean_scene(scene: Optional[str]) -> Optional[str]:
    """학습자가 적은 장면 → 프롬프트에 넣을 짧은 한 줄(제어문자·따옴표·괄호 제거, 30자). 비면 None."""
    if not scene:
        return None
    s = "".join(" " if ch.isspace() else ch for ch in str(scene))        # 줄바꿈·탭은 띄어쓰기로
    s = "".join(ch for ch in s if ch.isprintable() and ch not in '"\'`{}[]<>')
    s = " ".join(s.split())[:30].strip()
    return s or None


# 닮은꼴 치환에서 어절 끝에 붙어도 되는 조사(이것 외의 꼬리가 붙은 어절은 치환하지 않는다).
_PARTICLES = ("", "은", "는", "이", "가", "을", "를", "에", "에서", "에게", "도", "만", "랑", "하고",
              "의", "으로", "로", "와", "과", "이야", "야", "이에요", "예요", "요")


def speaker_sequence(speakers: int, turns: int, rng: random.Random) -> List[int]:
    """화자 순서 — 규칙적으로 번갈지 않게(같은 사람이 연달아 말하기 포함) 섞되 모든 화자가 나온다.
    순서만 보고 화자를 맞히는 요령을 막아, 얼굴·입모양으로 화자를 가리게 한다(H-2)."""
    for _ in range(50):
        seq, prev = [], rng.randrange(speakers)
        for i in range(turns):
            if i == 0:
                cur = prev
            elif rng.random() < 0.3:
                cur = prev                          # 같은 사람이 이어 말함
            else:
                cur = rng.choice([s for s in range(speakers) if s != prev])
            seq.append(cur)
            prev = cur
        alternating = all(seq[i] == i % speakers for i in range(turns))
        if len(set(seq)) == speakers and not alternating:
            return seq
    return [i % speakers for i in range(turns)]


def lookalike_map() -> Dict[str, List[str]]:
    """최소대립쌍 데이터 중 입모양으로 헷갈리는 쌍(same_looking) → {단어: [닮은꼴 단어...]}.
    실재 단어만 쓰려고 생성기(lookalike_candidates) 대신 이 데이터를 쓰되, 표시가 틀린 쌍(예: 모음까지
    다른 바다/파도)을 거르려고 규칙(content_rules._visually_confusable)으로 한 번 더 확인한다."""
    import content_rules as _rules
    import curriculum as _cur
    m: Dict[str, set] = {}
    for p in _cur.MINIMAL_PAIRS:
        if (p.get("same_looking") and p.get("a") and p.get("b")
                and _rules._visually_confusable(p["a"], p["b"])):
            m.setdefault(p["a"], set()).add(p["b"])
            m.setdefault(p["b"], set()).add(p["a"])
    return {k: sorted(v) for k, v in m.items()}


def _stem(token: str, lmap: Dict[str, List[str]]) -> Optional[str]:
    """어절에서 닮은꼴 사전에 있는 가장 긴 앞부분(나머지는 조사여야 함)."""
    for n in range(len(token), 0, -1):
        head, tail = token[:n], token[n:]
        if head in lmap and tail in _PARTICLES:
            return head
    return None


def lookalike_variants(text: str, lmap: Dict[str, List[str]], k: int = 3,
                       rng: Optional[random.Random] = None) -> List[str]:
    """한 단어를 입모양이 같은 다른 단어로 바꾼 문장들 — 입만 보면 원문과 구별이 안 돼 문맥이 필요한 오답(H-4)."""
    rng = rng or random.Random(0)
    toks = text.split()
    out = []
    for i, tok in enumerate(toks):
        stem = _stem(tok.rstrip("?!.,"), lmap)
        if not stem:
            continue
        for partner in lmap[stem]:
            v = " ".join(toks[:i] + [partner + tok[len(stem):]] + toks[i + 1:])
            if v != text:
                out.append(v)
    out = list(dict.fromkeys(out))
    rng.shuffle(out)
    return out[:k]


def closure_turn(turns: List[Dict], lmap: Dict[str, List[str]], rng: random.Random) -> Optional[Dict]:
    """앞 턴 문맥으로 풀 빈칸 턴 하나 — 닮은꼴이 있는 단어 자리를 비우고 정답+닮은꼴 보기(3지)를 준다."""
    cands = []
    for i, t in enumerate(turns):
        if i == 0:
            continue                                  # 앞 문맥이 있어야 추론이 된다
        toks = t["text"].split()
        for j, tok in enumerate(toks):
            stem = _stem(tok.rstrip("?!.,"), lmap)
            if stem and len(lmap[stem]) >= 1:
                cands.append((i, j, stem))
    if not cands:
        return None
    i, j, stem = rng.choice(cands)
    toks = turns[i]["text"].split()
    toks[j] = "___" + toks[j][len(stem):]
    opts = [stem] + lmap[stem][:2]
    rng.shuffle(opts)
    return {"index": i, "display": " ".join(toks), "answer": stem, "options": opts}


def enrich(conv: Dict, rng: random.Random) -> Dict:
    """대화에 턴별 닮은꼴 오답(read_options)과 빈칸 턴(closure)을 붙인다."""
    lmap = lookalike_map()
    for t in conv["turns"]:
        t["lookalikes"] = lookalike_variants(t["text"], lmap, rng=rng)
    conv["closure"] = closure_turn(conv["turns"], lmap, rng)
    return conv


def score_multi(key: Dict, speaker_choices: List[Optional[int]], read_choices: List[Optional[str]],
                closure_choice: Optional[str]) -> Dict:
    """서버 재채점(H-9). key는 서명된 정답(화자 순서 sp, 턴 문장 tx, 빈칸 정답 cl).
    종합 점수는 계획서대로 립리딩(닮은꼴 문장 중 실제 문장 고르기)과 문맥 추론(빈칸)의 결합이고,
    화자 식별은 따로 보고한다."""
    sp, tx, cl = key.get("sp", []), key.get("tx", []), key.get("cl")
    s_pairs = [(c, sp[i]) for i, c in enumerate(speaker_choices or []) if c is not None and i < len(sp)]
    r_pairs = [(c, tx[i], i) for i, c in enumerate(read_choices or []) if c is not None and i < len(tx)]
    spk_acc = sum(c == a for c, a in s_pairs) / len(s_pairs) if s_pairs else 0.0
    read_acc = sum(c == a for c, a, _ in r_pairs) / len(r_pairs) if r_pairs else 0.0
    closure_ok = None if (cl is None or closure_choice is None) else (closure_choice == cl)
    context = read_acc if closure_ok is None else float(closure_ok)
    return {
        "combined": round(100 * (0.5 * read_acc + 0.5 * context), 1),
        "speaker_accuracy": round(spk_acc, 3),
        "read_accuracy": round(read_acc, 3),
        "closure_correct": closure_ok,
        "read_hits": [a for c, a, _ in r_pairs if c == a],
        "read_misses": [a for c, a, _ in r_pairs if c != a],
    }


def _fallback_conversation(speakers: int, turns: int, scene: str,
                           rng: Optional[random.Random] = None) -> Dict:
    rng = rng or random.Random()
    lines = _FALLBACK_LINES.get(scene) or _GENERIC_LINES
    seq = speaker_sequence(speakers, turns, rng)
    out = [{"speaker": seq[i], "text": lines[i % len(lines)]} for i in range(turns)]
    return {"scene": scene, "speakers": speakers, "turns": out, "fallback": True}


async def generate_multi_conversation(speakers: int = 2, turns: int = 6,
                                      scene: Optional[str] = None,
                                      focus_words: Optional[List[str]] = None) -> Dict:
    """N명이 나누는 짧은 일상 대화. 각 턴은 {speaker, text, lookalikes}, 대화에는 빈칸 턴(closure)이 붙는다.
    focus_words는 학습자의 약점 입모양이 든 승인 단어(G) — 대화에 자연스럽게 넣도록 요청한다(H-3).
    턴마다 문장 게이트(content_rules.check_sentence)를 거치고, 화자 순서는 규칙적으로 번갈지 않게 한다."""
    import content_rules as _rules
    rng = random.Random()
    speakers = max(2, min(speakers, MAX_SPEAKERS))
    turns = max(3, min(turns, 10))
    scene = clean_scene(scene) or rng.choice(_SCENES)
    focus = [w for w in (focus_words or []) if w][:6]
    focus_line = (f"- 가능하면 다음 단어 중 2개 이상을 자연스럽게 넣는다: {', '.join(focus)}\n" if focus else "")
    system = (
        f"너는 청각장애인 독화 훈련용 '다자 대화' 출제기다.\n"
        f"- {speakers}명이 '{scene}'에서 나누는 자연스러운 일상 대화를 만든다.\n"
        "- 각 턴은 6~14자의 짧은 구어체 한 문장.\n"
        "- 화자 순서를 규칙적으로 번갈지 말 것. 같은 사람이 연달아 두 번 말하는 경우를 한 번 이상 넣는다.\n"
        f"- 화자 번호는 0~{speakers - 1}.\n"
        f"{focus_line}"
        f'반드시 JSON만 출력: {{"turns": [{{"speaker": 0, "text": "문장"}}, ...]}} — 정확히 {turns}턴.'
    )
    try:
        resp = await anthropic_client.messages.create(
            model=_MODEL, max_tokens=600, temperature=1.0, system=system,
            messages=[{"role": "user", "content": f"변주 시드 {rng.randint(1000, 9999)}"}],
        )
        data = llm_json.extract_json(resp)
        out_turns: List[Dict] = []
        for t in data.get("turns", []):
            text = str(t.get("text", "")).strip()
            ok, _, _ = _rules.check_sentence(text)
            if not ok:
                continue                                     # 지시 이탈·부적합 문장은 버린다
            spk = int(t.get("speaker", 0)) % speakers
            out_turns.append({"speaker": spk, "text": text})
        if len(out_turns) < 3 or len({t["speaker"] for t in out_turns}) < 2:   # 부실하면 폴백
            return enrich(_fallback_conversation(speakers, turns, scene, rng), rng)
        return enrich({"scene": scene, "speakers": speakers, "turns": out_turns}, rng)
    except Exception as e:
        # 키 없음·네트워크·파싱 실패 → 결정론적 대화로 폴백(엔드포인트 500·프론트 무한로딩 방지)
        print(f"[WARN] multi-conversation LLM failed, using fallback: {e}")
        return enrich(_fallback_conversation(speakers, turns, scene, rng), rng)
