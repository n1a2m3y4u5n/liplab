# 전이 측정 배관 (C8·P17·P18, 2026-11-02)

기본값은 모두 끔이다. 실측 결과·효과 근거가 아니며 실제 촬영 자료는 **자료 대기**다. 기존 숙달·XP·복습·채점 상수를 바꾸지 않는다.

## P18 관리자 검수

서버 `LIPLAB_KMSAV_REVIEW=1`, 빌드 `VITE_KMSAV_REVIEW=1`일 때 `/admin/kmsav`를 쓴다. 기존 `LIPLAB_ADMIN_EMAILS` 권한을 적용한다.
영상 ID·HTTPS YouTube 출처·영상 페이지 CC 표기·확인 근거·pending/usable/rejected 판정만 `kmsav_reviews`에 저장한다.
KMSAV 자료 전체 라이선스로 영상 개별 허락을 추정하지 않는다. 영상 다운로드·앱 탑재·학습 모델 연결은 없다.
GET/PUT `/api/admin/kmsav`. 관리자 화면은 기존 토큰·버튼 스타일을 사용한다.

## C8 레슨 탐침

서버 `LIPLAB_REAL_FACE_PROBES=1`, 빌드 `VITE_REAL_FACE_PROBES=1`. 기존 1~3단계 레슨의 C16 탐침 뒤에 끼운다.
C16이 먼저 차지한 문항 수를 `used`로 보내 `mastery_probe.lesson_quota`의 20% 상한을 공유한다. C16 요청이 실패하면 실제 얼굴도 요청하지 않는다.
자연 속도·무음·정답 비공개이며 숙달·XP·SRS에 넣지 않는다. 제시 문항의 판본·화자·보기·정답을 서버에 동결하고 첫 응답만 채점·저장한다.
`real_face_probes`는 계정 열람·삭제·파일럿 보관기간 파기 대상이다. 같은 문항을 같은 계정에 다시 내지 않는다.

기본 목록 `backend/data/pilot/real_face_probes.json`은 빈 초안이다. 운영 목록은 `LIPLAB_REAL_FACE_MANIFEST`로 지정한다.
동결 목록 예시 형식(예시 문항 자체는 제공하지 않음):

```text
version: 판본 문자열(64자 이내)
status: frozen
items: [{id, talker, consent: true, purpose: lesson_probe,
         options: 서로 다른 네 문자열, answer: 보기 중 하나, media: 상대 영상 경로}]
```

영상은 저장소 밖 `LIPLAB_REAL_FACE_MEDIA_DIR`에 둔다. 기본 폴더는 `backend/data/pilot/probe_media`이며 파일을 커밋하지 않는다.
P3 검사 폼·동결 평가 자료와 겹치지 않는 별도 동의된 촬영 문항만 등록한다. 경로 이탈·심볼릭 링크 이탈은 거부한다.
`draft`·파일 없음은 0문항, 잘못된 동결 목록은 503이며 레슨은 기존 흐름을 계속한다. 철회 시 매체 파일도 제거한다.
API: POST `/api/probes/real-face`(lesson_id UUID, lesson_len, used), GET `.../media/{id}`, POST `.../{id}/answer`(chosen, rt_ms).

## P17 세 조건 비교

서버 `LIPLAB_AV_COMPARISON=1`, 빌드 `VITE_AV_COMPARISON=1`, 기존 파일럿 참여 자격(`LIPLAB_PILOT=1`·참여 코드)이 모두 필요하다.
화면 `/pilot/av-comparison`은 기존 `PilotBattery.LayerRunner`의 소음 혼합·반응 시간·재생 횟수·타이핑 UI를 재사용한다.
연구진이 소리 단독 정답률 약 30%가 되도록 미리 맞춘 SNR을 입력하고 헤드폰·고정 볼륨을 확인한다. 시작 뒤 SNR을 바꿀 수 없다.
목록 순서에 참여자 번호의 3가지 회전을 적용해 A(소리만)·avatar(소리+아바타)·real(소리+실제)을 균형 배정한다.
문장은 세 조건에서 같은 풀을 쓰되 한 참여자가 같은 문장을 반복해서 답하지 않는다. 각 조건에 같은 문항 수를 배정한다.
아바타 영상은 실제 영상과 같은 소리·정렬·길이를 사용해 미리 렌더한 별도 자극이다. 등록 전 연구진이 이를 확인한다.
재생 중 아바타를 즉석 생성하거나 가짜 실사 영상으로 대체하지 않는다.

서버 목록 `LIPLAB_AV_COMPARISON_MANIFEST`(기본 `backend/data/pilot/av_comparison.json`) 형식:

```text
version: 판본
status: frozen
noise: 잡음 상대 경로
items: [{id, text, talker, consent: true, real_media, avatar_media, speech_rms_dbfs}]
```

문항 수는 3의 배수다. 영상 두 종류와 잡음 모두 위의 별도 매체 폴더 안에 있어야 한다. 녹음·영상·전사 원자료를 저장소에 넣지 않는다.
조건별 낱말 맞힌 수/전체 수를 서버의 기존 `pilot_battery.word_hits`로 계산한다. 아바타 차이=avatar−A, 실제 차이=real−A,
상대 지수=(avatar−A)/(real−A). 실제 차이≤0 또는 미완료면 지수를 보고하지 않는다. 새 판단 기준이나 효과 주장으로 쓰지 않는다.
모델 간 차이의 참가자 재표집 구간·판정은 사람 자료와 별도 동결 분석 계획이 필요하므로 미측정이다.
`av_comparisons`는 동결 목록·SNR·기기 확인, `av_comparison_answers`는 조건·답·낱말 수·재생 수·반응 시간을 기록한다.
계정당 한 회차만 허용하고 미완료는 이어 하며, 재전송은 처음 답을 유지한다. 계정 열람·삭제·파기에 포함된다.
API: GET `/api/pilot/av-comparison`, POST `.../start`, `.../answer`, `.../finish`, 인증된 `.../media/{session}/{item}`·`.../noise/{session}`.

## 자료 대기와 검증 범위

P0 추가 구현: 관리자 가명 내보내기 `/api/pilot/export` 판 8의 `transfer`에 C8·P17 판본·문항 ID·화자·조건·채점 수·반응 시간·SNR·완료 여부를 싣는다.
로컬 파일 경로·동결 정답·타이핑 답 원문·사용자 번호는 넣지 않는다. 계정 본인 열람 API는 기존 방식대로 전체 본인 기록을 반환한다.

실제 촬영·동의·SNR 보정·매체 재생 동기 검증은 사람 자료가 들어온 뒤 한다. 테스트의 임시 매체 바이트는 권한·존재 검사에만 사용하며 제품 자료가 아니다.
기능 검증은 기본 끔, 인증/관리자/참여 자격, 자료 없음, 경로 경계, 상한 공유, 처음 답 유지, 서버 채점, 분모 0·음수 보호를 다룬다.
