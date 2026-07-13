import { useCallback, useEffect, useState } from 'react'
import { curriculumAPI } from '../api'

const clampPercent = (value) => Math.min(100, Math.max(0, Number(value) || 0))

export function useStageStatus(stage) {
  const [stageInfo, setStageInfo] = useState(null)

  const refreshStage = useCallback(async () => {
    try {
      const data = await curriculumAPI.getStages()
      setStageInfo((data?.stages || []).find((item) => item.stage === stage) || null)
    } catch {
      // 학습 콘텐츠 자체는 진행할 수 있도록 상태 조회 실패를 치명적으로 취급하지 않는다.
    }
  }, [stage])

  useEffect(() => { refreshStage() }, [refreshStage])

  return { stageInfo, setStageInfo, refreshStage }
}

export function StageProgressBar({ stageInfo, compact = false }) {
  const percent = clampPercent(stageInfo?.progress_percent)
  const displayPercent = Math.round(percent)
  const requirement = stageInfo?.requirement

  return (
    <div className={compact ? 'mt-2' : ''}>
      <div className={`flex items-center gap-2 ${compact ? '' : 'mb-1.5'}`}>
        {!compact && <span className="text-sm text-gray-600">단계 진행률</span>}
        <div className="flex-1 bg-gray-200 rounded-full h-2 overflow-hidden" role="progressbar"
          aria-label={`${stageInfo?.stage ?? ''}단계 진행률`} aria-valuemin="0" aria-valuemax="100" aria-valuenow={displayPercent}>
          <div
            className={`h-full rounded-full transition-all duration-500 ${stageInfo?.mastered ? 'bg-green-500' : 'bg-primary-500'}`}
            style={{ width: `${percent}%` }}
          />
        </div>
        <span className={`${compact ? 'text-[11px]' : 'text-sm'} min-w-9 text-right font-semibold ${stageInfo?.mastered ? 'text-green-600' : 'text-primary-600'}`}>
          {displayPercent}%
        </span>
      </div>
      {!compact && requirement && (
        <p className="text-xs text-gray-500">
          {stageInfo?.attempts || 0}/{requirement.min_attempts}{requirement.attempt_unit}
          {' · '}{requirement.metric_label} {stageInfo?.mastery_score || 0}%
        </p>
      )}
    </div>
  )
}

export function StageHeader({
  title,
  subtitle,
  stageInfo,
  onExit,
  exitLabel = '나가기',
  maxWidthClass = 'max-w-5xl',
  children,
}) {
  const requirement = stageInfo?.requirement
  const criterionTitle = requirement?.next_stage
    ? `${requirement.next_stage}단계 해금`
    : '최종 단계 완료'

  return (
    <header className="bg-white shadow-sm border-b border-gray-200 shrink-0">
      <div className={`${maxWidthClass} mx-auto px-4 sm:px-6 py-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between`}>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          {subtitle && <p className="text-sm text-gray-500">{subtitle}</p>}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2 sm:gap-3">
          {children}
          {requirement && (
            <span className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-800">
              <b>{criterionTitle}</b> · {requirement.criterion}
            </span>
          )}
          <button onClick={onExit} className="whitespace-nowrap text-gray-500 hover:text-gray-800 text-sm">
            ✕ {exitLabel}
          </button>
        </div>
      </div>
    </header>
  )
}
