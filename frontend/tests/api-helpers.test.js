import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getErrorMessage, isUnauthorized, unwrapEnvelope } from '../src/api/helpers'
import http from '../src/api/http'
import { analysisApi, dataApi, modelApi, predictApi, systemApi } from '../src/api'

vi.mock('../src/api/http', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))

beforeEach(() => vi.clearAllMocks())

describe('API helpers', () => {
  it('returns data from a successful envelope', () => {
    expect(unwrapEnvelope({ code: 200, message: 'success', data: { total: 8 } })).toEqual({ total: 8 })
  })

  it('throws the server message for an unsuccessful envelope', () => {
    expect(() => unwrapEnvelope({ code: 422, message: '记录无效', data: null })).toThrow('记录无效')
  })

  it('recognizes only HTTP 401 responses as unauthorized', () => {
    expect(isUnauthorized({ response: { status: 401 } })).toBe(true)
    expect(isUnauthorized({ response: { status: 403 } })).toBe(false)
    expect(isUnauthorized(new Error('network'))).toBe(false)
  })

  it('prefers FastAPI detail and falls back to a useful message', () => {
    expect(getErrorMessage({ response: { data: { detail: '登录已过期' } } })).toBe('登录已过期')
    expect(getErrorMessage(new Error('网络异常'))).toBe('网络异常')
    expect(getErrorMessage({})).toBe('操作失败，请稍后重试')
  })
})

describe('data and model workflow APIs', () => {
  it('exposes staged upload confirmation and version restoration', () => {
    const file = new File(['id'], 'train.csv', { type: 'text/csv' })
    dataApi.upload('train', file)
    dataApi.confirm('saved.csv', 'train')
    dataApi.versions()
    dataApi.activate('d20261103')

    expect(http.post.mock.calls[0][0]).toBe('/api/data/upload?kind=train')
    expect(http.post.mock.calls[0][1]).toBeInstanceOf(FormData)
    expect(http.post).toHaveBeenCalledWith('/api/data/confirm', { saved_name: 'saved.csv', kind: 'train' })
    expect(http.get).toHaveBeenCalledWith('/api/data/versions')
    expect(http.post).toHaveBeenCalledWith('/api/data/versions/activate', { version: 'd20261103' })
  })

  it('exposes full training and background status polling', () => {
    modelApi.train()
    modelApi.trainingStatus('job-1')

    expect(http.post).toHaveBeenCalledWith('/api/model/train', { quick: false })
    expect(http.get).toHaveBeenCalledWith('/api/model/train/job-1')
  })

  it('deletes a model version through the encoded version endpoint', () => {
    modelApi.remove('v20261103999999999999')

    expect(http.delete).toHaveBeenCalledWith('/api/model/versions/v20261103999999999999')
  })

  it('fetches the model explainability evaluation', () => {
    modelApi.explainability()

    expect(http.get).toHaveBeenCalledWith('/api/model/explainability')
  })

  it('runs and polls depth sensitivity analysis', () => {
    modelApi.sensitivity()
    modelApi.runSensitivity()
    modelApi.sensitivityStatus('job-2')

    expect(http.get).toHaveBeenCalledWith('/api/model/sensitivity')
    expect(http.post).toHaveBeenCalledWith('/api/model/sensitivity', { quick: false })
    expect(http.get).toHaveBeenCalledWith('/api/model/sensitivity/job-2')
  })

  it('exports the evaluation report as a blob', () => {
    modelApi.exportEvaluationReport()

    expect(http.get).toHaveBeenCalledWith('/api/model/evaluation-report', { responseType: 'blob' })
  })

  it('loads eda data and feature dependency points', () => {
    dataApi.eda()
    analysisApi.dependency()
    analysisApi.dependency('每月平均使用分钟数')

    expect(http.get).toHaveBeenCalledWith('/api/data/eda')
    expect(http.get).toHaveBeenCalledWith('/api/analysis/dependency', { params: {} })
    expect(http.get).toHaveBeenCalledWith('/api/analysis/dependency', { params: { feature: '每月平均使用分钟数' } })
  })

  it('loads system information', () => {
    systemApi.info()

    expect(http.get).toHaveBeenCalledWith('/api/system/info')
  })

  it('runs and polls lasso feature selection experiment', () => {
    modelApi.featureSelection()
    modelApi.runFeatureSelection()
    modelApi.featureSelectionStatus('job-3')

    expect(http.get).toHaveBeenCalledWith('/api/model/feature-selection')
    expect(http.post).toHaveBeenCalledWith('/api/model/feature-selection', { quick: false })
    expect(http.get).toHaveBeenCalledWith('/api/model/feature-selection/job-3')
  })

  it('passes the selected batch to the dashboard endpoint', () => {
    analysisApi.dashboard()
    analysisApi.dashboard('batch-1')

    expect(http.get).toHaveBeenCalledWith('/api/analysis/dashboard', { params: {} })
    expect(http.get).toHaveBeenCalledWith('/api/analysis/dashboard', { params: { batch_id: 'batch-1' } })
  })

  it('submits batch prediction as a background job and polls its status', () => {
    const file = new File(['id'], 'customers.csv', { type: 'text/csv' })
    predictApi.batch(file)
    predictApi.batchStatus('job-1')

    expect(http.post.mock.calls[0][0]).toBe('/api/predict/batch')
    expect(http.post.mock.calls[0][1]).toBeInstanceOf(FormData)
    expect(http.post.mock.calls[0][2]).toEqual({ timeout: 300000 })
    expect(http.get).toHaveBeenCalledWith('/api/predict/batch/job-1')
  })
})
