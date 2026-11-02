import LearnPanel from '../components/viseme/LearnPanel'
import QuizPanel from '../components/viseme/QuizPanel'
import { INTRO_MS } from '../components/viseme/VisemeParts'
import useStore from '../store/useStore'
import { loadLastTrack, learnHref } from '../lib/lastTrack'
import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { curriculumAPI } from '../api'
import LoadingScreen from '../components/LoadingScreen'
import { LoadFailed } from '../components/ErrorScreen'

/**
 * 1단계 · 입모양 인지 (Viseme Literacy)
 * ------------------------------------------------------------------
 * 지금까지 앱은 입모양 15종을 '아바타 애니메이션'에만 썼다. 이 페이지는 그 입모양을
 * 실제로 '가르치는' 기초 단계다. 인지퀴즈(어느 그룹인지 맞히기) + 학습 자료(10그룹 훑기).
 * 핵심 교육: 어떤 소리는 잘 보이고(모음·양순), 어떤 소리는 똑같이 보인다(동구형이음).
 *
 * /learn/viseme 는 독화 레슨 공통 템플릿(핸드오프 §4-03 — 91:12 · 94:98 · 94:140 · 93:12, 모바일 235:34 · 235:71)
 * 으로 인지퀴즈를 바로 연다. 예전 상단 헤더·학습/퀴즈 탭은 Figma에 없어 뺐다.
 * 학습 자료(LearnPanel: 10그룹·웹캠·성도 실험실·동구형이음)는 Figma 프레임이 없어 지우지 않고
 * /learn/viseme?tab=learn (또는 ?v=그룹번호)로 연다 — 연습 탭의 '입모양 교실' 카드가 이리로 온다.
 *
 * 퀴즈는 LipSyncPlayer3D를 쓰지 않는다 — 그 컴포넌트는 하단에 'Viseme N'을 노출해
 * 정답이 새기 때문. 대신 MouthAvatar로 오버레이 없이 입모양만 보여준다. 고르기 문항은 입모양 하나를 되풀이하고,
 * 7~12번 가운데 두 자리의 '같은지 다른지'(AX) 문항은 음절 둘을 차례로 말한다(lib/visemeAx). 한 아바타를 계속 써서
 * 문항 유형이 바뀌어도 WebGL 컨텍스트를 다시 만들지 않는다.
 */

// 보임 정도 배지 — 의미색 토큰(잘 보임=good · 보통=warn · 거의 안 보임=회색)
export default function VisemeLiteracy() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  // 학습 자료는 ?tab=learn 또는 ?v=그룹(약점 입모양 바로가기)일 때만 — 기본은 레슨(인지퀴즈)
  const learnMode = params.get('tab') === 'learn' || params.get('v') != null
  // 나가기: 연습 탭 '입모양 교실' 카드(?tab=learn, PracticeHub)로 들어왔으면 연습 탭으로, 그 밖(레슨·약점 바로가기 ?v=)은 학습 경로로
  const exitTo = params.get('tab') === 'learn' ? learnHref(loadLastTrack(useStore.getState().user?.id) === 'speak' ? 'speak' : 'read', 'res') : '/learn/path'
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [introDone, setIntroDone] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    curriculumAPI.getVisemeLessons()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
    const t = setTimeout(() => setIntroDone(true), INTRO_MS)
    return () => clearTimeout(t)
  }, [load])

  // 레슨 시작 전 = 독화 트랙 로딩(223:30 / 모바일 243:81). 학습 자료는 레슨이 아니라 기본 로딩(256:34).
  if (loading) return learnMode ? <LoadingScreen /> : <LoadingScreen variant="brand" track="perception" />
  if (!learnMode && !introDone) return <LoadingScreen variant="brand" track="perception" />
  if (!data) return <LoadFailed message="콘텐츠를 가져오지 못했어요." onRetry={load} onExit={() => navigate(exitTo)} />

  if (learnMode) {
    return (
      <div className="min-h-[100dvh] bg-page">
        <main className="mx-auto max-w-5xl px-[18px] pb-12 pt-[18px] lg:px-6 lg:pt-7">
          <button type="button" onClick={() => navigate(exitTo)} aria-label="나가기" className="mb-5 block">
            <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 lg:size-9" />
          </button>
          <LearnPanel data={data} />
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-[100dvh] bg-page">
      <QuizPanel data={data} />
    </div>
  )
}
