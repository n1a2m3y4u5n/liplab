APP = '/Users/namyunsu/Downloads/liplab/.claude/worktrees/agent-add8fe1d30054f08d/'
tv = '''

## 9. V15 표와 V5 재선정 (10/7)

538 탐색 절반 분포로 다시 맞춘 입모양 표(V15, `docs/viseme-calibration-2026-10.md`)와 함께 쓰는 가상 화자 값을 따로 두었다(`TALKERS_V15`,
범위 `RANGES_V15`). 입 벌림·돌출·말 속도는 탐색 화자 배율의 10~90백분위 안에서 정한 분위수를 시뮬레이션 반응 곡선으로 모프 배율로 옮겼고,
폭·동시조음·흔들림은 538 자료로 잴 수 없어 7.3절 값에서 출발했다. V15 표로 판별 기준 (a)~(d)를 걸어 화자 3·5·6은 4절 규칙으로 줄였다
(`scripts/v15_talker_shrink.mjs`, 단위 테스트 `talkers.test.mjs`). 확인 절반 판정에서 V15 표가 기준에 못 미쳐, 두 값 모두 빌드 플래그
`VITE_VISEME_V15=1`일 때만 켜지고 기본은 7.3절 값 그대로다.
'''
av = '''

### 10.8 후속(10/7): V15 간이 경로

10.6의 입모양 표 입력으로 538 탐색 절반 분포에 맞춘 표를 만들어 확인 절반에서 다시 쟀다(`docs/viseme-calibration-2026-10.md`). RSA는 0.612 →
0.865로 사람 범위 안에 들었지만 2.0배 진폭(7/13), 1.0배 원순 돌출, 무리별 구별성이 사전 기준에 못 미쳐 앱 기본은 바꾸지 않았다. 10.1의
mouthClose 리그 한계는 음성 구동·웹캠 경로의 보정 사상으로 왕복 r이 탐색 0.345 → 0.541, 확인 0.162 → 0.411로 올랐다.
'''
for path, text in (('docs/talker-variation.md', tv), ('docs/avatar-validity-2026-10.md', av)):
    s = open(APP + path, encoding='utf-8').read()
    if text.strip().splitlines()[0] not in s:
        open(APP + path, 'w', encoding='utf-8').write(s.rstrip('\n') + '\n' + text)
print('ok')
