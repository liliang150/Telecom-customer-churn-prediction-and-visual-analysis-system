export function unwrapEnvelope(payload) {
  if (!payload || payload.code !== 200) {
    throw new Error(payload?.message || '服务响应异常')
  }
  return payload.data
}

export function isUnauthorized(error) {
  return error?.response?.status === 401
}

export function getErrorMessage(error) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join('；')
  return error?.message || '操作失败，请稍后重试'
}
