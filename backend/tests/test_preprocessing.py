import numpy as np

from backend.ml.preprocessing import ID_COLUMN, LABEL_COLUMN, build_quality_report, clean_dataframe, prepare_features


def test_clean_dataframe_removes_empty_columns_and_duplicate_ids(sample_frame):
    frame = sample_frame.copy()
    frame["Unnamed: 99"] = np.nan
    duplicate = frame.iloc[[0]].copy()
    duplicate[LABEL_COLUMN] = 1 - duplicate[LABEL_COLUMN]
    cleaned, report = clean_dataframe(__import__("pandas").concat([frame, duplicate], ignore_index=True))

    assert "Unnamed: 99" not in cleaned.columns
    assert len(cleaned) == len(frame)
    assert report["duplicates_removed"] == 1
    assert report["rows_after"] == len(frame)


def test_prepare_features_excludes_identifier_and_adds_business_features(sample_frame):
    matrix = prepare_features(sample_frame)

    assert ID_COLUMN not in matrix.columns
    assert LABEL_COLUMN not in matrix.columns
    assert "usage_change_rate" in matrix.columns
    assert "monthly_fee_change_rate" in matrix.columns
    assert "service_call_count" in matrix.columns
    assert "dropped_call_count" in matrix.columns
    assert "avg_call_minutes_3m" in matrix.columns
    assert np.isfinite(matrix.to_numpy(dtype=float)).all()


def test_quality_report_profiles_missing_unique_numeric_and_anomalies(sample_frame):
    train = sample_frame.head(20).copy()
    train.loc[0, "平均月费用"] = np.nan
    train.loc[1, "平均月费用"] = -1
    train.loc[2, "平均月费用"] = np.inf
    test = train.drop(columns=[LABEL_COLUMN])

    report = build_quality_report(train, test)
    field = next(item for item in report["train"]["fields"] if item["name"] == "平均月费用")

    assert field["missing"] == 2
    assert field["unique"] > 0
    assert field["minus_one"] == 1
    assert field["infinite"] == 1
    assert set(field["numeric"]) == {"mean", "std", "min", "max"}
    assert report["train"]["row_count"] == 20


def test_quality_report_detects_schema_differences_and_numeric_drift(sample_frame):
    train = sample_frame.copy()
    test = sample_frame.drop(columns=[LABEL_COLUMN, "平均掉线语音呼叫数"]).copy()
    test["平均月费用"] = test["平均月费用"] + 1000
    test["额外字段"] = 1

    report = build_quality_report(train, test)

    assert "平均掉线语音呼叫数" in report["schema"]["missing_in_test"]
    assert "额外字段" in report["schema"]["extra_in_test"]
    drift = next(item for item in report["drift"] if item["name"] == "平均月费用")
    assert drift["psi"] > 0.25
    assert drift["status"] == "显著漂移"
