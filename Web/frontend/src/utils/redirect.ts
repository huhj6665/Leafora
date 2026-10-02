const DEFAULT_AUTH_REDIRECT = '/platform/overview'

export function getSafeInternalRedirect(value: unknown, fallback = DEFAULT_AUTH_REDIRECT): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) {
    return fallback
  }

  let decoded = value
  try {
    decoded = decodeURIComponent(value)
  } catch {
    return fallback
  }

  if (decoded.startsWith('//') || decoded.includes('\\') || /[\u0000-\u001f]/.test(decoded)) {
    return fallback
  }

  const target = new URL(value, window.location.origin)
  if (target.origin !== window.location.origin) {
    return fallback
  }

  return `${target.pathname}${target.search}${target.hash}`
}
