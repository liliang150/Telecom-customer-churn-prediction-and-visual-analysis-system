import { describe, expect, it } from 'vitest'

async function getBuilder() {
  const module = await import('../src/utils/priorityFlow.js').catch(() => ({}))
  expect(module.buildPriorityFlow).toBeTypeOf('function')
  return module.buildPriorityFlow
}

async function getScroller() {
  const module = await import('../src/utils/priorityFlow.js').catch(() => ({}))
  expect(module.nextPriorityScrollTop).toBeTypeOf('function')
  return module.nextPriorityScrollTop
}

function customers(probabilities) {
  return probabilities.map((probability, index) => ({ customer_id: `${index + 1}`, probability }))
}

describe('优先关注客户流动列表', () => {
  it('按流失概率降序排列且不修改原数组', async () => {
    const build = await getBuilder()
    const original = customers([0.42, 0.96, 0.71, 0.88, 0.67, 0.55, 0.49])

    const result = build(original, 6)

    expect(result.items.map((item) => item.probability)).toEqual([0.96, 0.88, 0.71, 0.67, 0.55, 0.49, 0.42])
    expect(original.map((item) => item.probability)).toEqual([0.42, 0.96, 0.71, 0.88, 0.67, 0.55, 0.49])
  })

  it('客户数超过可视行数时生成两段相同列表用于无缝循环', async () => {
    const build = await getBuilder()
    const result = build(customers([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]), 6)

    expect(result.shouldFlow).toBe(true)
    expect(result.sequences).toHaveLength(2)
    expect(result.sequences[0]).toEqual(result.sequences[1])
  })

  it('客户数未超过可视行数时保持静态单列表', async () => {
    const build = await getBuilder()
    const result = build(customers([0.9, 0.8, 0.7, 0.6, 0.5, 0.4]), 6)

    expect(result.shouldFlow).toBe(false)
    expect(result.sequences).toEqual([result.items])
  })

  it('从用户手动滚动的位置继续自动滚动', async () => {
    const next = await getScroller()

    expect(next(120, 400, 7000, 28000)).toBe(220)
  })

  it('滚过第一段末尾后按序列高度无缝回绕', async () => {
    const next = await getScroller()

    expect(next(350, 400, 7000, 28000)).toBe(50)
  })

  it('原生滚动位置被取整时仍从内部精确位置持续推进', async () => {
    const module = await import('../src/utils/priorityFlow.js')
    expect(module.resolvePriorityScrollTop).toBeTypeOf('function')
    const next = await getScroller()
    let precise = 0.8

    for (let frame = 0; frame < 10; frame += 1) {
      const current = module.resolvePriorityScrollTop(precise, 0.8, 0.8)
      precise = next(current, 384.4, 7)
    }

    expect(precise).toBeGreaterThan(1.5)
  })

  it('检测到用户手动滚动时改用实际滚动位置', async () => {
    const module = await import('../src/utils/priorityFlow.js')
    expect(module.resolvePriorityScrollTop).toBeTypeOf('function')

    expect(module.resolvePriorityScrollTop(0.8786, 0.8, 160)).toBe(160)
  })

  it('数千客户仅渲染可视行和缓冲行', async () => {
    const module = await import('../src/utils/priorityFlow.js')
    expect(module.buildPriorityWindow).toBeTypeOf('function')
    const items = customers(Array.from({ length: 3000 }, (_, index) => (index % 100) / 100))

    const result = module.buildPriorityWindow(items, 0, 6, 2)

    expect(result.rows).toHaveLength(8)
    expect(result.totalHeight).toBe(3000 * 2 * 48)
    expect(result.rows[0].customer.customer_id).toBe('1')
  })

  it('第二段虚拟循环从首位客户重新开始', async () => {
    const module = await import('../src/utils/priorityFlow.js')
    expect(module.buildPriorityWindow).toBeTypeOf('function')
    const items = customers([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3])

    const result = module.buildPriorityWindow(items, 7 * 48, 6, 0)

    expect(result.rows[0].index).toBe(7)
    expect(result.rows[0].customer.customer_id).toBe('1')
    expect(result.rows).toHaveLength(6)
  })
})
