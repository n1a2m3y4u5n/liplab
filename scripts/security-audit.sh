#!/usr/bin/env bash
# 의존성 보안 점검(계획서 §4.9 ⑦) — 배포 전에 한 번 돌린다. 결과는 요약만 출력하고 파일은 만들지 않는다.
#   bash scripts/security-audit.sh
# 파이썬: pip-audit(없으면 설치 안내만). 프론트: npm audit(운영 의존성만).
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
rc=0

echo "== backend (pip-audit, requirements.txt)"
if command -v pip-audit >/dev/null 2>&1; then
  pip-audit -r "$ROOT/backend/requirements.txt" --progress-spinner off || rc=1
else
  echo "pip-audit 없음 — 설치: pipx install pip-audit (또는 pip install pip-audit) 뒤 다시 실행"
  rc=2
fi

echo "== frontend (npm audit --omit=dev)"
if [ -f "$ROOT/frontend/package-lock.json" ]; then
  (cd "$ROOT/frontend" && npm audit --omit=dev --audit-level=high) || rc=1
else
  echo "package-lock.json 없음 — npm install 뒤 다시 실행"
  rc=2
fi

case $rc in
  0) echo "SECURITY_AUDIT_OK" ;;
  1) echo "SECURITY_AUDIT_FINDINGS — 위 목록을 보고 올릴 수 있는 것은 버전 상한(requirements.txt)과 함께 올린다" ;;
  *) echo "SECURITY_AUDIT_INCOMPLETE — 도구가 없어 일부를 건너뛰었다" ;;
esac
exit $rc
