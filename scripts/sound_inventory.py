#!/usr/bin/env python
"""소리 조건(C17)으로 미리 합성할 고정 글 목록. 파드에서 합성하기 전에 맥에서 만든다(가벼운 순수 계산).

    python scripts/sound_inventory.py OUT.json

출처(docs/sound-condition.md 2절)
  stage1   1단계: 입모양 무리 대표 음절(DEMO_SYLLABLE), 레슨 예시 단어, 최소대립 짝, AX(같다·다르다) 문항 음절
  word     2단계: 단어 은행(큐레이션 + 승인 단어)과 승인 짝의 단어
  closure  문맥 추론: 빈칸을 채운 문장(승인·미검수 병합 뒤 CLOSURE_ITEMS)
  sentence 3단계 문장 풀(sentence_options.static_pool: 단계별 대체 문장·상황 기본 문장·말하기 문장)
  convo    대화 대체 대사(llm_service.FALLBACK_TURNS·GENERIC, conversation_scenario._FALLBACK_LINES·_GENERIC_LINES)
  listen   듣기(청능훈련) 트랙(listen_curriculum.inventory_texts, 모듈이 있을 때만). 듣기 목소리 전부로 합성한다
뺀 것: 사전·사후 평가 폼, 파일럿 검사, 숙달 지연 탐침. 검사 문항은 소리 없이 보는 것이 원칙이라 소리를 만들지 않는다.

같은 키(sound_clips.normalize_text)는 한 번만 합성한다. 합성에 넣는 글은 숫자를 한국어 읽기로 바꾼 것이다(입모양 엔진과 같은
korean_numbers.normalize_numbers). 키에는 원래 글을 쓴다(화면이 묻는 글이 원래 글이다).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

import curriculum as C  # noqa: E402
import sound_clips as S  # noqa: E402


def collect():
    out = {}

    def add(text, src):
        key = S.normalize_text(text)
        if not key:
            return
        e = out.setdefault(key, {"key": key, "text": text, "sources": []})
        if src not in e["sources"]:
            e["sources"].append(src)

    for syl in C.DEMO_SYLLABLE.values():
        add(syl, "stage1")
    for l in C.VISEME_LESSONS:
        for w in l.get("example_words", []):
            add(w, "stage1")
    for p in C.MINIMAL_PAIRS:
        add(p["a"], "stage1"); add(p["b"], "stage1")
    for a, b in C.ax_candidates():
        if C.ax_pair(a, b):
            add(a, "stage1"); add(b, "stage1")

    for w in C.WORD_BANK:
        add(w["word"], "word")
    try:
        with open(C._APPROVED_PATH, encoding="utf-8") as f:
            approved = json.load(f)
        for p in approved.get("pairs", []):
            add(p["a"], "word"); add(p["b"], "word")
    except OSError:
        pass

    for it in C.CLOSURE_ITEMS:
        if "display" in it and "answer" in it:
            add(it["display"].replace("___", it["answer"]), "closure")

    import sentence_options
    for s in sentence_options.static_pool():
        add(s, "sentence")

    import llm_service as L
    import conversation_scenario as CS
    for lines in L.FALLBACK_TURNS.values():
        for s in lines:
            add(s, "convo")
    for s in L.FALLBACK_TURNS_GENERIC:
        add(s, "convo")
    for lines in CS._FALLBACK_LINES.values():
        for s in lines:
            add(s, "convo")
    for s in CS._GENERIC_LINES:
        add(s, "convo")

    # 듣기(청능훈련) 트랙 글. 이 글은 듣기 목소리 전부로 합성한다(다른 출처는 기본 목소리만). 모듈이 없으면 건너뛴다.
    try:
        import listen_curriculum as LC
        for t in LC.inventory_texts():
            add(t, "listen")
    except ImportError:
        pass

    from korean_numbers import normalize_numbers
    items = []
    for e in out.values():
        e["tts_text"] = normalize_numbers(e["text"])
        e["n_syl"] = len(S.syllable_positions(e["text"]))
        items.append(e)
    items.sort(key=lambda e: (e["sources"][0], e["key"]))
    return items


def main():
    items = collect()
    path = sys.argv[1] if len(sys.argv) > 1 else "sound_texts.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=0)
    by = {}
    for e in items:
        for s in e["sources"]:
            by[s] = by.get(s, 0) + 1
    print(json.dumps({"total": len(items), "by_source": by,
                      "syllables": sum(e["n_syl"] for e in items)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
