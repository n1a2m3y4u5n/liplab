"""pytest 공통 설정. 테스트마다 서버(TestClient)를 띄우므로 켜질 때의 콘텐츠 표 예열(main._warmup_content)은 끈다.
예열은 첫 요청 지연만 줄이는 것이라 끄면 표를 요청 때 만든다(결과는 같다). 하위 프로세스 테스트도 이 환경 변수를 물려받는다.

Windows(기본 인코딩 cp949)에서는 파이썬 UTF-8 모드로 pytest를 다시 띄운다. 하위 프로세스 테스트는 `python -c`의 한국어 출력을
text=True로 읽고, 앱 코드도 인코딩을 적지 않은 open()으로 UTF-8 자료 파일을 읽어, UTF-8 모드가 아니면 10/17 데스크탑에서
72개가 실패했다(PYTHONUTF8=1이면 809개 모두 통과). PYTHONUTF8은 하위 프로세스에도 물려져 부모·자식이 같은 인코딩을 쓴다.
맥·리눅스(기본 UTF-8)와 이미 UTF-8 모드인 실행에서는 아무것도 하지 않는다."""
import os
import subprocess
import sys

os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")

if os.name == "nt" and not sys.flags.utf8_mode and os.environ.get("LIPLAB_PYTEST_UTF8") != "1":
    os.environ["PYTHONUTF8"] = "1"
    os.environ["LIPLAB_PYTEST_UTF8"] = "1"      # 다시 띄운 pytest가 또 띄우지 않게
    sys.stdout.flush()
    raise SystemExit(subprocess.call([sys.executable, "-X", "utf8", "-m", "pytest", *sys.argv[1:]]))
