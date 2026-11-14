<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Lock, User } from '@element-plus/icons-vue'
import { useAuth } from '../stores/auth'
import { getErrorMessage } from '../api/helpers'

const router = useRouter()
const route = useRoute()
const { login } = useAuth()
const form = reactive({ username: 'admin', password: 'admin123' })
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (!form.username.trim() || !form.password) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  try {
    await login({ username: form.username.trim(), password: form.password })
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/dashboard'
    await router.replace(redirect)
  } catch (err) {
    error.value = getErrorMessage(err)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-context" aria-label="平台介绍">
      <div class="login-brand"><div class="login-mark"><span /><span /><span /></div><strong>流失智析</strong></div>
      <div class="context-copy">
        <span class="eyebrow">TELECOM CUSTOMER INTELLIGENCE</span>
        <h1>把客户风险转化为<br>清晰的运营行动</h1>
        <p>基于 XGBoost 的电信客户流失预测与可视化分析系统</p>
      </div>
      <div class="context-foot"><span>风险识别</span><i /><span>特征归因</span><i /><span>精准挽留</span></div>
    </section>
    <section class="login-workspace">
      <form class="login-form" @submit.prevent="submit">
        <div class="form-heading"><span>运营工作台</span><h2>欢迎登录</h2><p>使用系统账户进入客户风险工作区</p></div>
        <div class="field-group">
          <label for="username">用户名</label>
          <el-input id="username" v-model="form.username" size="large" autocomplete="username" placeholder="请输入用户名" :prefix-icon="User" @keyup.enter="submit" />
        </div>
        <div class="field-group">
          <label for="password">密码</label>
          <el-input id="password" v-model="form.password" size="large" type="password" show-password autocomplete="current-password" placeholder="请输入密码" :prefix-icon="Lock" @keyup.enter="submit" />
        </div>
        <div class="login-error" aria-live="polite">{{ error }}</div>
        <el-button type="primary" size="large" native-type="submit" :loading="loading" :disabled="loading">{{ loading ? '正在验证…' : '进入工作台' }}</el-button>
        <div class="login-hint"><span>答辩演示账户</span><code>admin / admin123</code></div>
      </form>
      <footer>毕业设计 · 电信客户流失智能运营平台</footer>
    </section>
  </main>
</template>

<style scoped>
.login-page { min-height: 100vh; display: grid; grid-template-columns: minmax(380px, .95fr) minmax(460px, 1.05fr); background: #fffefb; }
.login-context { background: #102a43; color: #fff; padding: 48px clamp(40px, 6vw, 92px) 38px; display: flex; flex-direction: column; position: relative; overflow: hidden; }
.login-context::after { content: ""; position: absolute; right: -120px; bottom: 12%; width: 360px; height: 360px; border: 1px solid rgba(150,184,217,.12); border-radius: 50%; box-shadow: 0 0 0 70px rgba(150,184,217,.035), 0 0 0 140px rgba(150,184,217,.025); pointer-events: none; }
.login-brand { display: flex; align-items: center; gap: 12px; font-size: 18px; letter-spacing: .1em; }
.login-mark { width: 32px; height: 32px; border: 1px solid rgba(255,255,255,.4); border-radius: 7px; padding: 7px; display: flex; align-items: flex-end; gap: 3px; }
.login-mark span { width: 4px; background: #d7e7f8; }.login-mark span:nth-child(1) { height: 8px; }.login-mark span:nth-child(2) { height: 17px; }.login-mark span:nth-child(3) { height: 12px; }
.context-copy { margin: auto 0; position: relative; z-index: 1; }
.eyebrow { color: #89a6c0; font-size: 10px; letter-spacing: .18em; }
.context-copy h1 { margin: 22px 0 20px; font-size: clamp(31px, 3.4vw, 46px); line-height: 1.4; letter-spacing: -.02em; font-weight: 550; }
.context-copy p { color: #a9bccb; max-width: 390px; font-size: 14px; line-height: 1.8; }
.context-foot { display: flex; align-items: center; gap: 13px; color: #91a8bb; font-size: 11px; position: relative; z-index: 1; }.context-foot i { width: 3px; height: 3px; background: #59748c; border-radius: 50%; }
.login-workspace { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 28px 24px; }
.login-form { width: min(100%, 390px); margin: auto; }
.form-heading > span { color: #2563c7; font-size: 11px; letter-spacing: .12em; }
.form-heading h2 { margin: 13px 0 9px; font-size: 29px; font-weight: 600; color: #102a43; }
.form-heading p { margin: 0 0 34px; color: #788895; font-size: 13px; }
.field-group { margin-bottom: 20px; }.field-group label { display: block; margin-bottom: 8px; color: #3d5569; font-size: 12px; font-weight: 550; }
.field-group :deep(.el-input__wrapper) { padding: 4px 13px; }
.login-error { min-height: 25px; color: #c74646; font-size: 12px; margin-top: -4px; }
.login-form > .el-button { width: 100%; height: 44px; }
.login-hint { margin-top: 20px; display: flex; justify-content: space-between; color: #8a98a4; font-size: 11px; }.login-hint code { color: #597185; font-family: inherit; }
.login-workspace footer { color: #9aa6af; font-size: 10px; text-align: center; }
@media (max-width: 760px) { .login-page { grid-template-columns: 1fr; }.login-context { display: none; }.login-workspace { min-height: 100vh; padding: 32px 24px 22px; } }
</style>
