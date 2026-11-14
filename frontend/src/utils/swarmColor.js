function quantile(sortedValues, probability) {
  const position = (sortedValues.length - 1) * probability
  const lower = Math.floor(position)
  const upper = Math.ceil(position)
  if (lower === upper) return sortedValues[lower]
  return sortedValues[lower] + (sortedValues[upper] - sortedValues[lower]) * (position - lower)
}

export function normalizeSwarmColors(items) {
  const groups = new Map()
  for (const item of items) {
    if (!groups.has(item.feature)) groups.set(item.feature, [])
    groups.get(item.feature).push(item.value)
  }

  const ranges = new Map()
  for (const [feature, values] of groups) {
    const sorted = [...values].sort((a, b) => a - b)
    let low = quantile(sorted, 0.05)
    let high = quantile(sorted, 0.95)
    if (high === low && sorted[0] !== sorted[sorted.length - 1]) {
      low = sorted[0]
      high = sorted[sorted.length - 1]
    }
    ranges.set(feature, { low, high })
  }

  return items.map((item) => {
    const { low, high } = ranges.get(item.feature)
    const colorValue = high === low ? 0.5 : Math.min(1, Math.max(0, (item.value - low) / (high - low)))
    return { ...item, colorValue }
  })
}
