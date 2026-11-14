<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { analysisApi } from '../api'
import { getErrorMessage } from '../api/helpers'
import { featureValue, formatNumber } from '../utils/format'
import { normalizeSwarmColors } from '../utils/swarmColor'
import PageHeader from '../components/PageHeader.vue'
import EChart from '../components/EChart.vue'

const loading = ref(false)
const error = ref('')
const dependency = ref(null)
const dependencyFeature = ref('')
const dependencyLoading = ref(false)
const dependencyError = ref('')
const data = ref({ global: [], swarm: [] })
async function load() {
  loading.value = true; error.value = ''
  try { data.value = await analysisApi.features() } catch (err) { error.value = getErrorMessage(err) } finally { loading.value = false }
}
async function loadDependency(feature) {
  dependencyLoading.value = true
  dependencyError.value = ''
  try {
    const result = await analysisApi.dependency(feature || undefined)
    dependency.value = result
    dependencyFeature.value = result.feature
  } catch (err) {
    dependencyError.value = getErrorMessage(err)
  } finally {
    dependencyLoading.value = false
  }
}
function handleModelUpdated() {
  load()
  loadDependency()
}
onMounted(() => {
  load()
  loadDependency()
  window.addEventListener('model:updated', handleModelUpdated)
})
onBeforeUnmount(() => window.removeEventListener('model:updated', handleModelUpdated))

const globalOption = computed(() => {
  const items = [...(data.value.global || [])].reverse()
  return {
    grid: { left: 178, right: 54, top: 16, bottom: 32 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (params) => { const item = items[params[0].dataIndex]; return `${item.feature}<br/>平均 |SHAP|：${formatNumber(item.importance, 4)}` } },
    xAxis: { type: 'value', name: '平均 |SHAP|', nameTextStyle: { color: '#7a8a97', fontSize: 10 }, axisLabel: { color: '#7a8a97', fontSize: 10 }, splitLine: { lineStyle: { color: '#edf0f2' } } },
    yAxis: { type: 'category', data: items.map((item) => item.feature), axisLabel: { color: '#405767', fontSize: 11, width: 164, overflow: 'truncate' }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: 'bar', data: items.map((item) => item.importance), barMaxWidth: 15, itemStyle: { color: '#477dbb', borderRadius: [0, 3, 3, 0] }, label: { show: true, position: 'right', color: '#657786', fontSize: 9, formatter: ({ value }) => formatNumber(value, 3) } }],
  }
})
const swarmOption = computed(() => {
  const names = (data.value.global || []).slice(0, 12).map((item) => item.feature)
  const swarm = (data.value.swarm || []).filter((item) => names.includes(item.feature))
  const points = normalizeSwarmColors(swarm).map((item, index) => [item.shap_value, names.indexOf(item.feature) + (((index * 37) % 100) / 100 - .5) * .56, item.colorValue, item.value, names.indexOf(item.feature)])
  return {
    grid: { left: 178, right: 32, top: 28, bottom: 96 },
    tooltip: { trigger: 'item', formatter: ({ value }) => `${names[value[4]]}<br/>特征值：${featureValue(value[3])}<br/>SHAP：${Number(value[0]).toFixed(4)}` },
    visualMap: { min: 0, max: 1, dimension: 2, orient: 'horizontal', left: 'center', bottom: 3, itemWidth: 10, itemHeight: 100, text: ['特征值高', '特征值低'], calculable: false, textStyle: { color: '#657786', fontSize: 10 }, inRange: { color: ['#367bc5', '#c9d2d7', '#d94b4b'] } },
    xAxis: { type: 'value', name: 'SHAP 值（对流失预测的贡献）', nameLocation: 'middle', nameGap: 31, nameTextStyle: { color: '#657786', fontSize: 11 }, axisLabel: { color: '#7a8a97', fontSize: 10 }, splitLine: { lineStyle: { color: '#edf0f2' } } },
    yAxis: { type: 'value', min: -1, max: 12, interval: 1, axisLabel: { color: '#405767', fontSize: 11, width: 164, overflow: 'truncate', formatter: (value) => { const index = Number(value); return Number.isInteger(index) ? names[index] || '' : '' } }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: true, lineStyle: { color: '#f1f3f4' } } },
    series: [{ type: 'scatter', data: points, symbolSize: 6, itemStyle: { opacity: .58 }, emphasis: { scale: 1.8, itemStyle: { opacity: 1 } }, markLine: { silent: true, symbol: 'none', lineStyle: { color: '#8b99a4', type: 'solid', width: 1 }, label: { show: false }, data: [{ xAxis: 0 }] } }],
  }
})
const dependencyOption = computed(() => {
  const points = (dependency.value?.points || []).filter((item) => item.value !== null)
  return {
    grid: { left: 58, right: 24, top: 26, bottom: 48 },
    tooltip: { trigger: 'item', formatter: ({ value }) => `特征值：${formatNumber(value[0], 3)}<br/>SHAP：${Number(value[1]).toFixed(4)}` },
    xAxis: {
      type: 'value',
      name: '特征取值',
      nameLocation: 'middle',
      nameGap: 30,
      nameTextStyle: { color: '#7a8a97', fontSize: 10 },
      axisLabel: { color: '#7a8a97', fontSize: 10 },
      splitLine: { lineStyle: { color: '#f0f2f4' } },
    },
    yAxis: {
      type: 'value',
      name: 'SHAP 贡献',
      nameTextStyle: { color: '#7a8a97', fontSize: 10 },
      axisLabel: { color: '#7a8a97', fontSize: 10 },
      splitLine: { lineStyle: { color: '#edf0f2' } },
    },
    series: [
      {
        type: 'scatter',
        symbolSize: 7,
        data: points.map((item) => ({
          value: [item.value, item.shap_value],
          itemStyle: { color: item.shap_value >= 0 ? '#d94b4b' : '#367bc5', opacity: 0.62 },
        })),
        markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: '#8b99a4', type: 'dashed' }, data: [{ yAxis: 0 }] },
      },
    ],
  }
})
</script>

<template>
  <div class="workspace-page">
    <PageHeader title="特征分析" description="从当前生效 XGBoost 模型的 SHAP 解释中识别全局风险驱动因素及其影响方向。">
      <template #actions><el-button :icon="Refresh" :loading="loading" @click="load">刷新解释</el-button></template>
    </PageHeader>
    <div class="inline-note explanation-note"><span><strong>读图说明：</strong>SHAP &gt; 0 表示该特征推高流失预测，SHAP &lt; 0 表示降低流失预测；全局重要性使用平均绝对 SHAP 值，蜂群图颜色按每个特征的 5%–95% 分位数独立归一化，悬浮提示显示原始值。</span></div>
    <el-result v-if="error && !data.global.length" icon="warning" title="模型解释不可用" :sub-title="error"><template #extra><el-button type="primary" @click="load">重新加载</el-button></template></el-result>
    <template v-else>
      <section class="panel mt-18">
        <div class="panel-header"><div><h2>全局特征重要性</h2><p>测试样本中各特征的平均绝对 SHAP 值，按影响力从高到低排列</p></div><span class="panel-badge">Top {{ data.global.length }}</span></div>
        <div class="panel-body"><EChart :option="globalOption" :loading="loading" :empty="!data.global.length" height="570px" aria-label="全局 SHAP 特征重要性水平条形图" /></div>
      </section>
      <section class="panel mt-18">
        <div class="panel-header"><div><h2>Top 12 特征蜂群图</h2><p>每个点代表一个客户样本；横向位置表示贡献方向与幅度，纵向轻微分散仅用于减少重叠</p></div><div class="legend"><span class="legend-item"><i class="legend-dot" style="background:#367bc5" />特征值低</span><span class="legend-item"><i class="legend-dot" style="background:#d94b4b" />特征值高</span></div></div>
        <div class="panel-body"><EChart :option="swarmOption" :loading="loading" :empty="!data.swarm.length" height="570px" aria-label="Top 12 特征 SHAP 蜂群散点图" /></div>
      </section>
      <section class="panel mt-18">
        <div class="panel-header"><div><h2>特征依赖分析</h2><p>观察单个特征取值变化如何影响 SHAP 贡献；红色推高流失，蓝色降低流失</p></div><el-select v-model="dependencyFeature" class="dependency-select" filterable placeholder="选择特征" :disabled="!dependency?.features?.length" @change="loadDependency"><el-option v-for="item in dependency?.features || []" :key="item" :label="item" :value="item" /></el-select></div>
        <div class="panel-body"><EChart :option="dependencyOption" :loading="dependencyLoading" :error="dependencyError" :empty="!dependency?.points?.length" height="380px" aria-label="特征取值与 SHAP 贡献的依赖散点图" /></div>
        <div class="inline-note dependency-note"><span>{{ dependency?.note }}</span></div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.explanation-note { border-left-color: #477dbb; }
.panel-badge { color: #657786; background: #f0f3f6; border-radius: 4px; padding: 4px 8px; font-size: 10px; }
.dependency-select { width: 260px; }
.dependency-note { margin: 0 20px 18px; border-left-color: #477dbb; }
@media (max-width: 620px) { .dependency-select { width: 100%; } }
</style>
