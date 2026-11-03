r"""GPU 호스트 주소(사용자@주소)를 저장소 밖 설정에서 읽는다(11/03 검토 M15). 공개 저장소에 Tailscale 주소·계정명을 두지 않는다.

우선순위: 환경변수 LIPLAB_HOST_<이름 대문자> (예: LIPLAB_HOST_LAB_MAIN=사용자@주소)
          → JSON 파일 {"lab_main": "사용자@주소", "black": "..."} (경로: 환경변수 LIPLAB_HOSTS_FILE, 기본 D:\work\hq\shared\liplab-hosts.json)
둘 다 없으면 어디에 무엇을 적을지 알려 주며 멈춘다.
"""
import json
import os

DEFAULT_FILE = r'D:\work\hq\shared\liplab-hosts.json'


def host(name: str) -> str:
    key = name.strip().lower()
    env = os.environ.get('LIPLAB_HOST_' + key.upper())
    if env:
        return env
    path = os.environ.get('LIPLAB_HOSTS_FILE', DEFAULT_FILE)
    try:
        with open(path, encoding='utf-8') as f:
            value = json.load(f).get(key)
    except (OSError, ValueError):
        value = None
    if not value:
        raise RuntimeError(f"호스트 '{key}'를 찾지 못했다: 환경변수 LIPLAB_HOST_{key.upper()} 또는 {path}의 \"{key}\"에 '사용자@주소'를 적는다")
    return value
