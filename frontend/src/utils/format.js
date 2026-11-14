export function riskLevel(probability) {
  if (probability >= 0.7) return '高风险'
  if (probability >= 0.4) return '中风险'
  return '低风险'
}

export function riskTagType(level) {
  return { 高风险: 'danger', 中风险: 'warning', 低风险: 'success' }[level] || 'info'
}

export function formatPercent(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return `${(Number(value) * 100).toFixed(digits)}%`
}

export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function displaySourceName(savedName) {
  return savedName?.replace(/^\d{20}_/, '') || 'train.csv'
}

export function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

export function featureValue(value) {
  if (value === null || value === undefined || value === '') return '缺失'
  return typeof value === 'number' ? formatNumber(value, Math.abs(value) < 10 ? 2 : 0) : String(value)
}
