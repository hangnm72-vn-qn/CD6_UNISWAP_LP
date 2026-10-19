import pytest
import numpy as np
import pandas as pd
from src.data.clean import reindex_and_fill_timeline


def test_reindex_continuity():
    """Kiểm tra reindex tạo đúng và đủ số lượng bar giờ liên tục giữa 2 mốc thời gian."""
    start_dt = pd.Timestamp("2024-01-01 00:00:00+00:00")
    end_dt = pd.Timestamp("2024-01-03 23:00:00+00:00")
    expected_hours = 3 * 24  # 72 giờ

    # Giả lập nến bị khuyết ở giữa
    sparse_dates = [start_dt, start_dt + pd.Timedelta(hours=10), end_dt]
    df_sparse = pd.DataFrame({
        "datetime": sparse_dates,
        "price": [2000.0, 2050.0, 2100.0],
        "volumeUSD": [100.0, 200.0, 300.0],
    })

    df_filled = reindex_and_fill_timeline(df_sparse, start_dt, end_dt, freq="1h")

    assert len(df_filled) == expected_hours, f"Số lượng giờ thực tế {len(df_filled)} != kỳ vọng {expected_hours}"
    assert df_filled["datetime"].iloc[0] == start_dt
    assert df_filled["datetime"].iloc[-1] == end_dt


def test_non_negative_values():
    """Kiểm tra không có giá trị bất hợp lý: Giá <= 0, TVL < 0, Volume < 0."""
    sample_data = pd.DataFrame({
        "price": [1000.0, 1500.0, 2000.0],
        "tvlUSD": [5e6, 6e6, 7e6],
        "volumeUSD": [0.0, 1e5, 2e5],
    })

    assert (sample_data["price"] > 0).all(), "Phát hiện giá <= 0!"
    assert (sample_data["tvlUSD"] >= 0).all(), "Phát hiện TVL âm!"
    assert (sample_data["volumeUSD"] >= 0).all(), "Phát hiện Volume âm!"


def test_flow_variables_zero_fill():
    """Đảm bảo các bar không có swap thì Volume và Fees được điền 0, không được điền forward-fill."""
    start_dt = pd.Timestamp("2024-01-01 00:00:00+00:00")
    end_dt = pd.Timestamp("2024-01-01 03:00:00+00:00")
    df = pd.DataFrame({
        "datetime": [start_dt],
        "price": [2000.0],
        "volumeUSD": [50000.0],
        "feesUSD": [25.0]
    })
    df_filled = reindex_and_fill_timeline(df, start_dt, end_dt)

    # Bar lúc 01:00 phải có volume = 0 và fees = 0
    bar_gap = df_filled[df_filled["datetime"] == start_dt + pd.Timedelta(hours=1)].iloc[0]
    assert bar_gap["volumeUSD"] == 0.0
    assert bar_gap["feesUSD"] == 0.0
    assert bar_gap["is_filled"] == True
    assert bar_gap["price"] == 2000.0  # Giá được giữ nguyên trạng thái
