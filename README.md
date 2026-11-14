---
title: Telecom Churn Prediction System
sdk: docker
app_port: 7860
---

# 电信客户流失预测与可视化分析系统

基于 XGBoost 与 SHAP 的电信客户流失预测与可视化分析系统，包含风险总览、重点客户、特征分析、流失预测、数据与模型管理、系统信息六个模块。

## 技术栈

- 后端：FastAPI、SQLAlchemy、SQLite、XGBoost、SHAP
- 前端：Vue 3、Element Plus、ECharts、Vite
- 测试：pytest、Vitest

## 功能

- 风险总览：按预测批次汇总风险规模、概率分布、区域差异和高风险客户清单
- 重点客户：按风险等级、区域、费用筛选，查看单客户 SHAP 归因
- 特征分析：全局 SHAP 重要性、蜂群图、单特征依赖分析
- 流失预测：单客户实时预测、批量文件预测（后台任务与进度）、结果导出
- 数据与模型：数据版本管理、模型训练与版本切换、模型评估、解释性评估、参数敏感性与特征筛选实验、评估摘要导出
- 系统信息：运行时环境、依赖版本、当前模型与数据版本、接口清单

## 目录结构

```
backend/        FastAPI 后端与机器学习模块
frontend/       Vue 3 前端
scripts/        启动与初始化脚本
requirements.txt
start.bat       Windows 一键启动
```

## 本地运行

1. 安装 Python 3.12 依赖：

```bash
pip install -r requirements.txt
```

2. 安装并构建前端：

```bash
cd frontend
npm install
npm run build
```

3. 数据已随仓库提供（`数据集/train.csv`、`数据集/test.csv`），可直接启动；也可以在“数据与模型”页面上传自己的训练数据。

4. 启动：

```bash
python scripts/run.py
```

或直接双击 `start.bat`。启动后访问 http://127.0.0.1:8000 。

首次启动会自动训练模型，并基于 `test.csv` 生成批量预测缓存，需要几分钟；之后启动会跳过。

默认演示账号：`admin` / `admin123`。

## 测试

```bash
python -m pytest backend/tests -q
cd frontend && npm test
```

## 未纳入版本控制的内容

- `artifacts/`：模型训练产物，首次启动会自动训练生成
- `data/`：运行时 SQLite 数据库与上传文件
- `backups/`：项目备份
- `数据集/2.csv`：额外样例文件，体积较大未纳入仓库

## 说明

模型指标来自内部验证集，SHAP 反映模型预测依据而非业务因果关系。默认账号与本地开发密钥仅用于演示，部署到生产环境前需修改。
