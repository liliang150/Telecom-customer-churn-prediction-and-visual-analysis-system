<script setup>
import { onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { systemApi } from '../api'
import { getErrorMessage } from '../api/helpers'
import { formatNumber } from '../utils/format'
import PageHeader from '../components/PageHeader.vue'

const loading = ref(false)
const error = ref('')
const info = ref(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    info.value = await systemApi.info()
  } catch (err) {
    error.value = getErrorMessage(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="workspace-page">
    <PageHeader title="系统信息" description="展示系统运行时环境、当前模型与数据版本、依赖版本和接口清单。">
      <template #actions><el-button :icon="Refresh" :loading="loading" @click="load">刷新信息</el-button></template>
    </PageHeader>
    <el-result v-if="error && !info" icon="warning" title="系统信息不可用" :sub-title="error">
      <template #extra><el-button type="primary" @click="load">重新加载</el-button></template>
    </el-result>
    <template v-else>
      <section class="info-grid" v-loading="loading">
        <div class="info-card"><span>系统名称</span><strong>{{ info?.name || '—' }}</strong><small>版本 {{ info?.version || '—' }}</small></div>
        <div class="info-card"><span>运行环境</span><strong>Python {{ info?.python || '—' }}</strong><small>{{ info?.platform || '—' }}</small></div>
        <div class="info-card"><span>数据库</span><strong>{{ info?.database?.engine || '—' }}</strong><small>{{ info?.database?.file || '—' }}</small></div>
        <div class="info-card"><span>当前模型</span><strong>{{ info?.model?.version || '未上线' }}</strong><small>{{ info?.model ? `AUC ${formatNumber(info.model.auc, 4)} · Recall ${formatNumber(info.model.recall, 4)}` : '暂无可用模型' }}</small></div>
        <div class="info-card"><span>训练数据 / 特征</span><strong>{{ formatNumber(info?.model?.rows) }} 行</strong><small>{{ formatNumber(info?.model?.feature_count) }} 个模型输入特征</small></div>
        <div class="info-card"><span>数据版本</span><strong>{{ info?.data_version || '默认数据' }}</strong><small>当前活动训练数据版本</small></div>
      </section>
      <section class="panel mt-18">
        <div class="panel-header"><div><h2>依赖版本</h2><p>系统实际运行的 Python 依赖，来自运行时读取</p></div></div>
        <div class="dependency-grid"><div v-for="(version, name) in info?.dependencies || {}" :key="name"><span>{{ name }}</span><strong>{{ version || '未安装' }}</strong></div></div>
      </section>
      <section class="panel mt-18">
        <div class="panel-header"><div><h2>功能模块</h2><p>系统对外提供的业务能力</p></div><span class="panel-badge">{{ info?.modules?.length || 0 }} 个模块</span></div>
        <el-table class="data-table" :data="info?.modules || []">
          <el-table-column prop="name" label="模块" width="150" />
          <el-table-column prop="description" label="说明" />
        </el-table>
      </section>
      <section class="panel mt-18">
        <div class="panel-header"><div><h2>接口清单</h2><p>由运行中的应用动态读取，共 {{ info?.routes?.length || 0 }} 个 API 接口</p></div></div>
        <el-table class="data-table" :data="info?.routes || []" max-height="480">
          <el-table-column prop="tag" label="分组" width="120" />
          <el-table-column label="方法" width="110"><template #default="{ row }"><span class="method">{{ row.methods.join(' / ') }}</span></template></el-table-column>
          <el-table-column prop="path" label="路径" min-width="260" class-name="mono" />
          <el-table-column prop="name" label="处理函数" min-width="190" show-overflow-tooltip />
        </el-table>
      </section>
    </template>
  </div>
</template>

<style scoped>
.info-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; background: #e8edf0; border: 1px solid #e8edf0; border-radius: 8px; overflow: hidden; }
.info-card { padding: 18px 20px; background: #fff; }
.info-card span { display: block; color: #7a8a97; font-size: 11px; }
.info-card strong { display: block; margin-top: 8px; color: #102a43; font-size: 18px; font-weight: 600; word-break: break-all; }
.info-card small { display: block; margin-top: 6px; color: #8a98a4; font-size: 10px; line-height: 1.6; }
.dependency-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; background: #edf0f2; }
.dependency-grid > div { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding: 14px 20px; background: #fff; }
.dependency-grid span { color: #657786; font-size: 12px; }.dependency-grid strong { color: #233e52; font-size: 13px; }
.panel-badge { color: #657786; background: #f0f3f6; border-radius: 4px; padding: 4px 8px; font-size: 10px; }
.method { color: #2563c7; font-size: 11px; font-weight: 600; }
@media (max-width: 1000px) { .info-grid, .dependency-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 640px) { .info-grid, .dependency-grid { grid-template-columns: 1fr; } }
</style>
