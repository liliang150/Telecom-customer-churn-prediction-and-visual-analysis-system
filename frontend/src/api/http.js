import axios from 'axios'
import { unwrapEnvelope } from './helpers'

const http = axios.create({
  baseURL: '/',
  timeout: 120000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('churn_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (response) => {
    if (response.config.responseType === 'blob') return response
    return unwrapEnvelope(response.data)
  },
  (error) => {
    if (error?.response?.status === 401) {
      localStorage.removeItem('churn_token')
      localStorage.removeItem('churn_user')
      window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    }
    return Promise.reject(error)
  },
)

export default http
