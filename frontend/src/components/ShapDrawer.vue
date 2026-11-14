<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { analysisApi } from '../api'
import { getErrorMessage } from '../api/helpers'
import { formatPercent } from '../utils/format'
import RiskTag from './RiskTag.vue'
import ShapWaterfall from './ShapWaterfall.vue'

const props = defineProps({ modelValue: Boolean, customerId: { type: [String, Number], default: '' } })
const emit = defineEmits(['update:modelValue'])
const visible = computed({ get: () => props.modelValue, set: (value) => emit('update:modelValue', value) })
const loading = ref(false)
const result = ref(null)
const error = ref('')

async function load() {
  if (!visible.value || !props.customerId) return
  loading.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await analysisApi.shap(props.customerId)
  } catch (err) {
    error.value = getErrorMessage(err)
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

watch(() => [props.customerId, props.modelValue], load, { immediate: true })
</script>

<template>
  <el-drawer v-model="visible" class="shap-drawer" size="520px" destroy-on-close :title="`客户 ${customerId} · 风险归因`">
    <div aria-live="polite">
      <template v-if="result">
        <div class="drawer-summary">
          <div><span>流失概率</span><strong>{{ formatPercent(result.probability) }}</strong></div>
          <RiskTag :level="result.risk_level" />
        </div>
        <p class="model-note">模型版本 {{ result.model_version }} · 基于当前生效模型解释</p>
        <div class="drawer-section-head">
          <h3>关键特征贡献</h3>
          <div class="legend"><span class="legend-item"><i class="legend-dot" style="background:#d94b4b" />推高</span><span class="legend-item"><i class="legend-dot" style="background:#367bc5" />降低</span></div>
        </div>
        <ShapWaterfall :features="result.top_features" :base-value="result.base_value" />
        <div class="contribution-list">
          <div v-for="item in result.top_features" :key="item.feature" class="contribution-row">
            <span>{{ item.feature }}</span>
            <span :class="item.shap_value >= 0 ? 'text-positive' : 'text-negative'" class="numeric">{{ item.shap_value >= 0 ? '+' : '' }}{{ Number(item.shap_value).toFixed(4) }}</span>
          </div>
        </div>
        <section class="advice-box">
          <h3>建议挽留动作</h3>
          <p>{{ result.advice }}</p>
        </section>
      </template>
      <div v-if="loading" class="empty-block"><span class="state-spinner" />正在计算客户归因…</div>
      <el-result v-else-if="error" icon="error" title="归因加载失败" :sub-title="error">
        <template #extra><el-button @click="load">重新加载</el-button></template>
      </el-result>
    </div>
  </el-drawer>
</template>

<style scoped>
.drawer-summary { display: flex; align-items: center; justify-content: space-between; padding-bottom: 16px; border-bottom: 1px solid #e2e7eb; }
.drawer-summary > div { display: flex; align-items: baseline; gap: 12px; }
.drawer-summary span { color: #657786; font-size: 12px; }
.drawer-summary strong { font-size: 28px; color: #102a43; }
.model-note { color: #7a8a97; font-size: 11px; margin: 9px 0 22px; }
.drawer-section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.drawer-section-head h3, .advice-box h3 { margin: 0; font-size: 14px; color: #102a43; }
.contribution-list { margin-top: 4px; border-top: 1px solid #edf0f2; }
.contribution-row { display: flex; justify-content: space-between; gap: 16px; padding: 10px 2px; border-bottom: 1px solid #edf0f2; font-size: 12px; color: #536776; }
.advice-box { margin-top: 22px; padding: 17px 18px; background: #f1f5f9; border-left: 3px solid #2563c7; border-radius: 0 6px 6px 0; }
.advice-box p { margin: 9px 0 0; color: #405767; font-size: 13px; line-height: 1.8; }
.state-spinner { width: 16px; height: 16px; border: 2px solid #d7e2ef; border-top-color: #2563c7; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
:global(.shap-drawer) { max-width: 94vw; }
</style>
