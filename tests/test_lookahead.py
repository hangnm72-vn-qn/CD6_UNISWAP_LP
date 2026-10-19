import pytest
import numpy as np
import pandas as pd
from src.data.features import calculate_returns_and_realized_vol, calculate_liquidity_and_gas_features


@pytest.fixture
def mock_price_series():
    """Tạo chuỗi giá giả lập 500 nến giờ có xu hướng và biến động."""
    np.random.seed(42)
    n = 500
    dates = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    returns = np.random.normal(0, 0.01, size=n)
    prices = 2000.0 * np.exp(np.cumsum(returns))

    df = pd.DataFrame({
        "datetime": dates,
        "pool_name": "MOCK-POOL",
        "close_clean": prices,
        "open_clean": prices * 0.999,
        "high_clean": prices * 1.005,
        "low_clean": prices * 0.995,
        "volumeUSD": np.random.uniform(1e5, 1e6, size=n),
        "feesUSD": np.random.uniform(50, 500, size=n),
        "tvlUSD": np.random.uniform(1e7, 2e7, size=n),
    })
    return df


def test_timeline_strictly_monotonic(mock_price_series):
    """Kiểm tra timestamp phải tăng dần nghiêm ngặt, không trùng lặp và không nhảy lùi."""
    dates = mock_price_series["datetime"]
    assert dates.is_monotonic_increasing, "Dữ liệu thời gian không tăng dần nghiêm ngặt!"
    assert not dates.duplicated().any(), "Phát hiện timestamp bị trùng lặp!"


def test_rolling_volatility_no_lookahead(mock_price_series):
    """
    Kiểm định Truncate and Recompute:
    Feature tại thời điểm t không được phép thay đổi khi dữ liệu sau t bị xóa bỏ hoàn toàn.
    """
    df_full = calculate_returns_and_realized_vol(mock_price_series, windows=[24, 168])
    cutoff_idx = 300  # Điểm cắt t

    # Cắt bỏ toàn bộ dữ liệu tương lai sau cutoff_idx
    df_truncated = mock_price_series.iloc[:cutoff_idx + 1].copy()
    df_recomputed = calculate_returns_and_realized_vol(df_truncated, windows=[24, 168])

    # So sánh giá trị tại đúng thời điểm t
    val_full = df_full.loc[cutoff_idx, "vol_hist_24h"]
    val_recomputed = df_recomputed.loc[cutoff_idx, "vol_hist_24h"]

    assert np.isclose(val_full, val_recomputed, rtol=1e-7, atol=1e-7), (
        f"Rò rỉ dữ liệu (Look-ahead bias) phát hiện ở vol_hist_24h! "
        f"Full: {val_full}, Truncated: {val_recomputed}"
    )


def test_turnover_no_future_leakage(mock_price_series):
    """Kiểm tra các biến đổi tỷ số và log-change không dùng dữ liệu tương lai."""
    df_full = calculate_liquidity_and_gas_features(mock_price_series)
    cutoff_idx = 250

    df_truncated = mock_price_series.iloc[:cutoff_idx + 1].copy()
    df_recomputed = calculate_liquidity_and_gas_features(df_truncated)

    assert np.isclose(
        df_full.loc[cutoff_idx, "volume_turnover"],
        df_recomputed.loc[cutoff_idx, "volume_turnover"],
        rtol=1e-7
    )
    assert np.isclose(
        df_full.loc[cutoff_idx, "volume_log_change"],
        df_recomputed.loc[cutoff_idx, "volume_log_change"],
        rtol=1e-7
    )
