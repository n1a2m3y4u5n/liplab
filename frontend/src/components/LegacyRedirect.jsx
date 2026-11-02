import { Navigate, useLocation } from 'react-router-dom'
import { legacyTarget } from '../lib/legacyRoutes'
export default function LegacyRedirect({ to }) {
  const { search } = useLocation()
  return <Navigate to={legacyTarget(to, search)} replace />
}
