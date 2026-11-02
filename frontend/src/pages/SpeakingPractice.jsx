import useSpeakingLesson from '../hooks/useSpeakingLesson'
import SpeakingLessonView from '../components/speaking/SpeakingLessonView'
import LoadingScreen from '../components/LoadingScreen'

export default function SpeakingPractice() {
  const lesson = useSpeakingLesson()
  if (lesson.pending || !lesson.introDone) return <LoadingScreen variant="brand" track="language" />
  return <SpeakingLessonView {...lesson} />
}
