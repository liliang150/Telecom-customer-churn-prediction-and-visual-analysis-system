import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { title: '登录' } },
  {
    path: '/',
    component: () => import('../layouts/AppShell.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '风险总览' } },
      { path: 'customers', name: 'customers', component: () => import('../views/CustomersView.vue'), meta: { title: '重点客户' } },
      { path: 'features', name: 'features', component: () => import('../views/FeatureAnalysisView.vue'), meta: { title: '特征分析' } },
      { path: 'prediction', name: 'prediction', component: () => import('../views/PredictionView.vue'), meta: { title: '流失预测' } },
      { path: 'data-model', name: 'data-model', component: () => import('../views/DataModelView.vue'), meta: { title: '数据与模型' } },
      { path: 'system', name: 'system', component: () => import('../views/SystemInfoView.vue'), meta: { title: '系统信息' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  const { isAuthenticated } = useAuth()
  if (to.path !== '/login' && !isAuthenticated.value) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/login' && isAuthenticated.value) return '/dashboard'
  document.title = `${to.meta.title || '工作台'} · 客户流失智能运营平台`
  return true
})

export default router
