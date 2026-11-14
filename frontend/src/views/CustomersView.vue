<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Refresh, Search } from '@element-plus/icons-vue'
import { analysisApi } from '../api'
import { getErrorMessage } from '../api/helpers'
import { featureValue, formatNumber, formatPercent } from '../utils/format'
import PageHeader from '../components/PageHeader.vue'
import RiskTag from '../components/RiskTag.vue'
import ShapDrawer from '../components/ShapDrawer.vue'

const route = useRoute()
const loading = ref(false)
const error = ref('')
const result = ref({ items: [], total: 0, distribution: {}, regions: [] })
const filters = reactive({ risk_level: '', region: '', min_fee: null, customer_id: '', page: 1, page_size: 20 })
const drawerOpen = ref(false)
const selectedCustomer = ref('')

async function load() {
  loading.value = true
  error.value = ''
  const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== '' && value !== null && value !== undefined))
  try { result.value = await analysisApi.risk(params) } catch (err) { error.value = getErrorMessage(err) } finally { loading.value = false }
}
function applyFilters() { filters.page = 1; load() }
function resetFilters() { Object.assign(filters, { risk_level: '', region: '', min_fee: null, customer_id: '', page: 1, page_size: 20 }); load() }
function openShap(row) { selectedCustomer.value = row.customer_id; drawerOpen.value = true }

onMounted(() => {
  if (route.query.customer_id) {
    filters.customer_id = String(route.query.customer_id)
    selectedCustomer.value = filters.customer_id
    drawerOpen.value = true
  }
  load()
  window.addEventListener('prediction:updated', load)
})
onBeforeUnmount(() => window.removeEventListener('prediction:updated', load))
</script>

<template>
  <div class="workspace-page">
    <PageHeader title="重点客户" description="筛选当前预测范围内的客户，按流失概率降序确定挽留优先级并查看个体归因。">
      <template #actions><el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button></template>
    </PageHeader>
    <section class="filter-panel" aria-label="客户筛选">
      <el-form label-position="top" @submit.prevent="applyFilters">
        <div class="filter-grid">
          <el-form-item label="风险等级"><el-select v-model="filters.risk_level" clearable placeholder="全部风险" style="width:100%"><el-option label="高风险" value="高风险" /><el-option label="中风险" value="中风险" /><el-option label="低风险" value="低风险" /></el-select></el-form-item>
          <el-form-item label="地理区域"><el-select v-model="filters.region" clearable filterable placeholder="全部区域" style="width:100%"><el-option v-for="item in result.regions" :key="item.region" :label="`区域 ${item.region}（${item.total}）`" :value="item.region" /></el-select></el-form-item>
          <el-form-item label="最低平均月费"><el-input-number v-model="filters.min_fee" :min="0" :precision="2" :controls="false" placeholder="不限金额" style="width:100%" /></el-form-item>
          <el-form-item label="客户 ID"><el-input v-model="filters.customer_id" clearable placeholder="支持模糊查询" @keyup.enter="applyFilters" /></el-form-item>
          <div class="filter-actions"><el-button native-type="button" @click="resetFilters">重置</el-button><el-button type="primary" native-type="submit" :icon="Search" :loading="loading">查询客户</el-button></div>
        </div>
      </el-form>
    </section>
    <div class="risk-summary" aria-live="polite">
      <span>当前范围 <strong>{{ formatNumber(result.total) }}</strong> 位匹配客户</span>
      <div><span><i class="low" />低风险 {{ formatNumber(result.distribution?.低风险) }}</span><span><i class="medium" />中风险 {{ formatNumber(result.distribution?.中风险) }}</span><span><i class="high" />高风险 {{ formatNumber(result.distribution?.高风险) }}</span></div>
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="error-alert" />
    <section class="panel">
      <el-table class="data-table" :data="result.items" v-loading="loading" empty-text="没有符合条件的客户" row-key="customer_id">
        <el-table-column prop="customer_id" label="客户 ID" min-width="125" fixed="left" />
        <el-table-column label="流失概率（降序）" min-width="160"><template #default="{ row }"><div class="probability-cell"><strong>{{ formatPercent(row.probability, 2) }}</strong><el-progress :percentage="Math.round(row.probability * 100)" :show-text="false" :stroke-width="5" :color="row.probability >= .7 ? '#d94b4b' : row.probability >= .4 ? '#d49b3e' : '#6c94bd'" /></div></template></el-table-column>
        <el-table-column label="风险等级" width="100"><template #default="{ row }"><RiskTag :level="row.risk_level" /></template></el-table-column>
        <el-table-column prop="region" label="区域" width="90" />
        <el-table-column label="平均月费" min-width="115"><template #default="{ row }">¥ {{ formatNumber(row.monthly_fee, 2) }}</template></el-table-column>
        <el-table-column label="主要贡献特征" min-width="230"><template #default="{ row }"><span class="table-feature" :title="row.top_features?.map((item) => `${item.feature}：${featureValue(item.feature_value)}`).join('；')">{{ row.top_features?.[0]?.feature || '—' }}<template v-if="row.top_features?.[0]"> · {{ featureValue(row.top_features[0].feature_value) }}</template></span></template></el-table-column>
        <el-table-column prop="model_version" label="模型版本" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="100" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openShap(row)">SHAP 归因</el-button></template></el-table-column>
      </el-table>
      <div class="table-footer"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.page_size" :total="result.total" :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next, jumper" background @current-change="load" @size-change="applyFilters" /></div>
    </section>
    <ShapDrawer v-model="drawerOpen" :customer-id="selectedCustomer" />
  </div>
</template>

<style scoped>
.filter-panel { padding: 18px 20px 2px; background: #fffefb; border: 1px solid #e2e7eb; border-radius: 10px; }
.filter-grid { display: grid; grid-template-columns: 1fr 1.2fr 1fr 1.2fr auto; gap: 14px; align-items: end; }
.filter-grid :deep(.el-form-item) { margin-bottom: 16px; }.filter-grid :deep(.el-form-item__label) { font-size: 11px; line-height: 1.5; margin-bottom: 6px; }
.filter-actions { display: flex; gap: 8px; padding-bottom: 16px; }
.risk-summary { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 3px 13px; color: #657786; font-size: 12px; }
.risk-summary strong { color: #102a43; font-size: 15px; margin: 0 3px; }.risk-summary > div { display: flex; gap: 17px; }.risk-summary > div span { display: flex; align-items: center; gap: 6px; }.risk-summary i { width: 7px; height: 7px; border-radius: 50%; }.risk-summary .low { background: #8ba5b7; }.risk-summary .medium { background: #d49b3e; }.risk-summary .high { background: #d94b4b; }
.error-alert { margin-bottom: 12px; }
.probability-cell { display: grid; grid-template-columns: 58px minmax(50px, 1fr); align-items: center; gap: 10px; }.probability-cell strong { font-weight: 600; color: #314b60; font-variant-numeric: tabular-nums; }
@media (max-width: 1250px) { .filter-grid { grid-template-columns: repeat(4, 1fr); }.filter-actions { grid-column: 4; justify-content: flex-end; } }
@media (max-width: 850px) { .filter-grid { grid-template-columns: repeat(2, 1fr); }.filter-actions { grid-column: 2; } }
@media (max-width: 540px) { .filter-grid { grid-template-columns: 1fr; gap: 0; }.filter-actions { grid-column: auto; justify-content: stretch; }.filter-actions .el-button { flex: 1; }.risk-summary { align-items: flex-start; flex-direction: column; }.risk-summary > div { gap: 10px; flex-wrap: wrap; } }
</style>
