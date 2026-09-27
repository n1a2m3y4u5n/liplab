"""숫자 한국어 읽기(korean_numbers)."""
from korean_numbers import native, normalize_numbers, sino


def test_sino():
    assert sino(1) == "일" and sino(10) == "십" and sino(15) == "십오"
    assert sino(123) == "백이십삼" and sino(5000) == "오천"
    assert sino(10000) == "만" and sino(15000) == "만오천" and sino(20000) == "이만"
    assert sino(100000000) == "일억"


def test_native_forms():
    assert native(1) == "한" and native(2) == "두" and native(3) == "세" and native(4) == "네"
    assert native(20) == "스무" and native(21) == "스물한" and native(35) == "서른다섯"
    assert native(1, attributive=False) == "하나"


def test_counter_decides_reading():
    assert normalize_numbers("3시에 만나요") == "세시에 만나요"
    assert normalize_numbers("2명 예약할게요") == "두명 예약할게요"
    assert normalize_numbers("3층으로 가세요") == "삼층으로 가세요"
    assert normalize_numbers("5,000원입니다") == "오천원입니다"
    assert normalize_numbers("30분 걸려요") == "삼십분 걸려요"
    assert normalize_numbers("20살이에요") == "스무살이에요"


def test_beon_times_versus_number():
    assert normalize_numbers("2번 말했어요") == "두번 말했어요"
    assert normalize_numbers("3번 출구로 나가세요") == "삼번 출구로 나가세요"
    assert normalize_numbers("2번째 집이에요") == "두번째 집이에요"


def test_months_and_decimals_and_plain():
    assert normalize_numbers("6월에 봐요") == "유월에 봐요"
    assert normalize_numbers("1.5킬로예요") == "일점오킬로예요"
    assert normalize_numbers("100명이 왔어요") == "백명이 왔어요"   # 고유어는 99까지
    assert normalize_numbers("안녕하세요") == "안녕하세요"


def test_engine_reads_numbers_and_aspirates():
    import engine

    def pron(w):
        cho = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
        jung = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
        jong = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")
        out = ""
        for t in engine.to_pronounced_syllables(w):
            if isinstance(t, list):
                out += chr(0xAC00 + (cho.index(t[0] or "ㅇ") * 21 + jung.index(t[1])) * 28 + jong.index(t[2] or ""))
            else:
                out += t
        return out
    # 받침 ㅅ·ㅊ·ㅌ + ㅎ(표준발음법 12항 붙임2), 겹받침 + ㅎ, 숫자 읽기
    assert pron("못하다") == "모타다" and pron("깨끗하다") == "깨끄타다" and pron("따뜻해") == "따뜨태"
    assert pron("밝히다") == "발키다" and pron("넓히다") == "널피다" and pron("앉히다") == "안치다"
    assert pron("입학") == "이팍" and pron("좋다") == "조타" and pron("닫히다") == "다치다"   # 예전 규칙 유지
    assert pron("3시에 만나요") == "세시에 만나요"


def test_gate_rejects_latin_but_accepts_digits():
    from content_rules import check_sentence
    assert not check_sentence("Wi-Fi 비밀번호 알려주세요")[0]
    assert check_sentence("2시에 만나요")[0]


def test_counters_found_in_audit():
    """9/27 감사: 앞글자가 겹치는 한자어 단위, 첫 번째, 빠졌던 고유어 단위."""
    assert normalize_numbers("3개월 걸려요") == "삼개월 걸려요"
    assert normalize_numbers("5달러예요") == "오달러예요"
    assert normalize_numbers("1번째 집") == "첫번째 집" and normalize_numbers("3번째 줄") == "세번째 줄"
    assert normalize_numbers("2정거장 가요") == "두정거장 가요"
    assert normalize_numbers("3그릇 주세요") == "세그릇 주세요"
    assert normalize_numbers("10개 주세요") == "열개 주세요" and normalize_numbers("2달 뒤") == "두달 뒤"



def test_bun_counts_people_only_with_honorific_endings():
    # '분'은 시간(한자어)과 사람 높임(고유어)이 같은 글자라, 사람일 때만 붙는 어미·조사로 가른다
    assert normalize_numbers("2분이시면 안내해 드릴게요.") == "두분이시면 안내해 드릴게요."
    assert normalize_numbers("3분이세요?") == "세분이세요?"
    assert normalize_numbers("2분께서 오셨어요.") == "두분께서 오셨어요."
    assert normalize_numbers("4분이서 오셨네요.") == "네분이서 오셨네요."
    assert normalize_numbers("2분이 오셨어요.") == "두분이 오셨어요."
    assert normalize_numbers("3분 손님 자리 있어요.") == "세분 손님 자리 있어요."
    # 시간은 그대로 한자어
    assert normalize_numbers("5분 뒤에 나와요.") == "오분 뒤에 나와요."
    assert normalize_numbers("3분이면 돼요.") == "삼분이면 돼요."
    assert normalize_numbers("10분이 지났어요.") == "십분이 지났어요."
    assert normalize_numbers("20분 걸려요.") == "이십분 걸려요."
