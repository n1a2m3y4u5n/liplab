import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listenAPI } from '../api'
import { stopAll } from '../lib/listenAudio'
import ListenBlocks from '../components/listen/ListenBlocks'
import ListenComplete from '../components/listen/ListenComplete'
import ListenFrame from '../components/listen/ListenFrame'
import SentenceTask from '../components/listen/SentenceTask'
import StateCard from '../components/listen/StateCard'
import WordId from '../components/listen/WordId'
import { Skeleton } from '../components/listen/ui'

/**
 * 듣기 복습: /listen/review (GET /api/listen/review → {words:[{target, options, key}], sentences:[{id, text, key}], n}).
 * 지난번에 놓친 낱말을 먼저 고르고, 놓친 문장을 받아쓴다. 답은 POST /api/listen/answer에 practice_mode='review'를 붙여 보내
 * 복습 간격만 조정하고 단계 숙달에는 넣지 않는다(백엔드 계약). 복습 탭의 '듣기 복습' 카드에서 들어온다.
 */
const EXTRA = { practice_mode: 'review' }

export default function ListenReview() {
  const navigate = useNavigate()
  const [rev, setRev] = useState(null)
  const [err, setErr] = useState(null)   // 'missing' | 'network'
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let on = true
    setRev(null)
    setErr(null)
    listenAPI.review().then((r) => { if (on) setRev({ words: r?.words || [], sentences: r?.sentences || [] }) })
      .catch((e) => { if (on) setErr(e?.response?.status === 404 ? 'missing' : 'network') })
    return () => { on = false }
  }, [nonce])
  const exit = () => { stopAll(); navigate('/review') }

  const blocks = useMemo(() => {
    if (!rev) return []
    const out = []
    if (rev.words.length) out.push({ key: 'words', title: '낱말 복습', kind: 'words', data: { items: rev.words, guide: '지난번에 놓친 낱말이에요. 듣고 골라 보세요.' } })
    if (rev.sentences.length) out.push({ key: 'sentences', title: '문장 복습', kind: 'sentences', data: { items: rev.sentences } })
    return out
  }, [rev])

  return (
    <ListenFrame kicker="듣기 복습" onExit={exit} exitAria="나가기, 복습 탭으로">
      {(ctx) => (
        err ? (
          <StateCard title={err === 'missing' ? '듣기 복습을 준비하고 있어요' : '복습할 소리를 불러오지 못했어요'}
            body={err === 'missing' ? '곧 열려요.' : '인터넷 연결을 확인하고 다시 불러와 주세요.'}
            actions={err === 'missing' ? [{ label: '복습 탭으로', onClick: exit }] : [{ label: '다시 불러오기', onClick: () => setNonce((n) => n + 1) }, { label: '복습 탭으로', onClick: exit }]} />
        ) : !rev || !ctx.voiceList ? <Skeleton /> : blocks.length === 0 ? (
          <StateCard title="다시 들을 소리가 없어요" body="소리 듣기에서 놓친 낱말과 문장이 며칠 뒤 여기에 모여요." actions={[{ label: '복습 탭으로', onClick: exit }]} />
        ) : (
          <ListenBlocks active={ctx.active} onProgress={ctx.onProgress}
            blocks={blocks.map((b) => ({
              ...b,
              run: ({ onDone }) => (b.kind === 'words'
                ? <WordId data={b.data} settings={ctx.settings} voices={ctx.voices} onProgress={ctx.onProgress} finish={{ onDone }} active={ctx.active}
                  answerExtra={EXTRA} metaLabel="다시 듣는 낱말" />
                : <SentenceTask data={b.data} settings={ctx.settings} voices={ctx.voices} onProgress={ctx.onProgress} onExit={exit} exitLabel="복습 탭으로"
                  finish={{ onDone }} active={ctx.active} answerExtra={EXTRA} metaLabel="다시 듣는 문장" />),
            }))}
            renderSummary={(results) => (
              <ListenComplete title="듣기 복습을 마쳤어요" sub="다시 놓친 소리는 며칠 뒤에 한 번 더 나와요."
                stats={results.filter((x) => x.result).map(({ block, result }) => ({ label: block.title, value: `${result.c} / ${result.n}`, main: block.kind === 'words' }))}
                primary={{ label: '복습 탭으로', onClick: exit }} />
            )} />
        )
      )}
    </ListenFrame>
  )
}
