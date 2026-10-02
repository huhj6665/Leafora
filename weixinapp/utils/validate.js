/** 与手机号身份及密码页面共用的纯函数校验。 */
const PHONE_RE = /^1[3-9]\d{9}$/
const CODE_RE = /^\d{6}$/

function isValidPhone(phone) {
  return PHONE_RE.test(String(phone || '').trim())
}

function isValidCode(code) {
  return CODE_RE.test(String(code || '').trim())
}

function isValidPassword(password) {
  return typeof password === 'string' && password.length >= 6 && password.length <= 128 &&
    /[a-zA-Z]/.test(password) && /\d/.test(password)
}

// 仅为兼容旧测试/调用保留；正式入口不再使用用户名身份。
function isValidUsername(username) {
  const value = String(username || '').trim()
  return value.length >= 1 && value.length <= 64
}

module.exports = {
  isValidPhone,
  isValidCode,
  isValidPassword,
  isValidUsername,
  PHONE_RE,
  CODE_RE,
}
