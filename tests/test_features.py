import pytest
import numpy as np
import pandas as pd
from src.data.features import calculate_returns_and_realized_vol, calculate_liquidity_and_gas_features


def test_log_return_formula():
    """Kiểm tra công thức r_t = ln(P_t / P_{t-1})."""
    df = pd.DataFrame({
        "close_clean": [100.0, 110.0, 110.0 * np.exp(0.05)],
    })
    df = calculate_returns_and_realized_vol(df, windows=[2])

    expected_ret_1 = np.log(110.0 / 100.0)
    expected_ret_2 = 0.05

    assert np.isclose(df.loc[1, "log_return"], expected_ret_1, atol=1e-6)
    assert np.isclose(df.loc[2, "log_return"], expected_ret_2, atol=1e-6)


def test_rebalance_gas_cost_calculation():
    """Kiểm tra công thức tính chi phí Rebalance Gas quy USD."""
    df = pd.DataFrame({
        "close_clean": [3000.0],       # ETH = 3,000 USD
        "avg_gas_price_gwei": [50.0],  # Gas = 50 Gwei
        "volumeUSD": [1000.0],
        "tvlUSD": [10000.0],
        "feesUSD": [3.0],
    })
    gas_units = 300000  # 300,000 gas units

    df_out = calculate_liquidity_and_gas_features(df, estimated_gas_units=gas_units)

    # Chi phí USD = 300,000 * (50 * 1e-9) * 3,000 = 45.0 USD
    expected_cost_usd = gas_units * (50.0 * 1e-9) * 3000.0
    assert np.isclose(df_out.loc[0, "cost_rebalance_usd"], expected_cost_usd, atol=1e-5)
    assert df_out.loc[0, "cost_rebalance_usd"] == 45.0


def test_gas_asof_join_accepts_different_datetime_resolutions():
    datetime = pd.Timestamp("2024-01-01T00:00:00Z")
    df = pd.DataFrame({
        "datetime": pd.Series([datetime]).astype("datetime64[us, UTC]"),
        "close_clean": [3000.0],
        "volumeUSD": [1000.0],
        "tvlUSD": [10000.0],
        "feesUSD": [3.0],
    })
    df_gas = pd.DataFrame({
        "datetime": pd.Series([datetime]).astype("datetime64[s, UTC]"),
        "avg_gas_price_gwei": [40.0],
    })

    df_out = calculate_liquidity_and_gas_features(df, df_gas=df_gas)

    assert df_out.loc[0, "avg_gas_price_gwei"] == 40.0
    assert df_out.loc[0, "cost_rebalance_usd"] == 36.0
