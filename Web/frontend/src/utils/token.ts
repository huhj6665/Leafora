// JWT token 的集中管理，避免散落到各组件。
const TOKEN_KEY = 'tld_access_token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

// 解码 JWT payload（仅解码，不做签名校验——校验由后端完成）。
export function decodeTokenPayload(token: string): Record<string, unknown> | null {
  try {
    const part = token.split('.')[1]
    if (!part) return null
    const base64 = part.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')
    const json = decodeURIComponent(
      atob(padded)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join(''),
    )
    return JSON.parse(json)
  } catch {
    return null
  }
}

// 脱敏显示 token（前 10 位 + …），禁止显示完整 token。
export function maskToken(token: string): string {
  if (!token) return '无'
  return token.length > 12 ? `${token.slice(0, 10)}…` : token
}
