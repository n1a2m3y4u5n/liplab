export function legacyTarget(to, search = '') {
  const url = new URL(to, 'https://liplab.local')
  const original = new URLSearchParams(search)
  const destinationKeys = new Set(url.searchParams.keys())
  for (const [key, value] of original) if (!destinationKeys.has(key)) url.searchParams.append(key, value)
  return url.pathname + url.search + url.hash
}
