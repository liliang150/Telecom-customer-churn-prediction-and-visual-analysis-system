import { describe, expect, it } from 'vitest'

async function getNormalizer() {
  const module = await import('../src/utils/swarmColor.js').catch(() => ({}))
  expect(module.normalizeSwarmColors).toBeTypeOf('function')
  return module.normalizeSwarmColors
}

describe('SHAP 蜂群图颜色归一化', () => {
  it('按每个特征独立归一化，避免量纲大的特征主导颜色', async () => {
    const normalize = await getNormalizer()
    const result = normalize([
      { feature: '小量纲', value: 0 },
      { feature: '小量纲', value: 50 },
      { feature: '小量纲', value: 100 },
      { feature: '大量纲', value: 0 },
      { feature: '大量纲', value: 500 },
      { feature: '大量纲', value: 1000 },
    ])

    expect(result.map((item) => item.colorValue)).toEqual([0, 0.5, 1, 0, 0.5, 1])
  })

  it('使用 5%–95% 分位数范围并截断极端值', async () => {
    const normalize = await getNormalizer()
    const values = Array.from({ length: 100 }, (_, index) => index).concat(10000)
    const result = normalize(values.map((value) => ({ feature: '费用', value })))

    expect(result[0].colorValue).toBe(0)
    expect(result[50].colorValue).toBe(0.5)
    expect(result[99].colorValue).toBe(1)
    expect(result[100].colorValue).toBe(1)
  })

  it('分位数范围退化时回退到该特征的实际范围', async () => {
    const normalize = await getNormalizer()
    const values = Array.from({ length: 100 }, () => 0).concat(1)
    const result = normalize(values.map((value) => ({ feature: '稀疏特征', value })))

    expect(result[0].colorValue).toBe(0)
    expect(result[100].colorValue).toBe(1)
  })

  it('常量特征使用中间色并保留原始值', async () => {
    const normalize = await getNormalizer()
    const result = normalize([{ feature: '常量', value: 7 }, { feature: '常量', value: 7 }])

    expect(result.map((item) => item.colorValue)).toEqual([0.5, 0.5])
    expect(result.map((item) => item.value)).toEqual([7, 7])
  })
})
