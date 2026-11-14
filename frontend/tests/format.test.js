import { describe, expect, it } from 'vitest'
import { displaySourceName, formatNumber, formatPercent, riskLevel, riskTagType } from '../src/utils/format'

describe('risk and formatting helpers', () => {
  it('uses the model risk thresholds', () => {
    expect(riskLevel(0.7)).toBe('高风险')
    expect(riskLevel(0.4)).toBe('中风险')
    expect(riskLevel(0.399)).toBe('低风险')
  })

  it('maps risk levels to restrained semantic tags', () => {
    expect(riskTagType('高风险')).toBe('danger')
    expect(riskTagType('中风险')).toBe('warning')
    expect(riskTagType('低风险')).toBe('success')
  })

  it('formats ratios as percentages and preserves empty values', () => {
    expect(formatPercent(0.2734)).toBe('27.3%')
    expect(formatPercent(0.2734, 2)).toBe('27.34%')
    expect(formatPercent(null)).toBe('—')
  })

  it('formats numbers with fixed precision when requested', () => {
    expect(formatNumber(1234.5)).toBe('1,235')
    expect(formatNumber(0.81234, 3)).toBe('0.812')
    expect(formatNumber(undefined)).toBe('—')
  })

  it('restores the original training filename and falls back to train.csv', () => {
    expect(displaySourceName('20261103091530123456_客户训练数据.xlsx')).toBe('客户训练数据.xlsx')
    expect(displaySourceName('train.csv')).toBe('train.csv')
    expect(displaySourceName(undefined)).toBe('train.csv')
  })
})
