import { useEffect, useRef, useState } from 'react'
import { curriculumAPI } from '../api'
import { EFFORT_POINTS, EFFORT_ANCHORS, newSessionId } from '../lib/measurement'
import { buildRenderLog, hasWebGL } from '../lib/pilotBattery'

/**
 * 레슨 끝 정신적 노력 한 문항(C14, Paas 9점) — 레슨 완료 화면에 붙인다. 답하지 않아도 된다.
 * 레슨 세션마다 한 번 서버에 남긴다(backend/mental_effort.py): 고르면 answered, '건너뛰기'는 skipped, 답하지 않고 화면을 떠나면 left.
 * 적응 규칙은 없다(기록만). 고른 뒤에도 다른 칸을 누르면 바꿀 수 있다.
 * 척도는 1(아주 아주 조금)~9(아주 아주 많이) 칸을 왼쪽에서 오른쪽으로 점점 높아지는 막대로 그려 글을 읽지 않아도 크기를 알 수 있게 한다.
 *
 * props: lessonKind('viseme' | 'word' | 'sentence' | 'closure' | 'review'), stage(읽기 단계, 복습은 없음), nItems, accuracy(0~1)
 */
export default function EffortCheck({ lessonKind, stage = null, nItems = null, accuracy = null }) {
  const [sessionId] = useState(() => newSessionId())
  const [rating, setRating] = useState(null)
  const [state, setState] = useState('ask')   // ask | answered | skipped
  const doneRef = useRef(false)
  const metaRef = useRef({})
  // 그 레슨의 기기·렌더링 요약(V20): 레슨 시작부터의 프레임 지연과 화면 크기·화소 비율 등(GPU 이름·사용자 에이전트 원문은 보내지 않음)
  const [renderLog] = useState(() => buildRenderLog({ scope: 'lesson', webgl: hasWebGL() }))
  metaRef.current = { session_id: sessionId, lesson_kind: lessonKind, stage, n_items: nItems, accuracy, render_log: renderLog }

  // 답하지 않고 떠나면 'left'로 남긴다(응답률 분모). 서버는 answered를 left로 덮지 않는다.
  useEffect(() => () => {
    if (!doneRef.current) curriculumAPI.lessonEffort({ ...metaRef.current, response: 'left' }).catch(() => {})
  }, [])

  const send = (body) => { curriculumAPI.lessonEffort({ ...metaRef.current, ...body }).catch(() => {}) }
  const pick = (v) => {
    doneRef.current = true
    setRating(v)
    setState('answered')
    send({ rating: v })
  }
  const skip = () => {
    doneRef.current = true
    setState('skipped')
    send({ response: 'skipped' })
  }

  if (state === 'skipped') return null
  return (
    <section aria-labelledby="effort-q" className="flex w-full max-w-[640px] flex-col gap-3 rounded-18 border-2 border-line bg-white px-4 py-3.5 lg:px-5 lg:py-4">
      <div className="flex items-start justify-between gap-3">
        <p id="effort-q" className="text-[15px] font-bold leading-figma text-ink lg:text-[16px]">
          {state === 'answered' ? '고마워요. 기록했어요.' : '이번 레슨, 머리를 얼마나 많이 썼나요?'}
        </p>
        {state === 'ask' && (
          <button type="button" onClick={skip} className="shrink-0 text-[13px] font-bold text-ink-faint underline-offset-2 hover:underline">
            건너뛰기
          </button>
        )}
      </div>
      <div role="radiogroup" aria-labelledby="effort-q" className="flex items-end gap-1 lg:gap-1.5">
        {EFFORT_POINTS.map((v) => {
          const on = rating === v
          return (
            <button key={v} type="button" role="radio" aria-checked={on} onClick={() => pick(v)}
              aria-label={`${v}점${EFFORT_ANCHORS[v] ? ` (${EFFORT_ANCHORS[v]})` : ''}`}
              className="group flex min-w-0 flex-1 flex-col items-center gap-1">
              <span className={`w-full rounded-[6px] transition-colors ${on ? 'bg-track' : 'bg-fill-strong group-hover:bg-primary-300'}`}
                style={{ height: `${10 + v * 4}px` }} />
              <span className={`text-[12px] font-bold leading-none ${on ? 'text-track' : 'text-ink-muted'}`}>{v}</span>
            </button>
          )
        })}
      </div>
      <div className="flex justify-between text-[11px] font-bold text-ink-faint lg:text-[12px]">
        <span>{EFFORT_ANCHORS[1]}</span>
        <span>{EFFORT_ANCHORS[5]}</span>
        <span>{EFFORT_ANCHORS[9]}</span>
      </div>
    </section>
  )
}
