<script setup>
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue'
import { Refresh, Right } from '@element-plus/icons-vue'
import { analysisApi, predictApi } from '../api'
import { getErrorMessage } from '../api/helpers'
import { formatDate, formatNumber, formatPercent } from '../utils/format'
import { buildPriorityFlow, buildPriorityWindow, nextPriorityScrollTop, resolvePriorityScrollTop } from '../utils/priorityFlow'
import PageHeader from '../components/PageHeader.vue'
import EChart from '../components/EChart.vue'
import RiskTag from '../components/RiskTag.vue'
import ShapDrawer from '../components/ShapDrawer.vue'

const loading = ref(false)
const error = ref('')
const data = ref(null)
const batches = ref([])
const selectedBatch = ref('')
const drawerOpen = ref(false)
const selectedCustomer = ref('')
const priorityViewport = ref(null)
const priorityVisibleScrollTop = ref(0)
const priorityFlow = computed(() => buildPriorityFlow(data.value?.high_risk_customers || []))
const priorityWindow = computed(() => buildPriorityWindow(priorityFlow.value.items, priorityVisibleScrollTop.value))

async function load() {
  loading.value = true
  error.value = ''
  try { data.value = await analysisApi.dashboard(selectedBatch.value || undefined) } catch (err) { error.value = getErrorMessage(err) } finally { loading.value = false }
}
async function loadBatches() {
  try { batches.value = await predictApi.batches() } catch { batches.value = [] }
}
function openShap(row) { selectedCustomer.value = row.customer_id; drawerOpen.value = true }

const priorityMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
let priorityFrame = 0
let previousTimestamp = 0
let priorityScrollPosition = 0
let appliedPriorityScrollTop = 0
function syncPriorityScroll() {
  const viewport = priorityViewport.value
  if (!viewport) return
  priorityScrollPosition = resolvePriorityScrollTop(priorityScrollPosition, appliedPriorityScrollTop, viewport.scrollTop)
  appliedPriorityScrollTop = viewport.scrollTop
  priorityVisibleScrollTop.value = viewport.scrollTop
}
function animatePriority(timestamp) {
  const viewport = priorityViewport.value
  const paused = viewport?.matches(':hover') || viewport?.matches(':focus-within')
  syncPriorityScroll()
  if (viewport && priorityFlow.value.shouldFlow && !priorityMotion.matches && !paused) {
    const elapsed = previousTimestamp ? Math.min(timestamp - previousTimestamp, 64) : 0
    const sequenceHeight = priorityFlow.value.items.length * 48
    const duration = priorityFlow.value.items.length * 3500
    priorityScrollPosition = nextPriorityScrollTop(priorityScrollPosition, sequenceHeight, elapsed, duration)
    viewport.scrollTop = priorityScrollPosition
    appliedPriorityScrollTop = viewport.scrollTop
    priorityVisibleScrollTop.value = viewport.scrollTop
  }
  previousTimestamp = timestamp
  priorityFrame = requestAnimationFrame(animatePriority)
}
function refreshAfterPrediction() {
  loadBatches()
  if (!selectedBatch.value) load()
}
onMounted(() => {
  load()
  loadBatches()
  window.addEventListener('model:updated', load)
  window.addEventListener('data:updated', load)
  window.addEventListener('prediction:updated', refreshAfterPrediction)
})
onActivated(() => {
  previousTimestamp = 0
  priorityFrame = requestAnimationFrame(animatePriority)
})
onDeactivated(() => cancelAnimationFrame(priorityFrame))
onBeforeUnmount(() => {
  cancelAnimationFrame(priorityFrame)
  window.removeEventListener('model:updated', load)
  window.removeEventListener('data:updated', load)
  window.removeEventListener('prediction:updated', refreshAfterPrediction)
})

const riskOption = computed(() => ({
  color: ['#8ba5b7', '#d49b3e', '#d94b4b'],
  tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 人 · {d}%' },
  legend: { bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { color: '#657786', fontSize: 11 } },
  series: [{ type: 'pie', radius: ['52%', '72%'], center: ['50%', '43%'], avoidLabelOverlap: true, itemStyle: { borderColor: '#fffefb', borderWidth: 3 }, label: { show: true, position: 'center', formatter: () => `${formatNumber(data.value?.kpis.predicted_customers)}\n预测客户`, color: '#102a43', fontSize: 18, lineHeight: 27, fontWeight: 600 }, emphasis: { label: { show: true } }, data: data.value?.risk_distribution || [] }],
}))
const histogramOption = computed(() => ({
  grid: { left: 46, right: 20, top: 22, bottom: 38 },
  tooltip: { trigger: 'axis', formatter: (params) => `流失概率 ${params[0].name}<br/>客户数：${formatNumber(params[0].value)}` },
  xAxis: { type: 'category', data: data.value?.probability_distribution.map((item) => item.range) || [], axisLabel: { color: '#7a8a97', fontSize: 10, interval: 1 }, axisLine: { lineStyle: { color: '#dfe5ea' } }, axisTick: { show: false } },
  yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#7a8a97', fontSize: 10 }, splitLine: { lineStyle: { color: '#edf0f2' } } },
  series: [{ type: 'bar', data: data.value?.probability_distribution.map((item) => item.count) || [], barMaxWidth: 32, itemStyle: { color: '#477dbb', borderRadius: [3, 3, 0, 0] } }],
}))
const regionOption = computed(() => {
  const items = [...(data.value?.regions || [])].sort((a, b) => a.high_rate - b.high_rate)
  return {
    grid: { left: 72, right: 54, top: 14, bottom: 28 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (params) => { const item = items[params[0].dataIndex]; return `区域 ${item.region}<br/>高风险率：${formatPercent(item.high_rate)}<br/>高风险 / 总客户：${item.high} / ${item.total}` } },
    xAxis: { type: 'value', max: (value) => Math.max(value.max * 1.12, 0.01), axisLabel: { color: '#7a8a97', fontSize: 10, formatter: (value) => `${Math.round(value * 100)}%` }, splitLine: { lineStyle: { color: '#edf0f2' } } },
    yAxis: { type: 'category', data: items.map((item) => `区域 ${item.region}`), axisLabel: { color: '#536776', fontSize: 11 }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: 'bar', data: items.map((item) => item.high_rate), barMaxWidth: 17, itemStyle: { color: '#d94b4b', borderRadius: [0, 3, 3, 0] }, label: { show: true, position: 'right', color: '#7b5555', fontSize: 10, formatter: ({ value }) => formatPercent(value) } }],
  }
})
const scatterOption = computed(() => {
  const groups = ['低风险', '中风险', '高风险']
  const colors = { 低风险: '#6c94bd', 中风险: '#d49b3e', 高风险: '#d94b4b' }
  return {
    grid: { left: 48, right: 24, top: 42, bottom: 45 },
    legend: { top: 2, right: 8, icon: 'circle', itemWidth: 7, itemHeight: 7, textStyle: { color: '#657786', fontSize: 10 } },
    tooltip: { trigger: 'item', formatter: ({ value }) => `平均月费：¥${formatNumber(value[0], 2)}<br/>流失概率：${formatPercent(value[1])}<br/>${value[2]}` },
    xAxis: { type: 'value', name: '平均月费（元）', nameLocation: 'middle', nameGap: 30, nameTextStyle: { color: '#7a8a97', fontSize: 10 }, axisLabel: { color: '#7a8a97', fontSize: 10 }, splitLine: { lineStyle: { color: '#f0f2f4' } } },
    yAxis: { type: 'value', min: 0, max: 1, name: '流失概率', nameTextStyle: { color: '#7a8a97', fontSize: 10 }, axisLabel: { color: '#7a8a97', fontSize: 10, formatter: (value) => `${value * 100}%` }, splitLine: { lineStyle: { color: '#edf0f2' } } },
    series: groups.map((level) => ({ name: level, type: 'scatter', symbolSize: 7, itemStyle: { color: colors[level], opacity: .56 }, emphasis: { scale: 1.6, itemStyle: { opacity: 1 } }, data: (data.value?.fee_risk_points || []).filter((item) => item.risk_level === level).map((item) => [item.fee, item.probability, item.risk_level]) })),
  }
})
</script>

<template>
  <div class="workspace-page">
    <PageHeader title="风险总览" description="汇总当前预测批次的客户风险规模、概率分布与关键归因入口。">
      <template #actions>
        <el-select v-model="selectedBatch" class="batch-selector" :disabled="!batches.length" placeholder="最新批次" @change="load">
          <el-option label="最新批次（默认）" value="" />
          <el-option v-for="item in batches" :key="item.batch_id" :value="item.batch_id" :label="`${item.filename} · ${formatDate(item.created_at)}`" />
        </el-select>
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新数据</el-button>
      </template>
    </PageHeader>
    <el-result v-if="error && !data" icon="warning" title="总览暂时不可用" :sub-title="error"><template #extra><el-button type="primary" @click="load">重新加载</el-button></template></el-result>
    <template v-else>
      <section class="kpi-band" aria-label="关键指标" aria-live="polite">
        <div class="kpi-item"><div class="kpi-label">预测客户数</div><div class="kpi-value">{{ formatNumber(data?.kpis.predicted_customers) }}</div><div class="kpi-note">{{ data?.batch_id ? `批次 ${data.batch_id}` : '单客户预测记录' }}</div></div>
        <div class="kpi-item emphasis"><div class="kpi-label">高风险客户</div><div class="kpi-value">{{ formatNumber(data?.kpis.high_risk_customers) }}</div><div class="kpi-note">流失概率 ≥ 70%</div></div>
        <div class="kpi-item"><div class="kpi-label">高风险客户占比</div><div class="kpi-value">{{ formatPercent(data?.kpis.high_risk_rate) }}</div><div class="kpi-note">当前预测范围</div></div>
        <div class="kpi-item"><div class="kpi-label">训练集实际流失率</div><div class="kpi-value">{{ formatPercent(data?.kpis.actual_churn_rate) }}</div><div class="kpi-note">历史标签基准</div></div>
        <div class="kpi-item"><div class="kpi-label">XGBoost AUC</div><div class="kpi-value">{{ formatNumber(data?.kpis.model_auc, 3) }}</div><div class="kpi-note">当前生效模型</div></div>
        <div class="kpi-item"><div class="kpi-label">训练客户数</div><div class="kpi-value">{{ formatNumber(data?.kpis.train_customers) }}</div><div class="kpi-note">模型学习样本</div></div>
      </section>
      <div class="chart-grid">
        <section class="panel"><div class="panel-header"><div><h2>客户风险结构</h2><p>低、中、高风险客户数量与占比</p></div></div><div class="panel-body"><EChart :option="riskOption" :loading="loading" :empty="!data?.risk_distribution?.length" height="286px" aria-label="客户风险分布环形图" /></div></section>
        <section class="panel"><div class="panel-header"><div><h2>流失概率直方图</h2><p>以 0.1 为区间观察预测概率分布</p></div></div><div class="panel-body"><EChart :option="histogramOption" :loading="loading" :empty="!data?.probability_distribution?.length" height="286px" aria-label="流失概率分布直方图" /></div></section>
        <section class="panel"><div class="panel-header"><div><h2>区域高风险率</h2><p>按地理区域比较高风险客户占比</p></div></div><div class="panel-body"><EChart :option="regionOption" :loading="loading" :empty="!data?.regions?.length" height="340px" aria-label="区域高风险率横向条形图" /></div></section>
        <section class="panel"><div class="panel-header"><div><h2>费用与流失风险</h2><p>每个点代表一位客户，最多展示 500 个样本</p></div></div><div class="panel-body"><EChart :option="scatterOption" :loading="loading" :empty="!data?.fee_risk_points?.length" height="340px" aria-label="平均月费与流失概率散点图" /></div></section>
      </div>
      <section class="panel mt-18">
        <div class="panel-header"><div><h2>流失风险客户</h2><p>当前批次全部高风险客户按流失概率降序循环展示，悬停暂停并可手动滚动；点击归因查看 SHAP 解释与挽留建议</p></div><router-link to="/customers" class="view-all">查看全部客户 <el-icon><Right /></el-icon></router-link></div>
        <div class="priority-table-shell" v-loading="loading" aria-label="流失风险客户，按流失概率降序排列">
          <div class="priority-table-scroll">
            <div class="priority-table">
              <table class="priority-grid priority-header">
                <colgroup><col class="col-id"><col class="col-probability"><col class="col-risk"><col class="col-region"><col class="col-fee"><col><col class="col-action"></colgroup>
                <thead><tr><th>客户 ID</th><th>流失概率</th><th>风险等级</th><th>区域</th><th>平均月费</th><th>首要风险因素</th><th>操作</th></tr></thead>
              </table>
              <div v-if="!loading && !priorityFlow.items.length" class="priority-empty">暂无高风险客户</div>
              <div v-else ref="priorityViewport" class="priority-viewport" @scroll="syncPriorityScroll">
                <div class="priority-track" :style="{ height: `${priorityWindow.totalHeight}px` }">
                  <div
                    v-for="{ customer: row, index, offset } in priorityWindow.rows"
                    :key="index"
                    class="priority-row"
                    :style="{ transform: `translateY(${offset}px)` }"
                    :aria-hidden="index >= priorityFlow.items.length ? 'true' : undefined"
                  >
                    <div class="priority-cell">{{ row.customer_id }}</div>
                    <div class="priority-cell"><div class="probability-cell"><span class="numeric">{{ formatPercent(row.probability) }}</span><el-progress :percentage="Math.round(row.probability * 100)" :show-text="false" :stroke-width="4" :color="row.probability >= .7 ? '#d94b4b' : '#477dbb'" /></div></div>
                    <div class="priority-cell"><RiskTag :level="row.risk_level" /></div>
                    <div class="priority-cell">{{ row.region }}</div>
                    <div class="priority-cell">¥ {{ formatNumber(row.monthly_fee, 2) }}</div>
                    <div class="priority-cell"><span class="table-feature">{{ row.top_features?.[0]?.feature || '—' }}</span></div>
                    <div class="priority-cell"><el-button link type="primary" :tabindex="index >= priorityFlow.items.length ? -1 : 0" @click="openShap(row)">查看归因</el-button></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </template>
    <ShapDrawer v-model="drawerOpen" :customer-id="selectedCustomer" />
  </div>
</template>

<style scoped>
.batch-selector { width: 260px; margin-right: 10px; }
.emphasis .kpi-value { color: #bd4040; }
.view-all { display: inline-flex; align-items: center; gap: 5px; color: #2563c7; font-size: 12px; white-space: nowrap; }
.probability-cell { display: grid; grid-template-columns: 50px minmax(50px, 1fr); align-items: center; gap: 9px; width: 100%; }
.priority-table-scroll { overflow-x: auto; }
.priority-table { min-width: 850px; }
.priority-grid { width: 100%; table-layout: fixed; border-collapse: collapse; border-spacing: 0; }
.priority-grid .col-id { width: 12%; }
.priority-grid .col-probability { width: 22%; }
.priority-grid .col-risk { width: 11%; }
.priority-grid .col-region { width: 8%; }
.priority-grid .col-fee { width: 12%; }
.priority-grid .col-action { width: 90px; }
.priority-grid th, .priority-cell { padding: 0 16px; text-align: left; white-space: nowrap; }
.priority-grid th { height: 44px; background: #f5f7f8; color: #536776; font-size: 13px; font-weight: 600; }
.priority-viewport { height: 288px; overflow-x: hidden; overflow-y: auto; scrollbar-width: thin; scrollbar-color: #c6d0d9 transparent; }
.priority-track { position: relative; }
.priority-row { position: absolute; top: 0; left: 0; display: grid; grid-template-columns: 12% 22% 11% 8% 12% minmax(0, 1fr) 90px; width: 100%; height: 48px; background: #fff; }
.priority-cell { display: flex; align-items: center; min-width: 0; height: 48px; box-sizing: border-box; border-bottom: 1px solid #edf0f2; color: #435a6b; font-size: 13px; overflow: hidden; }
.priority-empty { height: 180px; display: grid; place-items: center; color: var(--muted); font-size: 13px; }
</style>
