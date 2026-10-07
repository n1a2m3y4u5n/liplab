import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { listenAPI } from '../api'
import { stopAll } from '../lib/listenAudio'
import { completeActions } from '../lib/listenFlow'
import ListenFrame from '../components/listen/ListenFrame'
import StateCard from '../components/listen/StateCard'
import { Skeleton } from '../components/listen/ui'
import WordTest from '../components/listen/WordTest'
import { STAGE_TASK } from '../components/listen/tasks'

/**
 * 소리 듣기(청능훈련) 단계 레슨: /learn/listening?stage=N (backend listen_curriculum, docs/auditory-training-design.md).
 * 틀(X · 진행바 · 소리 크기 맞추기)은 components/listen/ListenFrame, 과제는 components/listen/의 과제 컴포넌트다.
 * 단계마다 과제가 다르다: 0 Ling 점검, 1 같다·다르다, 2 낱말 고르기, 3 조용한 문장 받아쓰기, 4 소음 속 문장(+검사), 5 대화 듣기.
 * 같은 과제를 연습 모드(/listen/practice/:mode), 오늘의 듣기(/listen/today), 듣기 복습(/listen/review)도 쓴다. 이 화면은 묶음 끝 버튼을
 * 단계용(lib/listenFlow.completeActions: 숙달하면 다음 단계로, 아니면 한 묶음 더)으로 넘긴다.
 * 소리는 서버가 미리 합성한 음성이고(lib/listenAudio), 받지 못한 글은 '아직 들을 수 없음'으로 알리고 세지 않고 넘긴다.
 * 키보드: 스페이스 = 듣기, 숫자 = 보기, Enter = 확인·계속하기(lib/listenView).
 */
export default function ListeningPractice() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const stage = Math.max(0, Math.min(5, Number(params.get('stage') ?? 0) || 0))
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let on = true
    setData(null)
    setErr(null)
    listenAPI.getStage(stage).then((d) => { if (on) setData(d) }).catch(() => { if (on) setErr(true) })
    return () => { on = false }
  }, [stage, nonce])
  const exit = () => { stopAll(); navigate('/learn/path?track=listen') }
  const reload = () => { stopAll(); setNonce((n) => n + 1) }
  const goStage = (n) => { stopAll(); navigate(`/learn/listening?stage=${n}`) }
  const finish = { actions: (r) => completeActions({ stage, mastered: r.mastered, reload, onExit: exit, onStage: goStage }) }

  const Task = data ? STAGE_TASK[data.mode] : null
  const wordTest = stage === 2 && params.get('wordtest') === '1'
  return (
    <ListenFrame key={stage} kicker={`소리 듣기 · ${stage + 1}단계${data?.title ? ` ${data.title}` : ''}`} onExit={exit} exitAria="나가기, 학습 경로로">
      {({ settings, voices, voiceList, onProgress, active }) => (
        err ? (
          <StateCard title="단계를 불러오지 못했어요" body="인터넷 연결을 확인하고 다시 불러와 주세요."
            actions={[{ label: '다시 불러오기', onClick: reload }, { label: '학습 경로로', onClick: exit }]} />
        ) : !data || !voiceList ? (
          <Skeleton />
        ) : data.status === 'locked' ? (
          <StateCard title="이 단계는 아직 잠겨 있어요" body="앞 단계를 숙달하면 열려요. 학습 경로에서 바로 앞 단계를 이어 하거나 건너뛸 수 있어요."
            actions={[{ label: '학습 경로로', onClick: exit }]} />
        ) : !Task ? (
          <StateCard title="이 단계를 열 수 없어요" actions={[{ label: '학습 경로로', onClick: exit }]} />
        ) : wordTest ? (
          <WordTest settings={settings} voices={voices} onProgress={onProgress} onExit={exit} active={active} />
        ) : (
          <Task key={`${stage}:${nonce}`} data={data} settings={settings} voices={voices} onProgress={onProgress} onExit={exit} finish={finish}
            reload={reload} noisy={data.mode === 'noise'} active={active} />
        )
      )}
    </ListenFrame>
  )
}
