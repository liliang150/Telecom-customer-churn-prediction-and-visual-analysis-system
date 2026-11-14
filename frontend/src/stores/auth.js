import { computed, reactive } from 'vue'
import { authApi } from '../api'

function storedUser() {
  try {
    return JSON.parse(localStorage.getItem('churn_user') || 'null')
  } catch {
    return null
  }
}

const state = reactive({
  token: localStorage.getItem('churn_token') || '',
  user: storedUser(),
})

export function useAuth() {
  const isAuthenticated = computed(() => Boolean(state.token))
  const isAdmin = computed(() => state.user?.role === 'admin')

  async function login(credentials) {
    const data = await authApi.login(credentials)
    state.token = data.access_token
    state.user = { username: data.username, role: data.role }
    localStorage.setItem('churn_token', data.access_token)
    localStorage.setItem('churn_user', JSON.stringify(state.user))
  }

  function logout() {
    state.token = ''
    state.user = null
    localStorage.removeItem('churn_token')
    localStorage.removeItem('churn_user')
  }

  return { state, isAuthenticated, isAdmin, login, logout }
}
