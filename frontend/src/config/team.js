// LIPLAB 팀 정보. 사용법 가이드 11 개발자 소개(Figma 342:530)와 랜딩 개발자 정보(9/25 사용자 요청)가 함께 쓴다.
// 이름·역할·핸들은 Figma 문구 그대로. 핸들은 깃허브 계정과 다를 수 있어 링크를 걸지 않는다.
// mascot(9/28): 프로필 사진 대신 마스코트, 사람마다 색(palette)·표정(face)·모션(motion)이 다르다(components/MascotAvatar).
// detail(9/28: 누르면 상세 정보): intro 소개, work 맡은 일, awards 수상·선발 이력(scope: 교외 external · 교내 school).
// 남윤수 수상은 본인이 준 목록(9/28)과 교사추천서 참고자료의 원본 대조 수상표를 맞춘 것이다. 다른 팀원의 상세는 확인된 자료가
// 없어 비워 두었다(채우면 화면에 바로 나온다).
const SCHOOL = '충남삼성고등학교장'
const IT = '충남삼성고등학교 IT 디플로마'   // 소속은 디플로마까지만(9/28 사용자 요청, 팀 이름은 넣지 않음)

export const TEAM = [
  {
    name: '남윤수', role: '팀장 · 개발', handle: '@namyunsu',
    mascot: { palette: 'purple', face: 'grin', motion: 'bob' },
    detail: {
      affiliation: IT,
      email: 'namyunsu1001@naver.com',   // 본인 연락처(9/28 요청). 다른 팀원에게는 넣지 않는다
      work: ['프로젝트 총괄·설계', '발음 평가(D-GOP)·음성 모델', '학습 알고리즘(출제·숙달·배치검사)', '배포·운영'],
      awards: [
        { title: '2026 K-AI Contents Award B트랙 대상', by: 'KT genie music 사장상' },
        { title: '제2회 World Invention School EXPO 발명 아이디어·시제품 부문 대상', by: '한국교원단체총연합회장상' },
        { title: '제2회 World Invention School EXPO AI시대 문제해결 챌린지 부문 대상', by: '한국교원단체총연합회장상' },
        { title: '제16회 e-ICON World Contest 고등부 최우수상', by: '한국디지털교육협회장상' },
        { title: '제19회 전국학생창업발명경진대회 환경부 최우수상', by: '지식재산처장상' },
        { title: '제17회 전국 창의적 문제해결능력 경진대회 금상', by: '지식재산처장상' },
        { title: '제11회 4차 산업혁명 AI 영재장학생 선발', by: '한국언론인협회·국제 디지털경제3.0포럼 대표의원 공동명의' },
        { title: '제19회 전국학생창업발명경진대회 창업부 우수상', by: '한국지식재산보호원장상' },
        { title: '제15회 에너지 환경 탐구대회 중고등부 우수상', by: '(사)환경교육센터 이사장상' },
        { title: '제9회 UNIST 청소년 슈퍼컴퓨팅 캠프 우수상', by: 'UNIST 총장상' },
        { title: '제6회 미래바다 아이디어 공모전 우수상', by: '선박해양플랜트연구소장상' },
        { title: '제5회 매일경제·MBN 원더차일드 창의발명대회 동상', by: '매일경제 회장상' },
        { title: '제28회 전국학생통계활용대회 동상' },
        { title: '제6회 AI·SW 학생 동아리 한마당 장려상', by: '충청남도교육감상' },
        { title: '제4회 IT코딩 발명 아이디어·에세이 경진대회 코딩 부문 장려상', by: '행복일자리운동본부 이사장상' },
        { title: '제17회 소외이웃과 함께하는 창의설계 경진대회 입상', by: '나눔과기술 대표상' },
        { title: 'IT 디플로마 최우수상', by: SCHOOL, scope: 'school' },
        { title: '2025 교내 과학발명품 경진대회 금상(1위)', by: SCHOOL, scope: 'school' },
        { title: '2026 교내 청소년 과학 페어 은상(2위)', by: SCHOOL, scope: 'school' },
        { title: '2025 교내 청소년 과학 페어 은상(2위)', by: SCHOOL, scope: 'school' },
      ],
    },
  },
  { name: '황성주', role: 'UI 디자인 · 개발', handle: '@JuHana', detail: { affiliation: IT }, mascot: { palette: 'rose', face: 'wink', motion: 'tilt' } },
  { name: '염우진', role: '개발', handle: '@duadnwls', detail: { affiliation: IT }, mascot: { palette: 'sky', face: 'laugh', motion: 'bounce' } },
  { name: '나현빈', role: '개발', handle: '@Devna08', detail: { affiliation: IT }, mascot: { palette: 'emerald', face: 'glance', motion: 'wiggle' } },
  { name: '최윤건', role: '타도마 기능 개발', detail: { affiliation: '충남삼성고등학교 공학 디플로마' }, mascot: { palette: 'amber', face: 'surprised', motion: 'float' } },
]

export const TEAM_ORG = '충남삼성고등학교 IT·공학 디플로마 학생들'
export const AWARD = 'K-AI 공모전 B트랙 중고등부 대상 수상작'
export const REPO_URL = 'https://github.com/n1a2m3y4u5n/liplab'
// 문의 연락처(9/28 사용자 지정). 바꾸려면 이 한 줄만 고친다.
export const CONTACT_EMAIL = 'namyunsu1001@naver.com'
