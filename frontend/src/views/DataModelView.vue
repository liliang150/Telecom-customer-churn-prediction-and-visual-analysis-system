<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { dataApi, modelApi } from '../api'
import { getErrorMessage } from '../api/helpers'
import { displaySourceName, formatDate, formatNumber, formatPercent } from '../utils/format'
import { useAuth } from '../stores/auth'
import PageHeader from '../components/PageHeader.vue'
import EChart from '../components/EChart.vue'

const { isAdmin } = useAuth()
const activeTab = ref('data')
const overview = ref(null)
const dataLoading = ref(false)
const dataError = ref('')
const metadata = ref(null)
const versions = ref([])
const modelLoading = ref(false)
const modelError = ref('')
const training = ref(false)
const activating = ref('')
const deleting = ref('')
const candidate = ref(null)
const explainability = ref(null)
const explainLoading = ref(false)
const sensitivity = ref(null)
const sensitivityRunning = ref(false)
const sensitivityProgress = ref({ completed: 0, total: 6, current_depth: null })
const exportingReport = ref(false)
const featureSelection = ref(null)
const featureSelectionRunning = ref(false)
const featureSelectionProgress = ref({ completed: 0, total: 3, current_label: null })
const eda = ref(null)
const edaLoading = ref(false)
const edaFeature = ref('')
const dataVersions = ref([])
const uploadFile = ref(null)
const uploadInput = ref(null)
const uploadLoading = ref(false)
const confirming = ref(false)
const stagedUpload = ref(null)
const activatingData = ref('')
const qualityDataset = ref('train')
let trainingTimer
const metricRows = [
  { key: 'auc', label: 'AUC', note: '越高越好' },
  { key: 'pr_auc', label: 'PR-AUC', note: '越高越好' },
  { key: 'recall', label: 'Recall（召回率）', note: '越高越好' },
  { key: 'precision', label: 'Precision（精确率）', note: '越高越好' },
  { key: 'f1', label: 'F1', note: '越高越好' },
  { key: 'ks', label: 'KS', note: '越高越好' },
  { key: 'brier', label: 'Brier', note: '越低越好' },
]

async function loadOverview() {
  dataLoading.value = true; dataError.value = ''
  try {
    const [overviewData, versionItems] = await Promise.all([dataApi.overview(), dataApi.versions()])
    overview.value = overviewData
    dataVersions.value = versionItems
  } catch (err) { dataError.value = getErrorMessage(err) } finally { dataLoading.value = false }
}
async function loadEda() {
  edaLoading.value = true
  try {
    eda.value = await dataApi.eda()
    edaFeature.value = eda.value?.features?.[0]?.feature || ''
  } catch {
    eda.value = null
  } finally {
    edaLoading.value = false
  }
}
async function loadModel() {
  modelLoading.value = true; modelError.value = ''
  try {
    const [evaluation, versionItems] = await Promise.all([modelApi.evaluate(), modelApi.versions()])
    metadata.value = evaluation
    versions.value = versionItems
  } catch (err) { modelError.value = getErrorMessage(err) } finally { modelLoading.value = false }
}
async function loadExplainability() {
  explainLoading.value = true
  try {
    explainability.value = await modelApi.explainability()
  } catch {
    explainability.value = null
  } finally {
    explainLoading.value = false
  }
}
async function loadSensitivity() {
  try {
    sensitivity.value = await modelApi.sensitivity()
  } catch {
    sensitivity.value = null
  }
}
async function waitSensitivity(jobId) {
  for (;;) {
    const job = await modelApi.sensitivityStatus(jobId)
    sensitivityProgress.value = { completed: job.completed, total: job.total, current_depth: job.current_depth }
    if (job.status === 'succeeded') {
      sensitivity.value = job.result
      ElMessage.success('参数敏感性实验完成')
      return
    }
    if (job.status === 'failed') throw new Error(job.error || '参数敏感性实验失败')
    await new Promise((resolve) => window.setTimeout(resolve, 1500))
  }
}
async function runSensitivityAnalysis() {
  if (sensitivityRunning.value) return
  sensitivityRunning.value = true
  sensitivityProgress.value = { completed: 0, total: 6, current_depth: null }
  try {
    const job = await modelApi.runSensitivity()
    await waitSensitivity(job.job_id)
  } catch (err) {
    ElMessage.error(getErrorMessage(err))
  } finally {
    sensitivityRunning.value = false
  }
}
async function loadFeatureSelection() {
  try {
    featureSelection.value = await modelApi.featureSelection()
  } catch {
    featureSelection.value = null
  }
}
async function waitFeatureSelection(jobId) {
  for (;;) {
    const job = await modelApi.featureSelectionStatus(jobId)
    featureSelectionProgress.value = { completed: job.completed, total: job.total, current_label: job.current_label }
    if (job.status === 'succeeded') {
      featureSelection.value = job.result
      ElMessage.success('特征筛选实验完成')
      return
    }
    if (job.status === 'failed') throw new Error(job.error || '特征筛选实验失败')
    await new Promise((resolve) => window.setTimeout(resolve, 1500))
  }
}
async function runFeatureSelectionExperiment() {
  if (featureSelectionRunning.value) return
  featureSelectionRunning.value = true
  featureSelectionProgress.value = { completed: 0, total: 3, current_label: null }
  try {
    const job = await modelApi.runFeatureSelection()
    await waitFeatureSelection(job.job_id)
  } catch (err) {
    ElMessage.error(getErrorMessage(err))
  } finally {
    featureSelectionRunning.value = false
  }
}
async function exportReport() {
  exportingReport.value = true
  try {
    const response = await modelApi.exportEvaluationReport()
    const url = URL.createObjectURL(new Blob([response.data], { type: 'text/markdown;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `模型评估摘要_${metadata.value?.version || 'report'}.md`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    ElMessage.success('评估摘要已导出')
  } catch (err) {
    ElMessage.error(getErrorMessage(err))
  } finally {
    exportingReport.value = false
  }
}
async function pollTraining(jobId) {
  try {
    const job = await modelApi.trainingStatus(jobId)
    if (['queued', 'running'].includes(job.status)) {
      trainingTimer = window.setTimeout(() => pollTraining(jobId), 800)
      return
    }
    training.value = false
    if (job.status === 'failed') {
      ElMessage.error(job.error || '模型训练失败')
      return
    }
    candidate.value = job.result
    await loadModel()
    ElMessage.success(`候选模型 ${job.result.version} 已训练完成，请核对指标后确认上线`)
  } catch (err) {
    training.value = false
    ElMessage.error(getErrorMessage(err))
  }
}
async function train() {
  try { await ElMessageBox.confirm(`将使用当前训练数据“${trainingDataName.value}”训练候选模型，当前上线模型不受影响。是否继续？`, '训练候选模型', { confirmButtonText: '开始训练', cancelButtonText: '取消', type: 'info', customStyle: { width: '420px' } }) } catch { return }
  training.value = true
  candidate.value = null
  try {
    const job = await modelApi.train()
    await pollTraining(job.job_id)
  } catch (err) {
    training.value = false
    ElMessage.error(getErrorMessage(err))
  }
}
function selectUploadFile(event) {
  uploadFile.value = event.target.files?.[0] || null
  stagedUpload.value = null
}
async function uploadData() {
  if (!uploadFile.value) {
    ElMessage.warning('请先选择 CSV 或 Excel 文件')
    return
  }
  uploadLoading.value = true
  try {
    stagedUpload.value = await dataApi.upload('train', uploadFile.value)
    ElMessage.success('文件校验通过，请核对预览后确认替换')
  } catch (err) { ElMessage.error(getErrorMessage(err)) } finally { uploadLoading.value = false }
}
async function confirmDataUpload() {
  try { await ElMessageBox.confirm('确认后将替换当前活动数据，并保存可追溯的数据版本。是否继续？', '确认替换数据', { confirmButtonText: '确认替换', cancelButtonText: '取消', type: 'warning' }) } catch { return }
  confirming.value = true
  try {
    const result = await dataApi.confirm(stagedUpload.value.saved_name, stagedUpload.value.kind)
    ElMessage.success(`数据版本 ${result.version} 已启用`)
    stagedUpload.value = null
    uploadFile.value = null
    if (uploadInput.value) uploadInput.value.value = ''
    await loadOverview()
    window.dispatchEvent(new CustomEvent('data:updated'))
  } catch (err) { ElMessage.error(getErrorMessage(err)) } finally { confirming.value = false }
}
async function restoreDataVersion(row) {
  try { await ElMessageBox.confirm(`将恢复数据版本 ${row.version}，当前模型版本不受影响。`, '恢复数据版本', { confirmButtonText: '恢复', cancelButtonText: '取消', type: 'warning' }) } catch { return }
  activatingData.value = row.version
  try {
    await dataApi.activate(row.version)
    ElMessage.success(`已恢复数据版本 ${row.version}`)
    await loadOverview()
    window.dispatchEvent(new CustomEvent('data:updated'))
  } catch (err) { ElMessage.error(getErrorMessage(err)) } finally { activatingData.value = '' }
}
async function activate(row) {
  activating.value = row.version
  try {
    await modelApi.activate(row.version)
    ElMessage.success(`已切换至模型 ${row.version}`)
    if (candidate.value?.version === row.version) candidate.value = null
    await loadModel()
    await loadExplainability()
    window.dispatchEvent(new CustomEvent('model:updated'))
  } catch (err) { ElMessage.error(getErrorMessage(err)) } finally { activating.value = '' }
}
async function deleteVersion(row) {
  try {
    await ElMessageBox.confirm(`将永久删除模型 ${row.version}，已有预测结果不受影响。是否继续？`, '删除模型版本', {
      confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning', customStyle: { width: '420px' },
    })
  } catch { return }
  deleting.value = row.version
  try {
    await modelApi.remove(row.version)
    if (candidate.value?.version === row.version) candidate.value = null
    ElMessage.success(`模型 ${row.version} 已删除`)
    await loadModel()
  } catch (err) { ElMessage.error(getErrorMessage(err)) } finally { deleting.value = '' }
}
onMounted(() => { loadOverview(); loadModel(); loadExplainability(); loadSensitivity(); loadEda(); loadFeatureSelection() })
onBeforeUnmount(() => window.clearTimeout(trainingTimer))

const previewColumns = computed(() => overview.value?.preview?.length ? Object.keys(overview.value.preview[0]).slice(0, 10) : [])
const stagedColumns = computed(() => stagedUpload.value?.preview?.length ? Object.keys(stagedUpload.value.preview[0]).slice(0, 10) : [])
const qualityFields = computed(() => overview.value?.quality_report?.[qualityDataset.value]?.fields || [])
const qualityDrift = computed(() => overview.value?.quality_report?.drift || [])
const explainRiskGroups = computed(() => {
  const groups = explainability.value?.risk_groups || {}
  return ['低风险', '中风险', '高风险'].filter((level) => groups[level]).map((level) => ({ level, ...groups[level] }))
})
const sensitivityOption = computed(() => {
  const items = sensitivity.value?.results || []
  return {
    grid: { left: 52, right: 24, top: 26, bottom: 38 },
    tooltip: { trigger: 'axis', formatter: (params) => `最大树深 ${params[0].name}<br/>AUC：${Number(params[0].value).toFixed(4)}` },
    xAxis: {
      type: 'category',
      name: '最大树深',
      nameTextStyle: { color: '#7a8a97', fontSize: 10 },
      data: items.map((item) => item.max_depth),
      axisLabel: { color: '#7a8a97', fontSize: 10 },
      axisLine: { lineStyle: { color: '#dfe5ea' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { color: '#7a8a97', fontSize: 10, formatter: (value) => Number(value).toFixed(3) },
      splitLine: { lineStyle: { color: '#edf0f2' } },
    },
    series: [{ type: 'line', smooth: true, symbolSize: 7, data: items.map((item) => item.auc), lineStyle: { width: 2.5, color: '#2563c7' }, itemStyle: { color: '#2563c7' }, areaStyle: { color: 'rgba(37,99,199,.08)' } }],
  }
})
const edaSelectedFeature = computed(() => {
  const items = eda.value?.features || []
  return items.find((item) => item.feature === edaFeature.value) || items[0] || null
})
const edaCorrelationOption = computed(() => {
  const items = [...(eda.value?.features || [])].reverse()
  return {
    grid: { left: 190, right: 46, top: 14, bottom: 30 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const item = items[params[0].dataIndex]
        return `${item.feature}<br/>相关系数：${Number(item.correlation).toFixed(4)}`
      },
    },
    xAxis: { type: 'value', axisLabel: { color: '#7a8a97', fontSize: 10 }, splitLine: { lineStyle: { color: '#edf0f2' } } },
    yAxis: { type: 'category', data: items.map((item) => item.feature), axisLabel: { color: '#405767', fontSize: 10, width: 180, overflow: 'truncate' }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: 'bar', barMaxWidth: 15, data: items.map((item) => ({ value: item.correlation, itemStyle: { color: item.correlation >= 0 ? '#d94b4b' : '#367bc5', borderRadius: [0, 3, 3, 0] } })) }],
  }
})
const edaHeatmapOption = computed(() => {
  const matrix = eda.value?.correlation || { features: [], matrix: [] }
  const names = matrix.features || []
  return {
    tooltip: { position: 'top', formatter: (params) => `${names[params.value[1]]} × ${names[params.value[0]]}<br/>相关：${Number(params.value[2]).toFixed(4)}` },
    grid: { left: 120, right: 24, top: 16, bottom: 92 },
    xAxis: { type: 'category', data: names, axisLabel: { color: '#7a8a97', fontSize: 9, rotate: 45, width: 120, overflow: 'truncate' }, axisLine: { show: false }, axisTick: { show: false } },
    yAxis: { type: 'category', data: names, axisLabel: { color: '#405767', fontSize: 9, width: 110, overflow: 'truncate' }, axisLine: { show: false }, axisTick: { show: false } },
    visualMap: { min: -1, max: 1, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, itemWidth: 10, itemHeight: 110, text: ['高', '低'], textStyle: { color: '#7a8a97', fontSize: 9 }, inRange: { color: ['#367bc5', '#f2f5f7', '#d94b4b'] } },
    series: [{ type: 'heatmap', data: (matrix.matrix || []).flatMap((row, i) => row.map((value, j) => [j, i, value])), label: { show: false }, emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,.2)' } } }],
  }
})
const edaBinOption = computed(() => {
  const bins = edaSelectedFeature.value?.bins || []
  return {
    grid: { left: 50, right: 20, top: 22, bottom: 58 },
    tooltip: { trigger: 'axis', formatter: (params) => `${params[0].name}<br/>流失率：${formatPercent(params[0].value)}<br/>样本：${bins[params[0].dataIndex]?.count ?? '—'}` },
    xAxis: { type: 'category', data: bins.map((item) => item.range), axisLabel: { color: '#7a8a97', fontSize: 9, rotate: 35, interval: 0, width: 90, overflow: 'truncate' }, axisLine: { lineStyle: { color: '#dfe5ea' } }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: '#7a8a97', fontSize: 10, formatter: (value) => `${Math.round(value * 100)}%` }, splitLine: { lineStyle: { color: '#edf0f2' } } },
    series: [{ type: 'bar', barMaxWidth: 34, data: bins.map((item) => item.rate), itemStyle: { color: '#477dbb', borderRadius: [3, 3, 0, 0] } }],
  }
})
const trainingDataName = computed(() => {
  const currentVersion = dataVersions.value.find(
    (item) => item.version === overview.value?.data_version && item.kind === 'train',
  )
  return displaySourceName(currentVersion?.source_file)
})
const splitOption = computed(() => {
  const hasTest = overview.value?.test_available
  if (!hasTest) {
    return {
      grid: { left: 96, right: 58, top: 18, bottom: 28 },
      tooltip: { trigger: 'axis', formatter: (params) => `${params[0].name}<br/>${formatNumber(params[0].value)} 条记录` },
      xAxis: { type: 'value', axisLabel: { color: '#7a8a97', fontSize: 10 }, splitLine: { lineStyle: { color: '#edf0f2' } } },
      yAxis: { type: 'category', data: ['train.csv'], axisLabel: { color: '#405767', fontSize: 12 }, axisLine: { show: false }, axisTick: { show: false } },
      series: [{ type: 'bar', barWidth: 28, data: [{ value: overview.value?.train_rows || 0, itemStyle: { color: '#2f659f' } }], itemStyle: { borderRadius: [0, 4, 4, 0] }, label: { show: true, position: 'right', color: '#536776', fontSize: 11, formatter: ({ value }) => `${formatNumber(value)} 行` } }],
    }
  }
  return {
    grid: { left: 76, right: 58, top: 18, bottom: 28 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (params) => `${params[0].name}<br/>${formatNumber(params[0].value)} 条记录` },
    xAxis: { type: 'value', axisLabel: { color: '#7a8a97', fontSize: 10 }, splitLine: { lineStyle: { color: '#edf0f2' } } },
    yAxis: { type: 'category', data: ['train.csv', 'test.csv'], axisLabel: { color: '#405767', fontSize: 12 }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: 'bar', barWidth: 28, data: [{ value: overview.value?.train_rows || 0, itemStyle: { color: '#2f659f' } }, { value: overview.value?.test_rows || 0, itemStyle: { color: '#9aafbf' } }], itemStyle: { borderRadius: [0, 4, 4, 0] }, label: { show: true, position: 'right', color: '#536776', fontSize: 11, formatter: ({ value }) => `${formatNumber(value)} 行` } }],
  }
})
const labelOption = computed(() => {
  const distribution = overview.value?.label_distribution || {}
  return {
    color: ['#8ba5b7', '#d94b4b'],
    tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 人 · {d}%' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { color: '#657786', fontSize: 11 } },
    series: [{ type: 'pie', radius: ['48%', '70%'], center: ['50%', '42%'], itemStyle: { borderColor: '#fffefb', borderWidth: 3 }, label: { show: false }, data: [{ name: '未流失（0）', value: distribution['0'] || 0 }, { name: '已流失（1）', value: distribution['1'] || 0 }] }],
  }
})
function curveOption(key, xName, yName, diagonal = false) {
  const xgboost = metadata.value?.metrics?.xgboost?.[key] || []
  const logistic = metadata.value?.metrics?.logistic_regression?.[key] || []
  const series = [
    { name: 'XGBoost', type: 'line', showSymbol: false, smooth: false, lineStyle: { width: 2.5, color: '#2563c7' }, itemStyle: { color: '#2563c7' }, data: xgboost.map((point) => [point.x, point.y]) },
    { name: '逻辑回归', type: 'line', showSymbol: false, smooth: false, lineStyle: { width: 2, color: '#9a6eaa' }, itemStyle: { color: '#9a6eaa' }, data: logistic.map((point) => [point.x, point.y]) },
  ]
  if (diagonal) series.push({ name: '随机基线', type: 'line', showSymbol: false, silent: true, lineStyle: { width: 1, type: 'dashed', color: '#bdc6cd' }, itemStyle: { color: '#bdc6cd' }, data: [[0, 0], [1, 1]] })
  return {
    grid: { left: 48, right: 24, top: 44, bottom: 46 },
    legend: { top: 4, right: 8, textStyle: { color: '#657786', fontSize: 10 } },
    tooltip: { trigger: 'axis', valueFormatter: (value) => formatNumber(value, 4) },
    xAxis: { type: 'value', min: 0, max: 1, name: xName, nameLocation: 'middle', nameGap: 30, nameTextStyle: { color: '#657786', fontSize: 10 }, axisLabel: { color: '#7a8a97', fontSize: 10 }, splitLine: { lineStyle: { color: '#f0f2f4' } } },
    yAxis: { type: 'value', min: 0, max: 1, name: yName, nameTextStyle: { color: '#657786', fontSize: 10 }, axisLabel: { color: '#7a8a97', fontSize: 10 }, splitLine: { lineStyle: { color: '#edf0f2' } } },
    series,
  }
}
const rocOption = computed(() => curveOption('roc_curve', '假阳性率 FPR', '真正率 TPR', true))
const prOption = computed(() => curveOption('pr_curve', '召回率 Recall', '精确率 Precision'))
const cvModels = computed(() => {
  const cv = metadata.value?.cross_validation || {}
  return [
    { key: 'xgboost', name: 'XGBoost', value: cv.xgboost },
    { key: 'logistic_regression', name: '逻辑回归', value: cv.logistic_regression },
  ].filter((item) => item.value)
})
</script>

<template>
  <div class="workspace-page">
    <PageHeader title="数据与模型" description="核对训练与预测数据分工，比较模型判别能力，并管理可追溯的模型版本。">
      <template #actions><el-button v-if="isAdmin" type="primary" :loading="training" @click="activeTab = 'model'; train()">{{ training ? '后台训练候选模型…' : '训练候选模型' }}</el-button></template>
    </PageHeader>
    <el-tabs v-model="activeTab" class="data-model-tabs">
      <el-tab-pane label="数据资产" name="data">
        <el-result v-if="dataError && !overview" icon="warning" title="数据概览不可用" :sub-title="dataError"><template #extra><el-button type="primary" @click="loadOverview">重新加载</el-button></template></el-result>
        <template v-else>
          <section v-if="isAdmin" class="panel data-update-panel">
            <div class="panel-header"><div><h2>数据更新</h2><p>上传后先校验与预览，确认前不会替换当前活动数据</p></div><span v-if="overview?.data_version" class="model-chip">当前版本 {{ overview.data_version }}</span></div>
            <div class="panel-body">
              <div class="upload-controls">
                <span class="muted">训练数据</span>
                <input ref="uploadInput" class="file-input" type="file" accept=".csv,.xlsx,.xls" @change="selectUploadFile">
                <el-button type="primary" :loading="uploadLoading" @click="uploadData">校验并预览</el-button>
              </div>
              <div v-if="stagedUpload" class="staged-area">
                <el-alert type="success" :closable="false" show-icon title="校验通过，等待确认" :description="`清洗后 ${stagedUpload.report.rows_after} 行，移除重复 ${stagedUpload.report.duplicates_removed} 行；当前活动数据尚未改变。`" />
                <el-table class="data-table staged-table" :data="stagedUpload.preview" max-height="260">
                  <el-table-column v-for="column in stagedColumns" :key="column" :prop="column" :label="column" :min-width="column.length > 12 ? 180 : 110" show-overflow-tooltip />
                </el-table>
                <div class="staged-actions"><el-button @click="stagedUpload = null">取消暂存</el-button><el-button type="warning" :loading="confirming" @click="confirmDataUpload">确认替换并生成版本</el-button></div>
              </div>
            </div>
          </section>
          <section class="kpi-band data-kpis mt-18" aria-label="数据质量统计">
            <div class="kpi-item"><div class="kpi-label">训练记录</div><div class="kpi-value">{{ formatNumber(overview?.train_rows) }}</div><div class="kpi-note">train.csv · 含监督标签</div></div>
            <div v-if="overview?.test_available" class="kpi-item"><div class="kpi-label">待预测记录</div><div class="kpi-value">{{ formatNumber(overview?.test_rows) }}</div><div class="kpi-note">test.csv · 仅用于预测</div></div>
            <div class="kpi-item"><div class="kpi-label">原始字段</div><div class="kpi-value">{{ formatNumber(overview?.column_count) }}</div><div class="kpi-note">含客户 ID 与标签</div></div>
            <div class="kpi-item"><div class="kpi-label">模型输入特征</div><div class="kpi-value">{{ formatNumber(overview?.feature_columns?.length) }}</div><div class="kpi-note">剔除 ID 与标签</div></div>
            <div class="kpi-item"><div class="kpi-label">训练集缺失值</div><div class="kpi-value">{{ formatNumber(overview?.missing_values) }}</div><div class="kpi-note">由模型管道中位数填补</div></div>
            <div class="kpi-item"><div class="kpi-label">重复客户 ID</div><div class="kpi-value">{{ formatNumber(overview?.duplicate_ids) }}</div><div class="kpi-note">清洗时保留首次记录</div></div>
          </section>
          <div v-if="overview?.test_available" class="inline-note" :class="{ warning: overview?.test_has_label }"><span><strong>数据分工：</strong>train.csv 含“是否流失”标签，用于训练与评估；test.csv 无标签，仅用于流失预测，不参与训练或指标计算。</span></div>
          <div v-else class="inline-note"><span><strong>当前仅配置了训练数据：</strong>如需批量预测，可在流失预测页面上传客户文件。</span></div>
          <div class="chart-grid mt-18">
            <section class="panel"><div class="panel-header"><div><h2>训练 / 预测数据规模</h2><p>明确监督学习与生产推理的数据边界</p></div></div><div class="panel-body"><EChart :option="splitOption" :loading="dataLoading" :empty="!overview" height="260px" aria-label="训练集和测试集记录数量" /></div></section>
            <section class="panel"><div class="panel-header"><div><h2>训练集标签分布</h2><p>实际流失标签是模型学习与评估的基准</p></div></div><div class="panel-body"><EChart :option="labelOption" :loading="dataLoading" :empty="!overview" height="260px" aria-label="训练集流失标签分布" /></div></section>
          </div>
          <section class="panel mt-18">
            <div class="panel-header"><div><h2>特征与流失关系</h2><p>按与流失标签的相关性排序；可切换特征查看分箱流失率</p></div><el-button :icon="Refresh" :loading="edaLoading" @click="loadEda">刷新分析</el-button></div>
            <div class="eda-grid" v-loading="edaLoading">
              <div class="eda-block"><h3>特征相关性 Top 12</h3><EChart :option="edaCorrelationOption" :empty="!eda?.features?.length" height="360px" aria-label="特征与流失标签相关性条形图" /></div>
              <div class="eda-block"><h3>Top 特征相关性矩阵</h3><EChart :option="edaHeatmapOption" :empty="!eda?.correlation?.features?.length" height="360px" aria-label="Top 特征相关性热力图" /></div>
            </div>
            <div class="eda-bin-head"><h3>分箱流失率</h3><el-select v-model="edaFeature" class="eda-select" filterable :disabled="!eda?.features?.length"><el-option v-for="item in eda?.features || []" :key="item.feature" :label="item.feature" :value="item.feature" /></el-select></div>
            <EChart :option="edaBinOption" :empty="!edaSelectedFeature?.bins?.length" height="300px" aria-label="选中特征的分箱流失率柱状图" />
            <div v-if="eda?.note" class="inline-note eda-note"><span>{{ eda.note }}</span></div>
          </section>
          <section class="panel mt-18">
            <div class="panel-header"><div><h2>字段级数据质量报告</h2><p>缺失包含无穷值；非数值、-1 与分布漂移均需结合业务含义核查</p></div><el-radio-group v-model="qualityDataset" size="small"><el-radio-button value="train">train.csv</el-radio-button><el-radio-button v-if="overview?.test_available" value="test">test.csv</el-radio-button></el-radio-group></div>
            <div v-if="overview?.test_available" class="schema-strip">
              <span :class="{ issue: overview?.quality_report?.schema?.missing_in_test?.length }">预测数据缺少字段：{{ overview?.quality_report?.schema?.missing_in_test?.join('、') || '无' }}</span>
              <span :class="{ issue: overview?.quality_report?.schema?.extra_in_test?.length }">预测数据额外字段：{{ overview?.quality_report?.schema?.extra_in_test?.join('、') || '无' }}</span>
              <span :class="{ issue: overview?.quality_report?.schema?.type_mismatches?.length }">类型不一致：{{ overview?.quality_report?.schema?.type_mismatches?.join('、') || '无' }}</span>
            </div>
            <el-table class="data-table quality-table" :data="qualityFields" max-height="390" v-loading="dataLoading">
              <el-table-column prop="name" label="字段" min-width="210" show-overflow-tooltip />
              <el-table-column prop="dtype" label="类型" width="90" />
              <el-table-column label="缺失" min-width="110"><template #default="{ row }">{{ formatNumber(row.missing) }} · {{ formatPercent(row.missing_rate, 1) }}</template></el-table-column>
              <el-table-column prop="unique" label="唯一值" width="85" />
              <el-table-column label="均值 / 标准差" min-width="150"><template #default="{ row }"><span v-if="row.numeric">{{ formatNumber(row.numeric.mean, 3) }} / {{ formatNumber(row.numeric.std, 3) }}</span><span v-else>—</span></template></el-table-column>
              <el-table-column label="最小值 / 最大值" min-width="150"><template #default="{ row }"><span v-if="row.numeric">{{ formatNumber(row.numeric.min, 2) }} / {{ formatNumber(row.numeric.max, 2) }}</span><span v-else>—</span></template></el-table-column>
              <el-table-column label="-1 核查" width="90"><template #default="{ row }"><span :class="{ 'issue-text': row.minus_one }">{{ formatNumber(row.minus_one) }}</span></template></el-table-column>
              <el-table-column label="非数值 / 无穷" width="120"><template #default="{ row }"><span :class="{ 'issue-text': row.non_numeric || row.infinite }">{{ row.non_numeric }} / {{ row.infinite }}</span></template></el-table-column>
            </el-table>
            <div v-if="overview?.test_available" class="drift-section">
              <div class="drift-heading"><h3>训练 / 预测分布漂移</h3><span>{{ overview?.quality_report?.drift_note }}</span></div>
              <el-table class="data-table" :data="qualityDrift" max-height="260">
                <el-table-column prop="name" label="字段" min-width="230" show-overflow-tooltip />
                <el-table-column label="PSI" width="130"><template #default="{ row }">{{ formatNumber(row.psi, 4) }}</template></el-table-column>
                <el-table-column label="判断" width="120"><template #default="{ row }"><el-tag size="small" :type="row.status === '显著漂移' ? 'danger' : row.status === '轻微漂移' ? 'warning' : row.status === '稳定' ? 'success' : 'info'">{{ row.status }}</el-tag></template></el-table-column>
              </el-table>
            </div>
          </section>
          <section class="panel mt-18">
            <div class="panel-header"><div><h2>数据版本</h2><p>每次确认替换保存当前训练数据快照，可恢复历史版本</p></div></div>
            <el-table class="data-table" :data="dataVersions" empty-text="暂无数据版本；确认一次数据替换后生成">
              <el-table-column prop="version" label="版本" min-width="190" class-name="mono"><template #default="{ row }"><span>{{ row.version }}</span><el-tag v-if="row.active" size="small" type="success" class="active-tag">当前数据</el-tag></template></el-table-column>
              <el-table-column label="创建时间" min-width="160"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column>
              <el-table-column label="更新对象" width="110"><template #default="{ row }">{{ row.kind === 'train' ? '训练数据' : '预测数据' }}</template></el-table-column>
              <el-table-column label="训练数据行数" min-width="140"><template #default="{ row }">{{ formatNumber(row.train_rows) }}</template></el-table-column>
              <el-table-column label="操作" width="100" fixed="right"><template #default="{ row }"><el-button v-if="!row.active" link type="primary" :loading="activatingData === row.version" @click="restoreDataVersion(row)">恢复</el-button><span v-else class="muted">正在使用</span></template></el-table-column>
            </el-table>
          </section>
          <section class="panel mt-18">
            <div class="panel-header"><div><h2>训练数据预览</h2><p>展示前 8 行与前 10 个原始字段，仅用于核对数据形态</p></div><el-button :icon="Refresh" :loading="dataLoading" @click="loadOverview">刷新概览</el-button></div>
            <el-table class="data-table" :data="overview?.preview || []" v-loading="dataLoading" empty-text="暂无预览数据" max-height="420">
              <el-table-column v-for="column in previewColumns" :key="column" :prop="column" :label="column" :min-width="column.length > 12 ? 190 : 115" show-overflow-tooltip />
            </el-table>
          </section>
        </template>
      </el-tab-pane>
      <el-tab-pane label="模型评估与版本" name="model">
        <el-result v-if="modelError && !metadata" icon="warning" title="模型信息不可用" :sub-title="modelError"><template #extra><el-button type="primary" @click="loadModel">重新加载</el-button></template></el-result>
        <template v-else>
          <section v-if="candidate" class="panel candidate-panel">
            <div class="panel-header"><div><h2>候选模型待确认</h2><p>{{ candidate.version }} 仅保存为候选版本，当前上线模型尚未改变</p></div><el-button type="primary" :loading="activating === candidate.version" @click="activate({ version: candidate.version })">确认上线此候选模型</el-button></div>
            <div class="candidate-comparison">
              <div><span>指标</span><strong>AUC</strong><strong>Recall</strong><strong>Brier</strong><strong>分类阈值</strong></div>
              <div><span>当前上线</span><strong>{{ formatNumber(metadata?.metrics?.xgboost?.auc, 4) }}</strong><strong>{{ formatNumber(metadata?.metrics?.xgboost?.recall, 4) }}</strong><strong>{{ formatNumber(metadata?.metrics?.xgboost?.brier, 4) }}</strong><strong>{{ formatNumber(metadata?.metrics?.xgboost?.threshold ?? metadata?.threshold, 3) }}</strong></div>
              <div class="candidate-values"><span>候选模型</span><strong>{{ formatNumber(candidate.metrics?.xgboost?.auc, 4) }}</strong><strong>{{ formatNumber(candidate.metrics?.xgboost?.recall, 4) }}</strong><strong>{{ formatNumber(candidate.metrics?.xgboost?.brier, 4) }}</strong><strong>{{ formatNumber(candidate.metrics?.xgboost?.threshold ?? candidate.threshold, 3) }}</strong></div>
            </div>
          </section>
          <div class="model-context" v-loading="modelLoading">
            <div><span>当前上线模型</span><strong>XGBoost</strong><small>{{ metadata?.version || '—' }}</small></div>
            <div><span>训练时间</span><strong class="context-value">{{ formatDate(metadata?.created_at) }}</strong><small>拟合 {{ formatNumber(metadata?.data_split?.fit_rows) }} · 校准 {{ formatNumber(metadata?.data_split?.calibration_rows) }} · 内部验证 {{ formatNumber(metadata?.validation_rows ?? metadata?.test_rows) }} 行</small></div>
            <div><span>分类 / 风险阈值</span><strong class="context-value">{{ formatNumber(metadata?.threshold, 3) }}</strong><small>中风险 ≥ {{ formatPercent(metadata?.risk_thresholds?.medium, 0) }} · 高风险 ≥ {{ formatPercent(metadata?.risk_thresholds?.high, 0) }}</small></div>
            <el-button :icon="Refresh" :loading="modelLoading" @click="loadModel">刷新评估</el-button>
          </div>
          <section class="panel mt-18">
            <div class="panel-header"><div><h2>模型卡</h2><p>当前上线模型的能力边界、决策规则与使用建议</p></div><span class="model-chip">{{ metadata?.version || '暂无模型' }}</span></div>
            <div class="model-card-grid">
              <div><span>适用场景</span><p>电信存量客户的流失风险分层、批量筛查与挽留优先级排序。</p></div>
              <div><span>训练数据</span><p>{{ formatNumber(metadata?.rows) }} 行；拟合 {{ formatNumber(metadata?.data_split?.fit_rows) }} / 校准 {{ formatNumber(metadata?.data_split?.calibration_rows) }} / 内部验证 {{ formatNumber(metadata?.validation_rows ?? metadata?.test_rows) }}。</p></div>
              <div><span>决策阈值</span><p>分类阈值 {{ formatNumber(metadata?.threshold, 3) }}，按最低召回率 {{ formatPercent(metadata?.threshold_optimization?.xgboost?.min_recall, 0) }} 优化，优先减少漏判。</p></div>
              <div><span>输入要求</span><p>需包含训练时的全部原始特征字段；缺失值由模型管道的中位数填补。</p></div>
              <div><span>已知限制</span><p>指标来自内部验证集；SHAP 为模型归因而非因果结论；尚无独立时间段的外部验证。</p></div>
              <div><span>使用建议</span><p>高风险名单建议人工复核后触达；批量结果应结合挽留成本与客户价值使用。</p></div>
            </div>
          </section>
          <div v-if="metadata?.threshold_optimization" class="inline-note mt-18"><span><strong>阈值与校准：</strong>两个模型均使用 sigmoid 概率校准；XGBoost 在校准集上以最低召回率 {{ formatPercent(metadata.threshold_optimization.xgboost.min_recall, 0) }} 为约束选择阈值 {{ formatNumber(metadata.threshold_optimization.xgboost.threshold, 3) }}，最终指标仅来自内部验证集。</span></div>
          <section class="panel mt-18">
            <div class="panel-header"><div><h2>解释性评估</h2><p>衡量 SHAP 归因是否聚焦、是否与逻辑回归一致，以及不同风险层的关键因素差异</p></div><el-button :icon="Refresh" :loading="explainLoading" @click="loadExplainability">刷新评估</el-button></div>
            <div v-if="explainability" class="explain-grid">
              <div class="explain-kpi"><span>归因集中度</span><strong>{{ formatPercent(explainability.concentration.top10_share, 1) }}</strong><small>前 10 个特征占全部平均 |SHAP| 的比例</small></div>
              <div class="explain-kpi"><span>模型一致率</span><strong>{{ formatPercent(explainability.model_agreement.rate, 0) }}</strong><small>XGBoost SHAP 与逻辑回归系数前 {{ explainability.model_agreement.total }} 名重合 {{ explainability.model_agreement.overlap }} 个</small></div>
              <div class="explain-kpi"><span>评估样本数</span><strong>{{ formatNumber(explainability.sample_count) }}</strong><small>来自训练时的验证样本抽样</small></div>
            </div>
            <div v-if="explainability" class="risk-group-grid">
              <div v-for="group in explainRiskGroups" :key="group.level" class="risk-group">
                <h3>{{ group.level }}<small>{{ formatNumber(group.count) }} 人</small></h3>
                <div v-for="(item, index) in group.top_features" :key="item.feature" class="risk-feature">
                  <span class="rank">{{ index + 1 }}</span>
                  <span class="name" :title="item.feature">{{ item.feature }}</span>
                  <span class="value">{{ formatNumber(item.mean_abs_shap, 3) }}</span>
                </div>
              </div>
            </div>
            <div v-else-if="!explainLoading" class="empty-block">当前模型缺少解释性评估产物</div>
            <div v-if="explainability" class="inline-note explain-note"><span>{{ explainability.note }}</span></div>
          </section>
          <section class="panel mt-18">
            <div class="panel-header"><div><h2>参数敏感性分析</h2><p>固定其他参数，只改变最大树深，观察内部验证集表现与训练耗时</p></div><el-button type="primary" :loading="sensitivityRunning" @click="runSensitivityAnalysis">{{ sensitivityRunning ? `正在训练深度 ${sensitivityProgress.current_depth ?? '—'}（${sensitivityProgress.completed}/${sensitivityProgress.total}）` : '运行参数敏感性实验' }}</el-button></div>
            <template v-if="sensitivity">
              <div class="panel-body"><EChart :option="sensitivityOption" height="280px" aria-label="不同最大树深对应的 AUC 变化折线图" /></div>
              <el-table class="data-table" :data="sensitivity.results">
                <el-table-column prop="max_depth" label="最大树深" width="100" />
                <el-table-column label="AUC" min-width="100"><template #default="{ row }"><span class="metric-value primary-model">{{ formatNumber(row.auc, 4) }}</span></template></el-table-column>
                <el-table-column label="Recall" min-width="100"><template #default="{ row }">{{ formatNumber(row.recall, 4) }}</template></el-table-column>
                <el-table-column label="Precision" min-width="110"><template #default="{ row }">{{ formatNumber(row.precision, 4) }}</template></el-table-column>
                <el-table-column label="F1" min-width="100"><template #default="{ row }">{{ formatNumber(row.f1, 4) }}</template></el-table-column>
                <el-table-column label="KS" min-width="100"><template #default="{ row }">{{ formatNumber(row.ks, 4) }}</template></el-table-column>
                <el-table-column label="训练耗时（秒）" min-width="130"><template #default="{ row }">{{ formatNumber(row.fit_seconds, 1) }}</template></el-table-column>
              </el-table>
              <div class="inline-note explain-note"><span>{{ sensitivity.note }} 实验基于 {{ formatNumber(sensitivity.sample_rows) }} 行训练数据、{{ formatNumber(sensitivity.feature_count) }} 个特征。</span></div>
            </template>
            <div v-else class="empty-block">{{ sensitivityRunning ? '实验正在后台运行，进度会实时更新…' : '暂无实验结果；完整实验约需 2–3 分钟' }}</div>
          </section>
          <section class="panel mt-18">
            <div class="panel-header"><div><h2>Lasso 特征筛选实验</h2><p>在同一三段拆分下比较全特征与 Lasso 子集，验证筛选是否掉点</p></div><el-button type="primary" :loading="featureSelectionRunning" @click="runFeatureSelectionExperiment">{{ featureSelectionRunning ? `正在评估 ${featureSelectionProgress.current_label || '—'}（${featureSelectionProgress.completed}/${featureSelectionProgress.total}）` : '运行特征筛选实验' }}</el-button></div>
            <template v-if="featureSelection">
              <el-table class="data-table" :data="featureSelection.results">
                <el-table-column prop="name" label="方案" min-width="150" />
                <el-table-column label="特征数" width="100"><template #default="{ row }">{{ formatNumber(row.feature_count) }}</template></el-table-column>
                <el-table-column label="AUC" min-width="100"><template #default="{ row }"><span class="metric-value primary-model">{{ formatNumber(row.auc, 4) }}</span></template></el-table-column>
                <el-table-column label="Recall" min-width="100"><template #default="{ row }">{{ formatNumber(row.recall, 4) }}</template></el-table-column>
                <el-table-column label="Precision" min-width="110"><template #default="{ row }">{{ formatNumber(row.precision, 4) }}</template></el-table-column>
                <el-table-column label="F1" min-width="100"><template #default="{ row }">{{ formatNumber(row.f1, 4) }}</template></el-table-column>
                <el-table-column label="耗时（秒）" min-width="110"><template #default="{ row }">{{ formatNumber(row.seconds, 1) }}</template></el-table-column>
              </el-table>
              <div class="inline-note explain-note"><span>{{ featureSelection.note }} 实验基于 {{ formatNumber(featureSelection.sample_rows) }} 行、{{ formatNumber(featureSelection.feature_count) }} 个特征。</span></div>
            </template>
            <div v-else class="empty-block">{{ featureSelectionRunning ? '实验正在后台运行，进度会实时更新…' : '暂无实验结果；完整实验约需 1–2 分钟' }}</div>
          </section>
          <section class="panel mt-18">
            <div class="panel-header"><div><h2>核心指标对比</h2><p>{{ metadata?.evaluation_scope || '内部验证集（历史版本未参与模型拟合）' }}；Brier 越低越好，其余指标越高越好</p></div><div class="panel-actions"><span class="model-chip">XGBoost vs 逻辑回归</span><el-button size="small" :loading="exportingReport" @click="exportReport">导出评估摘要</el-button></div></div>
            <el-table class="data-table metric-table" :data="metricRows" v-loading="modelLoading">
              <el-table-column prop="label" label="评估指标" min-width="180"><template #default="{ row }"><strong>{{ row.label }}</strong><small class="metric-note">{{ row.note }}</small></template></el-table-column>
              <el-table-column label="XGBoost" min-width="150"><template #default="{ row }"><span class="metric-value primary-model">{{ formatNumber(metadata?.metrics?.xgboost?.[row.key], 4) }}</span></template></el-table-column>
              <el-table-column label="逻辑回归" min-width="150"><template #default="{ row }"><span class="metric-value">{{ formatNumber(metadata?.metrics?.logistic_regression?.[row.key], 4) }}</span></template></el-table-column>
            </el-table>
          </section>
          <section class="panel mt-18">
            <div class="panel-header"><div><h2>混淆矩阵</h2><p>内部验证集预测结果；各模型使用校准集选择的分类阈值，行表示真实标签，列表示预测标签</p></div></div>
            <div class="matrix-layout">
              <div v-for="model in [{ key: 'xgboost', name: 'XGBoost' }, { key: 'logistic_regression', name: '逻辑回归' }]" :key="model.key" class="matrix-block">
                <h3>{{ model.name }} · 阈值 {{ formatNumber(metadata?.metrics?.[model.key]?.threshold ?? 0.5, 3) }}</h3>
                <div class="matrix-axis"><span /><span>预测未流失</span><span>预测已流失</span></div>
                <div class="matrix-row"><label>真实未流失</label><div class="matrix-cell correct"><strong>{{ formatNumber(metadata?.metrics?.[model.key]?.confusion_matrix?.[0]?.[0]) }}</strong><span>TN</span></div><div class="matrix-cell error"><strong>{{ formatNumber(metadata?.metrics?.[model.key]?.confusion_matrix?.[0]?.[1]) }}</strong><span>FP</span></div></div>
                <div class="matrix-row"><label>真实已流失</label><div class="matrix-cell error"><strong>{{ formatNumber(metadata?.metrics?.[model.key]?.confusion_matrix?.[1]?.[0]) }}</strong><span>FN</span></div><div class="matrix-cell correct"><strong>{{ formatNumber(metadata?.metrics?.[model.key]?.confusion_matrix?.[1]?.[1]) }}</strong><span>TP</span></div></div>
              </div>
            </div>
          </section>
          <div class="chart-grid mt-18">
            <section class="panel"><div class="panel-header"><div><h2>ROC 曲线</h2><p>比较不同阈值下的真正率与假阳性率</p></div></div><div class="panel-body"><EChart :option="rocOption" :loading="modelLoading" :empty="!metadata" height="340px" aria-label="XGBoost 与逻辑回归 ROC 曲线" /></div></section>
            <section class="panel"><div class="panel-header"><div><h2>PR 曲线</h2><p>关注流失正类的精确率与召回率权衡</p></div></div><div class="panel-body"><EChart :option="prOption" :loading="modelLoading" :empty="!metadata" height="340px" aria-label="XGBoost 与逻辑回归 PR 曲线" /></div></section>
          </div>
          <section v-if="cvModels.length" class="panel mt-18">
            <div class="panel-header"><div><h2>固定配置交叉验证</h2><p>{{ cvModels[0].value.note }}；评分指标为 ROC-AUC</p></div><span class="model-chip">{{ cvModels[0].value.folds }} 折 · random_state=42</span></div>
            <div class="cv-grid">
              <div v-for="model in cvModels" :key="model.key" class="cv-block"><div class="cv-head"><h3>{{ model.name }}</h3><strong>{{ formatNumber(model.value.auc_mean, 4) }} <small>± {{ formatNumber(model.value.auc_std, 4) }}</small></strong></div><div v-for="(score, index) in model.value.scores" :key="index" class="fold-row"><span>Fold {{ index + 1 }}</span><el-progress :percentage="Number((score * 100).toFixed(1))" :stroke-width="6" :show-text="false" color="#477dbb" /><strong>{{ formatNumber(score, 4) }}</strong></div></div>
            </div>
          </section>
          <section class="panel mt-18">
            <div class="panel-header"><div><h2>模型版本</h2><p>版本切换只改变当前上线指针，历史评估元数据保留可追溯</p></div></div>
            <el-table class="data-table" :data="versions" v-loading="modelLoading" empty-text="暂无模型版本">
              <el-table-column prop="version" label="版本" min-width="185" class-name="mono"><template #default="{ row }"><span>{{ row.version }}</span><el-tag v-if="row.active" size="small" type="success" class="active-tag">当前上线</el-tag></template></el-table-column>
              <el-table-column label="创建时间" min-width="160"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column>
              <el-table-column label="XGBoost AUC" width="130"><template #default="{ row }">{{ formatNumber(row.metrics?.xgboost?.auc, 4) }}</template></el-table-column>
              <el-table-column label="训练 / 内部验证行数" min-width="160"><template #default="{ row }">{{ formatNumber(row.rows) }} / {{ formatNumber(row.validation_rows ?? row.test_rows) }}</template></el-table-column>
              <el-table-column label="操作" width="170" fixed="right"><template #default="{ row }"><el-button v-if="!row.active && isAdmin" link type="primary" :loading="activating === row.version" @click="activate(row)">切换上线</el-button><el-button v-if="!row.active && isAdmin" link type="danger" :loading="deleting === row.version" @click="deleteVersion(row)">删除</el-button><span v-if="row.active" class="muted">正在使用</span><span v-else-if="!isAdmin" class="muted">仅管理员</span></template></el-table-column>
            </el-table>
          </section>
        </template>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.data-model-tabs :deep(.el-tabs__header) { margin-bottom: 20px; }.data-model-tabs :deep(.el-tabs__item) { height: 42px; padding: 0 22px; }
.model-context { min-height: 94px; display: grid; grid-template-columns: 1.1fr 1.2fr 1fr auto; align-items: center; gap: 24px; padding: 18px 22px; background: #102a43; color: #fff; border-radius: 10px; }.model-context > div > span { display: block; color: #91a8bb; font-size: 10px; }.model-context > div > strong { display: block; font-size: 22px; margin-top: 6px; }.model-context > div > strong.context-value { font-size: 16px; font-weight: 550; }.model-context small { display: block; color: #91a8bb; font-size: 10px; margin-top: 5px; }.model-context :deep(.el-button) { background: transparent; border-color: #54718c; color: #d7e3ed; }
.model-chip { padding: 4px 8px; background: #edf2f7; color: #536776; border-radius: 4px; font-size: 10px; }.metric-note { display: inline-block; color: #9aa6af; font-size: 10px; margin-left: 9px; }.metric-table strong { font-weight: 550; color: #405767; }.metric-value { font-variant-numeric: tabular-nums; color: #405767; }.primary-model { color: #2563c7; font-weight: 650; }
.matrix-layout { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 50px; padding: 24px; }.matrix-block { max-width: 470px; width: 100%; margin: 0 auto; }.matrix-block h3 { margin: 0 0 16px; text-align: center; color: #102a43; font-size: 13px; }.matrix-axis, .matrix-row { display: grid; grid-template-columns: 92px 1fr 1fr; gap: 7px; align-items: stretch; }.matrix-axis { margin-bottom: 7px; }.matrix-axis span { display: grid; place-items: center; color: #7a8a97; font-size: 10px; }.matrix-row { margin-bottom: 7px; }.matrix-row label { display: flex; align-items: center; color: #7a8a97; font-size: 10px; }.matrix-cell { min-height: 76px; display: flex; align-items: center; justify-content: center; gap: 10px; border-radius: 6px; }.matrix-cell strong { font-size: 24px; font-weight: 600; }.matrix-cell span { font-size: 10px; opacity: .7; }.matrix-cell.correct { background: #e9f0f7; color: #2d5f8d; }.matrix-cell.error { background: #f8eeee; color: #ae5555; }
.cv-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0; }.cv-block { padding: 22px 26px; }.cv-block + .cv-block { border-left: 1px solid #e2e7eb; }.cv-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin-bottom: 17px; }.cv-head h3 { margin: 0; color: #102a43; font-size: 13px; }.cv-head > strong { color: #2563c7; font-size: 18px; }.cv-head small { color: #7a8a97; font-size: 11px; font-weight: 400; }.fold-row { display: grid; grid-template-columns: 55px 1fr 55px; align-items: center; gap: 12px; margin-top: 12px; }.fold-row > span { color: #7a8a97; font-size: 10px; }.fold-row > strong { color: #536776; font-size: 11px; font-weight: 500; text-align: right; }
.active-tag { margin-left: 9px; }
.upload-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }.file-input { flex: 1; min-width: 260px; padding: 7px 10px; border: 1px solid #dce3e8; border-radius: 6px; color: #536776; background: #fff; font-size: 12px; }.staged-area { margin-top: 16px; }.staged-table { margin-top: 12px; }.staged-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.schema-strip { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; padding: 12px 18px; border-bottom: 1px solid #e8edf0; background: #f7f9fa; }.schema-strip span { padding: 8px 10px; color: #587080; font-size: 11px; line-height: 1.6; }.schema-strip .issue, .issue-text { color: #b54949; font-weight: 600; }.drift-section { padding: 18px; border-top: 1px solid #e8edf0; }.drift-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 20px; margin-bottom: 12px; }.drift-heading h3 { margin: 0; color: #233e52; font-size: 13px; }.drift-heading span { color: #7a8a97; font-size: 10px; text-align: right; }
.candidate-panel { margin-bottom: 18px; border: 1px solid #b8cce0; }.candidate-comparison { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); padding: 18px 22px; }.candidate-comparison > div { display: grid; grid-template-columns: 1fr; gap: 9px; }.candidate-comparison > div + div { padding-left: 22px; border-left: 1px solid #e5eaee; }.candidate-comparison span { margin-bottom: 3px; color: #7a8a97; font-size: 11px; }.candidate-comparison strong { color: #405767; font-size: 13px; font-weight: 550; }.candidate-comparison .candidate-values strong { color: #2563c7; }
.explain-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-bottom: 1px solid #e8edf0; }
.explain-kpi { padding: 18px 22px; }.explain-kpi + .explain-kpi { border-left: 1px solid #e8edf0; }
.explain-kpi span { display: block; color: #7a8a97; font-size: 11px; }.explain-kpi strong { display: block; margin-top: 7px; color: #102a43; font-size: 24px; font-variant-numeric: tabular-nums; }
.explain-kpi small { display: block; margin-top: 6px; color: #8a98a4; font-size: 10px; line-height: 1.6; }
.risk-group-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px; padding: 20px 22px 6px; }
.risk-group h3 { display: flex; align-items: baseline; justify-content: space-between; margin: 0 0 8px; color: #233e52; font-size: 13px; }
.risk-group h3 small { color: #8a98a4; font-size: 10px; font-weight: 400; }
.risk-feature { display: grid; grid-template-columns: 18px minmax(0, 1fr) 58px; gap: 8px; align-items: center; padding: 7px 0; border-bottom: 1px solid #f1f4f6; color: #435a6b; font-size: 12px; }
.risk-feature .rank { color: #a4b0ba; font-size: 10px; }.risk-feature .name { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.risk-feature .value { color: #2563c7; text-align: right; font-variant-numeric: tabular-nums; }
.explain-note { margin: 4px 22px 18px; }
.panel-actions { display: flex; align-items: center; gap: 10px; }
.model-card-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; background: #edf0f2; }
.model-card-grid > div { padding: 16px 20px; background: #fff; }
.model-card-grid span { display: block; color: #7a8a97; font-size: 11px; }
.model-card-grid p { margin: 8px 0 0; color: #405767; font-size: 12px; line-height: 1.75; }
@media (max-width: 900px) { .model-card-grid { grid-template-columns: 1fr; } }
.eda-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; padding: 16px 18px; }
.eda-block h3 { margin: 0 0 6px; color: #233e52; font-size: 13px; }
.eda-bin-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 18px 4px; border-top: 1px solid #edf0f2; }
.eda-bin-head h3 { margin: 0; color: #233e52; font-size: 13px; }
.eda-select { width: 260px; }
.eda-note { margin: 0 18px 18px; }
@media (max-width: 900px) { .eda-grid { grid-template-columns: 1fr; gap: 16px; } .eda-select { width: 100%; } }
@media (max-width: 1050px) { .risk-group-grid { grid-template-columns: 1fr; gap: 18px; } }
@media (max-width: 800px) { .explain-grid { grid-template-columns: 1fr; }.explain-kpi + .explain-kpi { border-left: 0; border-top: 1px solid #e8edf0; } }
@media (max-width: 540px) { .explain-kpi { padding: 14px 12px; }.risk-group-grid { padding: 16px 12px 4px; } }
@media (max-width: 1050px) { .model-context { grid-template-columns: repeat(3, 1fr); }.model-context > .el-button { grid-column: 3; justify-self: end; } }
@media (max-width: 800px) { .matrix-layout, .cv-grid { grid-template-columns: 1fr; }.matrix-layout { gap: 28px; }.cv-block + .cv-block { border-left: 0; border-top: 1px solid #e2e7eb; }.model-context { grid-template-columns: 1fr 1fr; }.model-context > .el-button { grid-column: auto; }.model-context > div:nth-child(3) { display: none; } }
@media (max-width: 540px) { .model-context { grid-template-columns: 1fr; gap: 14px; }.model-context > div:nth-child(2) { display: none; }.model-context > .el-button { justify-self: start; }.matrix-layout { padding: 18px 10px; }.matrix-axis, .matrix-row { grid-template-columns: 70px 1fr 1fr; }.matrix-cell { min-height: 66px; }.metric-note { display: none; } }
</style>
