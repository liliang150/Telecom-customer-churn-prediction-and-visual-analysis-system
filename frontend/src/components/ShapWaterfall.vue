<script setup>
import { computed } from 'vue'
import EChart from './EChart.vue'
import { featureValue } from '../utils/format'

const props = defineProps({
  features: { type: Array, default: () => [] },
  baseValue: { type: Number, default: null },
  height: { type: String, default: '330px' },
  loading: Boolean,
  error: { type: String, default: '' },
})

const option = computed(() => {
  const items = props.features || []
  let running = Number(props.baseValue ?? 0)
  const rows = items.map((item) => {
    const before = running
    running += Number(item.shap_value || 0)
    return { ...item, before, after: running }
  })
  const values = rows.flatMap((row) => [row.before, row.after])
  const minValue = Math.min(0, ...values)
  const maxValue = Math.max(0, ...values)
  const span = Math.max(maxValue - minValue, Math.abs(maxValue), Math.abs(minValue), 0.1)
  const labelX = maxValue + span * 0.1
  const colors = { positive: '#d94b4b', negative: '#367bc5' }

  return {
    grid: { left: 142, right: 24, top: 16, bottom: 36 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const row = rows[params[0]?.dataIndex]
        if (!row) return ''
        return `<strong>${row.feature}</strong><br/>特征值：${featureValue(row.feature_value)}<br/>SHAP 贡献：<span style="color:${row.shap_value >= 0 ? colors.positive : colors.negative}">${row.shap_value >= 0 ? '+' : ''}${Number(row.shap_value).toFixed(4)}</span>`
      },
    },
    xAxis: {
      type: 'value', min: minValue - span * 0.08, max: labelX + span * 0.32,
      axisLabel: { color: '#7a8a97', fontSize: 11, formatter: (value) => Number(value).toFixed(2) },
      splitLine: { lineStyle: { color: '#edf0f2' } }, axisLine: { show: false }, axisTick: { show: false },
    },
    yAxis: {
      type: 'category', inverse: true,
      data: rows.map((row) => row.feature),
      axisLabel: {
        color: '#405767', fontSize: 12, width: 128, overflow: 'truncate',
        formatter: (value, index) => `${value}  ${featureValue(rows[index]?.feature_value)}`,
      },
      axisLine: { show: false }, axisTick: { show: false },
    },
    series: [
      { name: '辅助', type: 'bar', stack: 'shap', silent: true, barWidth: 18, itemStyle: { color: 'transparent' }, emphasis: { disabled: true }, data: rows.map((row) => Math.min(row.before, row.after)) },
      { name: '推高流失风险', type: 'bar', stack: 'shap', barWidth: 18, itemStyle: { color: colors.positive, borderRadius: [2, 2, 2, 2] }, data: rows.map((row) => row.shap_value > 0 ? row.shap_value : null) },
      { name: '降低流失风险', type: 'bar', stack: 'shap', barWidth: 18, itemStyle: { color: colors.negative, borderRadius: [2, 2, 2, 2] }, data: rows.map((row) => row.shap_value < 0 ? Math.abs(row.shap_value) : null) },
      {
        type: 'custom', silent: true, data: rows.slice(0, -1).map((row, index) => [row.after, index]),
        renderItem: (params, api) => {
          const start = api.coord([api.value(0), api.value(1)])
          const end = api.coord([api.value(0), api.value(1) + 1])
          return { type: 'line', shape: { x1: start[0], y1: start[1], x2: end[0], y2: end[1] }, style: { stroke: '#b7c2cc', lineWidth: 1, lineDash: [3, 3] } }
        },
      },
      {
        type: 'custom', silent: true, data: rows.map((row, index) => [labelX, index, row.shap_value]),
        renderItem: (params, api) => {
          const point = api.coord([api.value(0), api.value(1)])
          const value = Number(api.value(2))
          return { type: 'text', x: point[0], y: point[1], style: { text: `${value >= 0 ? '+' : ''}${value.toFixed(4)}`, fill: value >= 0 ? colors.positive : colors.negative, fontSize: 12, fontWeight: 600, align: 'left', verticalAlign: 'middle' } }
        },
      },
    ],
  }
})
</script>

<template>
  <EChart :option="option" :height="height" :loading="loading" :error="error" :empty="!features.length" aria-label="单客户 SHAP 贡献瀑布图，右侧标注各特征正负贡献值" />
</template>
