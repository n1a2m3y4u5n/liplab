import LingCheck from './LingCheck'
import AxDrill from './AxDrill'
import WordId from './WordId'
import SentenceTask from './SentenceTask'
import NoiseStage from './NoiseTest'
import ConvoTask from './ConvoTask'

/**
 * 단계 응답의 mode → 과제 컴포넌트. 단계 레슨은 4단계(noise)를 검사 안내가 있는 NoiseStage로 열고,
 * 오늘의 듣기·연습은 TRAIN_TASK(4단계도 훈련 문장만, SentenceTask noisy)를 쓴다.
 */
export const STAGE_TASK = { ling: LingCheck, ax: AxDrill, word_id: WordId, sentence: SentenceTask, noise: NoiseStage, convo: ConvoTask }
export const TRAIN_TASK = { ...STAGE_TASK, noise: SentenceTask }
