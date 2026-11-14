import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const dataModelSource = readFileSync(new URL('../src/views/DataModelView.vue', import.meta.url), 'utf8')
const predictionSource = readFileSync(new URL('../src/views/PredictionView.vue', import.meta.url), 'utf8')

describe('数据更新与批量预测入口', () => {
  it('数据资产仅提供训练数据更新，不再提供预测数据上传', () => {
    const updatePanel = dataModelSource.match(/class="panel data-update-panel"[\s\S]*?<\/section>/)?.[0]

    expect(updatePanel).toBeTruthy()
    expect(updatePanel).toContain('训练数据')
    expect(updatePanel).not.toContain('value="predict"')
    expect(updatePanel).not.toContain('>预测数据<')
    expect(dataModelSource).toContain("dataApi.upload('train', uploadFile.value)")
  })

  it('流失预测页保留独立批量上传预测入口', () => {
    expect(predictionSource).toContain('开始批量预测')
    expect(predictionSource).toContain('predictApi.batch(selectedFile.value)')
  })
})

describe('模型版本删除', () => {
  it('仅允许管理员删除非上线版本并保留历史预测结果', () => {
    expect(dataModelSource).toContain('将永久删除模型 ${row.version}，已有预测结果不受影响。是否继续？')
    expect(dataModelSource).toContain('await modelApi.remove(row.version)')
    expect(dataModelSource).toContain('v-if="!row.active && isAdmin"')
    expect(dataModelSource).toContain("if (candidate.value?.version === row.version) candidate.value = null")
    expect(dataModelSource).toContain('await loadModel()')
  })
})

describe('候选模型训练提示', () => {
  it('简洁说明当前训练数据和上线影响', () => {
    expect(dataModelSource).toContain('将使用当前训练数据“${trainingDataName.value}”训练候选模型，当前上线模型不受影响。是否继续？')
    expect(dataModelSource).not.toContain('无需重复上传数据。若需使用新训练数据')
  })

  it('使用当前训练数据版本的原始文件名动态生成提示', () => {
    expect(dataModelSource).toContain('displaySourceName(currentVersion?.source_file)')
    expect(dataModelSource).toContain('${trainingDataName.value}')
  })

  it('训练提示框使用固定窄宽度', () => {
    expect(dataModelSource).toContain("customStyle: { width: '420px' }")
  })
})
