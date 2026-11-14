<script setup>
import { computed, onMounted, ref } from 'vue'
import { Download, Refresh, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { predictApi } from '../api'
import { getErrorMessage } from '../api/helpers'
import { formatDate, formatNumber, formatPercent } from '../utils/format'
import PageHeader from '../components/PageHeader.vue'
import RiskTag from '../components/RiskTag.vue'
import ShapWaterfall from '../components/ShapWaterfall.vue'
import EChart from '../components/EChart.vue'

const activeTab = ref('single')
const sampleLoading = ref(false)
const predicting = ref(false)
const record = ref({})
const result = ref(null)
const predictionError = ref('')
const keyFields = [
  { key: '客户ID', label: '客户 ID', type: 'text' },
  { key: '地理区域', label: '地理区域' },
  { key: '当前手机价格', label: '当前手机价格（元）' },
  { key: '当前设备使用天数', label: '当前设备使用天数' },
  { key: '在职总月数', label: '在职总月数' },
  { key: '平均月费用', label: '平均月费用（元）' },
  { key: '每月平均使用分钟数', label: '月均使用分钟数' },
  { key: '平均超额使用分钟数', label: '平均超额分钟数' },
  { key: '平均超额费用', label: '平均超额费用（元）' },
  { key: '当月使用分钟数与前三个月平均值的百分比变化', label: '当月使用分钟变化（%）' },
  { key: '当月费用与前三个月平均值的百分比变化', label: '当月费用变化（%）' },
  { key: '平均掉线语音呼叫数', label: '平均掉线语音呼叫数' },
  { key: '平均客户服务电话次数', label: '平均客服电话次数' },
  { key: '过去三个月的平均每月使用分钟数', label: '近三月月均使用分钟' },
]

async function loadSample() {
  sampleLoading.value = true
  predictionError.value = ''
  try {
    const data = await predictApi.sample()
    record.value = { ...data.record }
    result.value = null
  } catch (err) { predictionError.value = getErrorMessage(err) } finally { sampleLoading.value = false }
}
function invalidateResult() { result.value = null; predictionError.value = '' }
async function submitPrediction() {
  if (!Object.keys(record.value).length) { predictionError.value = '请先载入客户样本'; return }
  predicting.value = true
  predictionError.value = ''
  try {
    result.value = await predictApi.single(record.value)
    ElMessage.success('预测完成，结果已更新')
  } catch (err) { predictionError.value = getErrorMessage(err) } finally { predicting.value = false }
}

const fileList = ref([])
const selectedFile = ref(null)
const uploading = ref(false)
const batchResult = ref(null)
const batchError = ref('')
const batches = ref([])
const historyLoading = ref(false)
const downloading = ref('')
const deleting = ref('')
const batchProgress = ref(0)
const batchProcessed = ref(0)
const batchTotal = ref(0)

function handleFile(uploadFile) {
  const extension = uploadFile.name.split('.').pop()?.toLowerCase()
  if (!['csv', 'xlsx', 'xls'].includes(extension)) {
    fileList.value = []
    selectedFile.value = null
    ElMessage.error('仅支持 CSV、XLSX 或 XLS 文件')
    return
  }
  selectedFile.value = uploadFile.raw
  batchResult.value = null
  batchError.value = ''
}
function removeFile() { selectedFile.value = null; batchResult.value = null }
async function waitBatch(jobId) {
  for (;;) {
    const job = await predictApi.batchStatus(jobId)
    batchTotal.value = job.total
    batchProcessed.value = job.processed
    batchProgress.value = Math.round((job.progress || 0) * 100)
    if (job.status === 'succeeded') {
      batchResult.value = job.result
      ElMessage.success(`已完成 ${formatNumber(job.result.total)} 条客户记录预测`)
      await loadBatches()
      window.dispatchEvent(new CustomEvent('prediction:updated'))
      return
    }
    if (job.status === 'failed') throw new Error(job.error || '批量预测失败')
    await new Promise((resolve) => window.setTimeout(resolve, 1000))
  }
}
async function uploadBatch() {
  if (!selectedFile.value) { batchError.value = '请先选择待预测文件'; return }
  uploading.value = true
  batchError.value = ''
  batchProgress.value = 0
  batchProcessed.value = 0
  batchTotal.value = 0
  try {
    const job = await predictApi.batch(selectedFile.value)
    batchTotal.value = job.total
    await waitBatch(job.job_id)
  } catch (err) { batchError.value = getErrorMessage(err) } finally { uploading.value = false }
}
async function loadBatches() {
  historyLoading.value = true
  try { batches.value = await predictApi.batches() } catch (err) { ElMessage.error(getErrorMessage(err)) } finally { historyLoading.value = false }
}
async function downloadBatch(row) {
  downloading.value = row.batch_id
  try {
    const response = await predictApi.exportBatch(row.batch_id)
    const url = URL.createObjectURL(new Blob([response.data], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `churn_${row.batch_id}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (err) { ElMessage.error(getErrorMessage(err)) } finally { downloading.value = '' }
}
async function selectBatch(row) {
  batchResult.value = {
    batch_id: row.batch_id,
    filename: row.filename,
    total: row.total,
    low: row.low,
    medium: row.medium,
    high: row.high,
    model_version: row.model_version,
    from_history: true,
  }
  ElMessage.success(`已载入历史批次 ${row.filename}`)
}
async function deleteBatch(row) {
  try {
    await ElMessageBox.confirm(`确认删除批次 ${row.batch_id}？该批次全部 ${row.total} 条预测结果将被永久移除。`, '删除批次', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  deleting.value = row.batch_id
  try {
    await predictApi.deleteBatch(row.batch_id)
    ElMessage.success('批次已删除')
    if (batchResult.value?.batch_id === row.batch_id) batchResult.value = null
    await loadBatches()
    window.dispatchEvent(new CustomEvent('prediction:updated'))
  } catch (err) { ElMessage.error(getErrorMessage(err)) } finally { deleting.value = '' }
}
const batchOption = computed(() => ({
  color: ['#8ba5b7', '#d49b3e', '#d94b4b'],
  tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 人 · {d}%' },
  legend: { bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { color: '#657786', fontSize: 11 } },
  series: [{ type: 'pie', radius: ['48%', '70%'], center: ['50%', '42%'], itemStyle: { borderColor: '#fffefb', borderWidth: 3 }, label: { show: false }, data: batchResult.value ? [{ name: '低风险', value: batchResult.value.low }, { name: '中风险', value: batchResult.value.medium }, { name: '高风险', value: batchResult.value.high }] : [] }],
}))

onMounted(() => { loadSample(); loadBatches() })
</script>

<template>
  <div class="workspace-page">
    <PageHeader title="流失预测" description="对单个客户进行可解释的流失风险评估，或上传完整数据文件执行批量预测与结果导出。" />
    <el-tabs v-model="activeTab" class="prediction-tabs">
      <el-tab-pane label="单客户预测" name="single">
        <div class="prediction-layout">
          <section class="panel input-panel">
            <div class="panel-header"><div><h2>客户特征输入</h2><p>展示 14 个关键字段；其余样本字段在提交时完整保留</p></div><el-button :icon="Refresh" :loading="sampleLoading" @click="loadSample">载入演示客户</el-button></div>
            <div class="panel-body" v-loading="sampleLoading">
              <el-form label-position="top" @submit.prevent="submitPrediction">
                <div class="field-grid">
                  <el-form-item v-for="field in keyFields" :key="field.key" :label="field.label">
                    <el-input v-if="field.type === 'text'" v-model="record[field.key]" placeholder="客户标识" @input="invalidateResult" />
                    <el-input-number v-else v-model="record[field.key]" :controls="false" placeholder="请输入数值" style="width:100%" @change="invalidateResult" />
                  </el-form-item>
                </div>
                <el-alert v-if="predictionError && !result" class="form-error" :title="predictionError" type="error" :closable="false" show-icon />
                <div class="predict-actions"><span>修改任一字段后，需重新生成预测结果</span><el-button type="primary" native-type="submit" :loading="predicting" :disabled="sampleLoading">{{ predicting ? '正在计算…' : '生成流失预测' }}</el-button></div>
              </el-form>
            </div>
          </section>
          <section class="panel result-panel" aria-live="polite" aria-busy="predicting">
            <div class="panel-header"><div><h2>预测与归因结果</h2><p>结果基于当前生效模型实时计算</p></div><RiskTag v-if="result" :level="result.risk_level" /></div>
            <div v-if="result" class="result-content">
              <div class="probability-result"><span>客户 {{ result.customer_id }} 的流失概率</span><strong>{{ formatPercent(result.probability, 2) }}</strong><el-progress :percentage="Number((result.probability * 100).toFixed(1))" :stroke-width="7" :show-text="false" :color="result.probability >= .7 ? '#d94b4b' : result.probability >= .4 ? '#d49b3e' : '#477dbb'" /><small>模型 {{ result.model_version }} · {{ formatDate(result.predicted_at) }}</small></div>
              <div class="result-section-head"><h3>Top SHAP 特征瀑布图</h3><div class="legend"><span class="legend-item"><i class="legend-dot" style="background:#d94b4b" />推高</span><span class="legend-item"><i class="legend-dot" style="background:#367bc5" />降低</span></div></div>
              <ShapWaterfall :features="result.top_features" :base-value="result.base_value" height="330px" />
              <div class="waterfall-note">从基线出发逐项累加 Top 特征贡献，虚线连接相邻累计位置；右侧为独立贡献数值。</div>
              <section class="advice-box"><h3>建议挽留动作</h3><p>{{ result.advice }}</p></section>
            </div>
            <div v-else class="result-empty"><div class="empty-symbol" aria-hidden="true">%</div><h3>{{ predicting ? '正在生成客户风险画像' : '等待生成预测' }}</h3><p>{{ predicting ? '模型正在计算概率与 SHAP 特征贡献…' : '核对左侧客户特征后，点击“生成流失预测”查看概率、归因和挽留建议。' }}</p></div>
          </section>
        </div>
      </el-tab-pane>
      <el-tab-pane label="批量预测" name="batch">
        <div class="batch-layout">
          <section class="panel">
            <div class="panel-header"><div><h2>上传客户数据</h2><p>支持 CSV、XLSX、XLS；字段需与模型原始特征一致</p></div></div>
            <div class="panel-body">
              <el-upload v-model:file-list="fileList" drag :auto-upload="false" :limit="1" accept=".csv,.xlsx,.xls" :on-change="handleFile" :on-remove="removeFile">
                <el-icon class="el-icon--upload"><UploadFilled /></el-icon><div class="el-upload__text">拖放文件到这里，或 <em>选择文件</em></div><template #tip><div class="el-upload__tip">文件由后端逐行全量处理，前端不限制、不截断数据行数</div></template>
              </el-upload>
              <el-alert v-if="batchError" :title="batchError" type="error" show-icon :closable="false" class="batch-error" />
              <el-button class="upload-button" type="primary" :loading="uploading" :disabled="!selectedFile" @click="uploadBatch">{{ uploading ? '正在后台预测…' : '开始批量预测' }}</el-button>
              <div v-if="uploading" class="batch-progress" aria-live="polite">
                <el-progress :percentage="batchProgress" :stroke-width="6" :show-text="false" />
                <span>正在分析 {{ formatNumber(batchProcessed) }} / {{ formatNumber(batchTotal) }} 行 · {{ batchProgress }}%</span>
              </div>
            </div>
          </section>
          <section class="panel batch-result" aria-live="polite" :aria-busy="uploading">
            <div class="panel-header"><div><h2>本批次风险分布</h2><p>{{ batchResult ? `${batchResult.filename} · 模型 ${batchResult.model_version}` : '完成上传后显示批次统计' }}</p></div></div>
            <template v-if="batchResult">
              <div class="batch-kpis"><div><span>有效记录</span><strong>{{ formatNumber(batchResult.total) }}</strong></div><div><span>高风险</span><strong class="high-number">{{ formatNumber(batchResult.high) }}</strong></div><div><span>中风险</span><strong>{{ formatNumber(batchResult.medium) }}</strong></div><div><span>低风险</span><strong>{{ formatNumber(batchResult.low) }}</strong></div></div>
              <EChart :option="batchOption" height="260px" aria-label="批量预测风险分布图" />
              <div v-if="batchResult.cleaning_report" class="cleaning-report">清洗前 {{ formatNumber(batchResult.cleaning_report.rows_before) }} 行 · 去重 {{ formatNumber(batchResult.cleaning_report.duplicates_removed) }} 行 · 缺失值 {{ formatNumber(batchResult.cleaning_report.missing_values) }} 个</div>
            </template>
            <div v-else class="empty-block">{{ uploading ? '任务正在后台运行，进度实时更新，可继续停留本页…' : '暂无新批次结果' }}</div>
          </section>
        </div>
        <section class="panel mt-18">
          <div class="panel-header"><div><h2>预测批次历史</h2><p>保留最近 50 个批次；导出文件包含该批次全部客户预测结果</p></div><el-button :icon="Refresh" :loading="historyLoading" @click="loadBatches">刷新历史</el-button></div>
          <el-table class="data-table" :data="batches" v-loading="historyLoading" empty-text="暂无批量预测记录">
            <el-table-column prop="batch_id" label="批次 ID" min-width="160" class-name="mono" />
            <el-table-column prop="filename" label="文件名" min-width="180" show-overflow-tooltip />
            <el-table-column label="预测时间" min-width="155"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column>
            <el-table-column prop="total" label="总客户" width="85" align="right" />
            <el-table-column label="低 / 中 / 高风险" min-width="150" align="center"><template #default="{ row }"><span class="numeric">{{ row.low }} / {{ row.medium }} / <strong class="high-number">{{ row.high }}</strong></span></template></el-table-column>
            <el-table-column prop="model_version" label="模型版本" min-width="160" show-overflow-tooltip />
            <el-table-column label="操作" width="200" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="selectBatch(row)">选择</el-button><el-button link type="primary" :icon="Download" :loading="downloading === row.batch_id" @click="downloadBatch(row)">CSV</el-button><el-button link type="danger" :loading="deleting === row.batch_id" @click="deleteBatch(row)">删除</el-button></template></el-table-column>
          </el-table>
        </section>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.prediction-tabs :deep(.el-tabs__header) { margin-bottom: 20px; }.prediction-tabs :deep(.el-tabs__item) { height: 42px; padding: 0 22px; }
.prediction-layout { display: grid; grid-template-columns: minmax(0, 1.08fr) minmax(420px, .92fr); gap: 18px; align-items: start; }
.result-panel { position: sticky; top: 84px; }
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 18px; }
.field-grid :deep(.el-form-item) { margin-bottom: 17px; }.field-grid :deep(.el-form-item__label) { font-size: 11px; margin-bottom: 5px; line-height: 1.5; }
.predict-actions { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding-top: 17px; border-top: 1px solid #edf0f2; }.predict-actions > span { color: #8a98a4; font-size: 10px; }.form-error { margin-bottom: 16px; }
.result-content { padding: 20px 20px 22px; }.probability-result > span { display: block; color: #657786; font-size: 12px; }.probability-result strong { display: block; color: #102a43; font-size: 40px; line-height: 1.25; letter-spacing: -.04em; margin: 8px 0 13px; font-variant-numeric: tabular-nums; }.probability-result small { display: block; color: #8a98a4; font-size: 10px; margin-top: 10px; }
.result-section-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin: 25px 0 2px; }.result-section-head h3, .advice-box h3 { margin: 0; color: #102a43; font-size: 13px; }
.waterfall-note { color: #8a98a4; font-size: 10px; line-height: 1.6; margin-top: -4px; }
.advice-box { margin-top: 20px; padding: 16px 17px; background: #f1f5f9; border-left: 3px solid #2563c7; border-radius: 0 6px 6px 0; }.advice-box p { margin: 8px 0 0; color: #405767; font-size: 12px; line-height: 1.8; }
.result-empty { min-height: 570px; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px; text-align: center; }.empty-symbol { width: 52px; height: 52px; display: grid; place-items: center; border: 1px solid #dce5ed; color: #6d8ba5; font-size: 22px; border-radius: 50%; }.result-empty h3 { color: #405767; font-size: 14px; margin: 18px 0 8px; }.result-empty p { max-width: 310px; color: #8a98a4; font-size: 12px; line-height: 1.8; margin: 0; }
.batch-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }.upload-button { width: 100%; margin-top: 18px; }.batch-error { margin-top: 14px; }.batch-progress { margin-top: 12px; }.batch-progress span { display: block; margin-top: 7px; color: #7a8a97; font-size: 11px; text-align: center; }.batch-kpis { display: grid; grid-template-columns: repeat(4, 1fr); padding: 17px 18px 0; }.batch-kpis > div { text-align: center; }.batch-kpis span { display: block; color: #7a8a97; font-size: 10px; }.batch-kpis strong { display: block; color: #102a43; font-size: 22px; margin-top: 5px; }.high-number { color: #c74646 !important; }.cleaning-report { margin: 0 18px 17px; color: #7a8a97; font-size: 10px; text-align: center; }
@media (max-width: 1150px) { .prediction-layout { grid-template-columns: 1fr; }.result-panel { position: static; }.result-empty { min-height: 280px; } }
@media (max-width: 760px) { .batch-layout { grid-template-columns: 1fr; } }
@media (max-width: 540px) { .field-grid { grid-template-columns: 1fr; }.predict-actions { align-items: stretch; flex-direction: column; }.predict-actions .el-button { width: 100%; }.result-content { padding: 16px 10px; }.batch-kpis { padding-left: 8px; padding-right: 8px; } }
</style>
