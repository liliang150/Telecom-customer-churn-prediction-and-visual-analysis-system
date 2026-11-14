import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def sample_frame():
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    size = 240
    signal = rng.normal(size=size)
    return pd.DataFrame(
        {
            "客户ID": np.arange(size),
            "地理区域": rng.integers(0, 20, size),
            "平均月费用": np.clip(60 + signal * 25, 5, None),
            "每月平均使用分钟数": np.clip(300 - signal * 90, 0, None),
            "平均客户服务电话次数": np.clip(np.round(1 + signal), 0, None),
            "平均掉线语音呼叫数": np.clip(np.round(signal), 0, None),
            "过去三个月的平均每月使用分钟数": np.clip(280 - signal * 80, 0, None),
            "当月使用分钟数与前三个月平均值的百分比变化": -signal * 20,
            "当月费用与前三个月平均值的百分比变化": signal * 10,
            "是否流失": (signal + rng.normal(scale=0.6, size=size) > 0).astype(int),
        }
    )
