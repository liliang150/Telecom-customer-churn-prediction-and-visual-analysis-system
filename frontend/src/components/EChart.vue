<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '320px' },
  loading: Boolean,
  error: { type: String, default: '' },
  empty: Boolean,
  ariaLabel: { type: String, default: '数据图表' },
})

const container = ref(null)
let chart
let observer
let frame
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

function render() {
  if (!chart) return
  if (props.error || props.empty) {
    chart.clear()
    return
  }
  chart.setOption({ ...props.option, animation: !reducedMotion, animationDuration: 200 }, true)
}

function resize() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => chart?.resize())
}

onMounted(async () => {
  await nextTick()
  chart = echarts.init(container.value, null, { renderer: 'canvas' })
  observer = new ResizeObserver(resize)
  observer.observe(container.value)
  render()
})

watch(() => props.option, render, { deep: true })
watch(() => [props.error, props.empty], render)

onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
  chart?.dispose()
})

defineExpose({ resize })
</script>

<template>
  <div class="chart-shell" :style="{ height }">
    <div ref="container" class="chart-canvas" role="img" :aria-label="ariaLabel" />
    <div v-if="loading" class="chart-state" aria-live="polite"><span class="state-spinner" />图表加载中</div>
    <div v-else-if="error" class="chart-state chart-error" role="alert">{{ error }}</div>
    <div v-else-if="empty" class="chart-state">暂无可展示的数据</div>
  </div>
</template>

<style scoped>
.chart-shell { width: 100%; min-height: 180px; position: relative; }
.chart-canvas { width: 100%; height: 100%; }
.chart-state { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; gap: 9px; background: rgba(255, 254, 251, .88); color: #657786; font-size: 13px; text-align: center; padding: 20px; }
.chart-error { color: #b44242; }
.state-spinner { width: 16px; height: 16px; border: 2px solid #d7e2ef; border-top-color: #2563c7; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
