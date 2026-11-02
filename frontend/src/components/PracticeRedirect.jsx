import LegacyRedirect from './LegacyRedirect'
import useStore from '../store/useStore'
import { learnHref, loadLastTrack } from '../lib/lastTrack'
export default function PracticeRedirect() {
  const uid = useStore((s) => s.user?.id)
  return <LegacyRedirect to={learnHref(loadLastTrack(uid), 'free')} />
}
