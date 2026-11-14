<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Aim, DataAnalysis, DataLine, InfoFilled, Menu, SwitchButton, TrendCharts, UserFilled,
} from '@element-plus/icons-vue'
import { authApi } from '../api'
import { useAuth } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const { state, logout } = useAuth()
const mobileOpen = ref(false)
const health = ref({ status: 'degraded', model_available: false, model_version: null })
const navItems = [
  { path: '/dashboard', label: '风险总览', icon: DataAnalysis },
  { path: '/customers', label: '重点客户', icon: UserFilled },
  { path: '/features', label: '特征分析', icon: TrendCharts },
  { path: '/prediction', label: '流失预测', icon: Aim },
  { path: '/data-model', label: '数据与模型', icon: DataLine },
  { path: '/system', label: '系统信息', icon: InfoFilled },
]
const pageTitle = computed(() => route.meta.title || '工作台')
let timer

async function loadHealth() {
  try { health.value = await authApi.health() } catch { health.value = { status: 'degraded' } }
}

function handleLogout() {
  logout()
  router.replace('/login')
}

function handleUnauthorized() {
  logout()
  if (route.path !== '/login') router.replace({ path: '/login', query: { redirect: route.fullPath } })
}

onMounted(() => {
  loadHealth()
  timer = window.setInterval(loadHealth, 60000)
  window.addEventListener('auth:unauthorized', handleUnauthorized)
  window.addEventListener('model:updated', loadHealth)
})
onBeforeUnmount(() => {
  window.clearInterval(timer)
  window.removeEventListener('auth:unauthorized', handleUnauthorized)
  window.removeEventListener('model:updated', loadHealth)
})
</script>

<template>
  <div class="app-shell">
    <button v-if="mobileOpen" class="nav-overlay" aria-label="关闭导航" @click="mobileOpen = false" />
    <aside class="sidebar" :class="{ 'mobile-open': mobileOpen }" aria-label="主导航">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true"><span /><span /><span /></div>
        <div><strong>流失智析</strong><small>CHURN INTELLIGENCE</small></div>
      </div>
      <div class="nav-caption">运营工作区</div>
      <nav class="nav-list">
        <router-link v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item" active-class="active" @click="mobileOpen = false">
          <el-icon :size="18"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="sidebar-foot">
        <span class="system-dot" :class="{ ok: health.status === 'ok' }" />
        <div><strong>预测服务{{ health.status === 'ok' ? '正常' : '待检查' }}</strong><small>XGBoost 运营决策支持</small></div>
      </div>
    </aside>

    <div class="shell-main">
      <header class="topbar">
        <div class="topbar-title">
          <button class="mobile-menu" aria-label="打开导航" @click="mobileOpen = true"><el-icon :size="21"><Menu /></el-icon></button>
          <span class="topbar-section">客户运营</span><span class="topbar-divider">/</span><strong>{{ pageTitle }}</strong>
        </div>
        <div class="topbar-right">
          <div class="model-state" :class="{ degraded: !health.model_available }" :title="health.model_version || '模型不可用'">
            <i /> <span>{{ health.model_available ? '模型已就绪' : '模型未就绪' }}</span>
            <small v-if="health.model_version">{{ health.model_version }}</small>
          </div>
          <div class="user-block"><span class="avatar">{{ state.user?.username?.slice(0, 1).toUpperCase() || 'A' }}</span><div><strong>{{ state.user?.username || 'admin' }}</strong><small>{{ state.user?.role === 'admin' ? '系统管理员' : '运营用户' }}</small></div></div>
          <button class="logout-button" title="退出登录" aria-label="退出登录" @click="handleLogout"><el-icon :size="18"><SwitchButton /></el-icon></button>
        </div>
      </header>
      <main class="content-area">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <keep-alive><component :is="Component" /></keep-alive>
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-shell { min-height: 100vh; display: grid; grid-template-columns: 208px minmax(0, 1fr); }
.sidebar { position: sticky; top: 0; height: 100vh; z-index: 40; display: flex; flex-direction: column; background: #102a43; color: #fff; }
.brand { height: 74px; display: flex; align-items: center; gap: 11px; padding: 0 20px; border-bottom: 1px solid rgba(255,255,255,.09); }
.brand-mark { width: 29px; height: 29px; display: flex; align-items: flex-end; justify-content: center; gap: 3px; padding: 6px; border: 1px solid rgba(255,255,255,.36); border-radius: 7px; }
.brand-mark span { width: 3px; border-radius: 1px; background: #dbe9fa; }
.brand-mark span:nth-child(1) { height: 7px; }.brand-mark span:nth-child(2) { height: 15px; }.brand-mark span:nth-child(3) { height: 11px; }
.brand strong { display: block; font-size: 16px; letter-spacing: .08em; }
.brand small { display: block; margin-top: 3px; font-size: 8px; letter-spacing: .12em; color: #94a9bc; }
.nav-caption { padding: 25px 21px 9px; color: #8299ad; font-size: 10px; letter-spacing: .14em; }
.nav-list { display: grid; gap: 4px; padding: 0 11px; }
.nav-item { height: 43px; padding: 0 12px; display: flex; align-items: center; gap: 12px; border-radius: 6px; color: #b6c6d4; font-size: 13px; position: relative; transition: background 180ms ease, color 180ms ease; }
.nav-item:hover { background: rgba(255,255,255,.055); color: #fff; }
.nav-item.active { background: #1c4467; color: #fff; }
.nav-item.active::before { content: ""; position: absolute; left: -11px; top: 11px; bottom: 11px; width: 3px; border-radius: 0 2px 2px 0; background: #78aef5; }
.sidebar-foot { margin: auto 15px 18px; padding: 15px 6px 0; border-top: 1px solid rgba(255,255,255,.1); display: flex; align-items: flex-start; gap: 9px; }
.system-dot { margin-top: 5px; width: 7px; height: 7px; border-radius: 50%; background: #d7a64a; box-shadow: 0 0 0 3px rgba(215,166,74,.12); flex-shrink: 0; }
.system-dot.ok { background: #73bda0; box-shadow: 0 0 0 3px rgba(115,189,160,.12); }
.sidebar-foot strong { display: block; font-size: 11px; font-weight: 500; color: #c5d2dd; }.sidebar-foot small { display: block; font-size: 9px; color: #718ba2; margin-top: 4px; }
.shell-main { min-width: 0; }
.topbar { height: 64px; position: sticky; top: 0; z-index: 30; padding: 0 28px; background: rgba(255,254,251,.96); border-bottom: 1px solid #e2e7eb; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.topbar-title { display: flex; align-items: center; gap: 10px; min-width: 0; font-size: 12px; }
.topbar-section, .topbar-divider { color: #8a98a4; }.topbar-title strong { color: #314b60; font-weight: 600; }
.topbar-right { display: flex; align-items: center; gap: 20px; }
.model-state { display: flex; align-items: center; gap: 7px; color: #3d6d5d; font-size: 11px; }
.model-state i { width: 6px; height: 6px; background: #52a17e; border-radius: 50%; }.model-state small { color: #8a98a4; max-width: 130px; overflow: hidden; text-overflow: ellipsis; }
.model-state.degraded { color: #a16c25; }.model-state.degraded i { background: #d69a37; }
.user-block { display: flex; align-items: center; gap: 9px; padding-left: 20px; border-left: 1px solid #e2e7eb; }
.avatar { width: 30px; height: 30px; display: grid; place-items: center; background: #eaf0f8; color: #285481; border-radius: 50%; font-size: 12px; font-weight: 650; }
.user-block strong { display: block; color: #314b60; font-size: 12px; }.user-block small { display: block; margin-top: 2px; color: #8a98a4; font-size: 9px; }
.logout-button, .mobile-menu { border: 0; background: transparent; color: #657786; cursor: pointer; width: 34px; height: 34px; display: grid; place-items: center; border-radius: 6px; }
.logout-button:hover, .mobile-menu:hover { background: #edf2f7; color: #2563c7; }
.mobile-menu { display: none; }
.content-area { padding: 26px 28px 36px; min-height: calc(100vh - 64px); }
.nav-overlay { display: none; }
@media (max-width: 1100px) { .model-state small { display: none; } .topbar-right { gap: 12px; } .user-block { padding-left: 12px; } }
@media (max-width: 800px) {
  .app-shell { grid-template-columns: 1fr; }
  .sidebar { position: fixed; left: 0; transform: translateX(-100%); width: 220px; transition: transform 200ms ease; box-shadow: 12px 0 30px rgba(10,32,53,.16); }
  .sidebar.mobile-open { transform: translateX(0); }
  .nav-overlay { display: block; position: fixed; inset: 0; z-index: 35; border: 0; background: rgba(10,32,53,.42); }
  .mobile-menu { display: grid; margin-left: -8px; }
  .topbar { padding: 0 18px; }.content-area { padding: 22px 18px 30px; }
  .topbar-section, .topbar-divider { display: none; }
}
@media (max-width: 540px) {
  .model-state span { display: none; }.user-block > div { display: none; }.user-block { border: 0; padding-left: 0; }
  .topbar-right { gap: 6px; }.topbar { height: 58px; }.content-area { min-height: calc(100vh - 58px); padding: 20px 12px 28px; }
}
</style>
