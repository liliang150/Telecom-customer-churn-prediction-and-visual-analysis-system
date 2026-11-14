import http from './http'

export const authApi = {
  login: (payload) => http.post('/api/auth/login', payload),
  health: () => http.get('/api/health'),
}

export const analysisApi = {
  dashboard: (batchId) => http.get('/api/analysis/dashboard', { params: batchId ? { batch_id: batchId } : {} }),
  risk: (params) => http.get('/api/analysis/risk', { params }),
  features: () => http.get('/api/analysis/features'),
  shap: (customerId) => http.get('/api/analysis/shap', { params: { customer_id: customerId } }),
  dependency: (feature) => http.get('/api/analysis/dependency', { params: feature ? { feature } : {} }),
}

export const predictApi = {
  sample: () => http.get('/api/data/sample'),
  single: (record) => http.post('/api/predict/churn', { record }),
  batch: (file) => {
    const data = new FormData()
    data.append('file', file)
    return http.post('/api/predict/batch', data, { timeout: 300000 })
  },
  batchStatus: (jobId) => http.get(`/api/predict/batch/${encodeURIComponent(jobId)}`),
  batches: () => http.get('/api/predict/batches'),
  exportBatch: (batchId) => http.get(`/api/predict/batches/${encodeURIComponent(batchId)}/export`, { responseType: 'blob' }),
  deleteBatch: (batchId) => http.delete(`/api/predict/batches/${encodeURIComponent(batchId)}`),
}

export const dataApi = {
  overview: () => http.get('/api/data/overview'),
  eda: () => http.get('/api/data/eda'),
  upload: (kind, file) => {
    const data = new FormData()
    data.append('file', file)
    return http.post(`/api/data/upload?kind=${kind}`, data)
  },
  confirm: (savedName, kind) => http.post('/api/data/confirm', { saved_name: savedName, kind }),
  versions: () => http.get('/api/data/versions'),
  activate: (version) => http.post('/api/data/versions/activate', { version }),
}

export const systemApi = {
  info: () => http.get('/api/system/info'),
}

export const modelApi = {
  evaluate: () => http.get('/api/model/evaluate'),
  explainability: () => http.get('/api/model/explainability'),
  sensitivity: () => http.get('/api/model/sensitivity'),
  runSensitivity: () => http.post('/api/model/sensitivity', { quick: false }),
  sensitivityStatus: (jobId) => http.get(`/api/model/sensitivity/${encodeURIComponent(jobId)}`),
  featureSelection: () => http.get('/api/model/feature-selection'),
  runFeatureSelection: () => http.post('/api/model/feature-selection', { quick: false }),
  featureSelectionStatus: (jobId) => http.get(`/api/model/feature-selection/${encodeURIComponent(jobId)}`),
  exportEvaluationReport: () => http.get('/api/model/evaluation-report', { responseType: 'blob' }),
  train: () => http.post('/api/model/train', { quick: false }),
  trainingStatus: (jobId) => http.get(`/api/model/train/${encodeURIComponent(jobId)}`),
  versions: () => http.get('/api/model/versions'),
  activate: (version) => http.post('/api/model/activate', { version }),
  remove: (version) => http.delete(`/api/model/versions/${encodeURIComponent(version)}`),
}
