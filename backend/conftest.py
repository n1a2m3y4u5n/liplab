"""pytest 공통 설정. 테스트마다 서버(TestClient)를 띄우므로 켜질 때의 콘텐츠 표 예열(main._warmup_content)은 끈다.
예열은 첫 요청 지연만 줄이는 것이라 끄면 표를 요청 때 만든다(결과는 같다). 하위 프로세스 테스트도 이 환경 변수를 물려받는다."""
import os

os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")
