from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.artifacts import ArtifactStore, ModelNotReadyError
from backend.config import Settings
from backend.database import PredictionBatch, create_session_factory
from backend.ml.training import train_models
from backend.services import DataService, PredictionService


def _has_cached_predictions(session) -> bool:
    return session.query(PredictionBatch).count() > 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="初始化流失预测模型与演示预测结果")
    parser.add_argument("--quick", action="store_true", help="使用少量迭代，适用于开发测试")
    parser.add_argument("--retrain", action="store_true", help="强制重新训练")
    parser.add_argument("--repredict", action="store_true", help="重新生成 test.csv 批量预测缓存")
    parser.add_argument("--skip", action="store_true", help="跳过训练和预测缓存生成，仅检查依赖")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    store = ArtifactStore(settings.artifact_dir)
    engine, sessions = create_session_factory(settings.database_path)
    data_service = DataService(settings.train_path, settings.test_path, settings.upload_dir)

    if args.skip:
        print("    --skip 模式：跳过模型训练与预测缓存。", flush=True)
        return 0

    try:
        # --- 模型 ---
        try:
            store.load_active()
            model_ready = True
        except ModelNotReadyError:
            model_ready = False

        model_version = store.active_version()
        if model_ready and not args.retrain:
            print(f"    模型已就绪：{model_version}，跳过训练。", flush=True)
        else:
            if args.retrain and model_version:
                print(f"    --retrain 强制重新训练（当前版本 {model_version}）……", flush=True)
            else:
                print("    未找到可用模型，开始训练……", flush=True)
            result = train_models(data_service.train(), settings.artifact_dir, quick=args.quick)
            store.activate(result["version"])
            print(f"    模型 {result['version']} 已上线，内部验证集 AUC={result['metrics']['xgboost']['auc']:.4f}", flush=True)

        # --- 预测缓存 ---
        if os.getenv("CHURN_SKIP_CACHE") == "1":
            print("    CHURN_SKIP_CACHE 已开启，跳过预测缓存生成。", flush=True)
            return 0
        test_has_data = data_service.test_exists() and len(data_service.test()) > 0
        if not test_has_data:
            print("    test.csv 不存在或为空，跳过预测缓存生成。", flush=True)
            return 0

        with sessions() as session:
            has_cache = _has_cached_predictions(session)
            if args.retrain or args.repredict or not has_cache:
                reason = []
                if args.retrain:
                    reason.append("--retrain")
                if args.repredict:
                    reason.append("--repredict")
                if not has_cache:
                    reason.append("无缓存")
                print(f"    生成 test.csv 批量预测及 SHAP 风险原因（触发条件：{' + '.join(reason)}）……", flush=True)
                result = PredictionService(session, store).batch(data_service.test(), "test.csv")
                print(f"    已缓存 {result['total']} 条预测：高风险 {result['high']} 条", flush=True)
            else:
                print("    预测缓存已就绪，跳过。", flush=True)

        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
