# 요청 폭주·비용 공격 대비(2026-09-28)

## 서버에 들어간 것(배포하면 켜짐)

| 위협 | 대비 | 조정 |
|---|---|---|
| LLM 비용 폭증(데모 토큰은 로그인 없이 받음) | 모든 `messages.create` 앞에서 하루 호출 수를 센다(`backend/llm_budget.py`). 서버 전체 1,500회·IP당 150회, 한국 시간 자정 초기화. 넘으면 저장 문장·대체 대사·규칙 코칭으로 넘어간다. 서버 전체 수는 `/data/llm_budget.json`에 남아 재시작해도 이어진다 | `LIPLAB_LLM_DAILY_MAX`, `LIPLAB_LLM_CLIENT_DAILY_MAX` |
| LLM 엔드포인트 연타 | IP당 분당 한도를 낮춤: 상황 문장 40 → 15, 대화 턴 40 → 20, 다자 대화 30 → 15, 수어 번역 40 → 20, 말하기 단계 문항 60 → 30 | `main.py`의 `rate_limit(...)` |
| 채점 추론 대기열 독점 | 실행 중 + 대기가 동시 실행 수 + 4를 넘으면 받기 전에 503과 Retry-After 10초 | `LIPLAB_ML_QUEUE_MAX` |
| 큰 요청 하나로 기계 멈춤 | 요청 본문 상한(멀티파트 12MB, 그 밖 2MB), 오디오 10MB(전부터) | |
| 기계 수 증가로 인한 비용 | fly 기계가 앱마다 1대로 고정(자동으로 늘지 않음) | |

**가장 확실한 비용 상한은 Anthropic 콘솔의 월 사용 한도다.** console.anthropic.com → Settings → Limits에서 직접 건다.
코드의 하루 한도는 그 아래에서 서비스가 갑자기 멈추지 않게 나누는 역할이다.

## 방화벽(Cloudflare) 붙이는 법

fly에는 웹 요청(L7)을 거르는 방화벽이 없다. 대량 패킷(L3/L4)은 fly 엣지가 흡수한다. L7까지 막으려면 Cloudflare(무료 플랜으로 충분)를 앞에 둔다.
`*.fly.dev` 주소에는 Cloudflare를 씌울 수 없어 **직접 소유한 도메인이 필요하다.**

사용자가 할 일(계정·결제·DNS는 대신할 수 없음):
1. 도메인 준비(예: liplab.kr). Cloudflare 무료 계정에 도메인을 추가하고, 등록처에서 네임서버를 Cloudflare 것으로 바꾼다.
2. `fly certs add <도메인> -a liplab-dev`(전시앱이면 `-a liplab`), Cloudflare DNS에 CNAME `<도메인> → liplab-dev.fly.dev`를 **프록시 켬(주황 구름)**으로 만든다.
3. Cloudflare SSL/TLS를 Full(strict)로 둔다.
4. Security에서 Bot Fight Mode를 켜고, WAF 관리 규칙(무료 제공분)을 켠다. 공격 중에는 "Under Attack" 모드를 켠다.
5. 속도 제한 규칙 1개(무료): 경로 `/api/*`, IP당 10초 50회 초과 시 차단 10초 정도.
6. Rules → Transform Rules → 요청 헤더 수정: 모든 요청에 `X-Origin-Auth: <긴 무작위 값>`을 넣는다.
7. 같은 값을 서버에 넣는다: `fly secrets set LIPLAB_ORIGIN_SECRET=<같은 값> -a liplab-dev`.

7을 하면 서버가 `X-Origin-Auth`가 없는 요청(= fly 주소로 바로 온 요청)을 403으로 막아, 공격자가 Cloudflare를 건너뛰지 못한다
(`/health`만 예외). 이때 IP 제한은 Cloudflare가 넣는 `CF-Connecting-IP`로 센다(비밀 헤더가 맞을 때만 믿는다).
설정하지 않으면 지금처럼 fly 주소로 바로 받는다. 7은 반드시 2~6이 끝나고 새 도메인으로 접속되는 것을 확인한 뒤에 한다.
