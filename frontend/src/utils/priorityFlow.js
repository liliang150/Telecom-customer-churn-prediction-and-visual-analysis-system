export function buildPriorityFlow(customers, visibleRows = 6) {
  const items = [...customers].sort((a, b) => b.probability - a.probability)
  const shouldFlow = items.length > visibleRows
  return {
    items,
    shouldFlow,
    sequences: shouldFlow ? [items, items] : [items],
  }
}

export function buildPriorityWindow(items, scrollTop, visibleRows = 6, overscan = 2) {
  const rowHeight = 48
  const rowCount = items.length > visibleRows ? items.length * 2 : items.length
  const start = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan)
  const end = Math.min(rowCount, Math.ceil((scrollTop + visibleRows * rowHeight) / rowHeight) + overscan)
  const rows = []
  for (let index = start; index < end; index += 1) {
    rows.push({ customer: items[index % items.length], index, offset: index * rowHeight })
  }
  return { rows, totalHeight: rowCount * rowHeight }
}

export function resolvePriorityScrollTop(preciseScrollTop, appliedScrollTop, actualScrollTop) {
  return Math.abs(actualScrollTop - appliedScrollTop) > 0.01 ? actualScrollTop : preciseScrollTop
}

export function nextPriorityScrollTop(scrollTop, sequenceHeight, elapsedMs, durationMs = 28000) {
  if (sequenceHeight <= 0 || elapsedMs <= 0) return scrollTop
  const next = scrollTop + sequenceHeight * (elapsedMs / durationMs)
  return next >= sequenceHeight ? next % sequenceHeight : next
}
