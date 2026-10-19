import warnings

import numpy as np
import pandas as pd
import pytest

from src.data.clean import reindex_and_fill_timeline, standardize_pool_price
from src.data.build_dataset import merge_defillama_tvl, save_sample_preview
from src.data.features import (
    calculate_garch_volatility,
    calculate_liquidity_and_gas_features,
    calculate_returns_and_realized_vol,
)
from src.data.validate_processed import REQUIRED_COLUMNS, audit_parquet_file


@pytest.mark.parametrize(
    ("quote", "token0", "token1", "token0_price", "token1_price", "expected"),
    [
        ("USD_per_WETH", "USDC", "WETH", 2500.0, 1 / 2500.0, 2500.0),
        ("USD_per_WETH", "WETH", "USDT", 1 / 2500.0, 2500.0, 2500.0),
        ("WETH_per_WBTC", "WBTC", "WETH", 1 / 16.0, 16.0, 16.0),
        ("USDT_per_USDC", "USDC", "USDT", 1.0002, 1 / 1.0002, 1.0002),
    ],
)
def test_standardize_pool_price_uses_quote_direction(
    quote, token0, token1, token0_price, token1_price, expected
):
    raw_close = token0_price
    df = pd.DataFrame(
        {
            "token0Price": [token0_price],
            "token1Price": [token1_price],
            "open": [raw_close],
            "high": [raw_close],
            "low": [raw_close],
            "close": [raw_close],
        }
    )
    config = {
        "name": "TEST",
        "price_quote": quote,
        "token0": {"symbol": token0},
        "token1": {"symbol": token1},
    }

    result = standardize_pool_price(df, config)

    assert np.isclose(result.loc[0, "close_clean"], expected)
    assert np.isclose(result.loc[0, "price"], expected)


def test_zero_prices_are_removed_before_fill_and_pregenesis_is_marked():
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    valid = start + pd.Timedelta(hours=2)
    df = pd.DataFrame(
        {
            "datetime": [start, valid],
            "price": [0.0, 2000.0],
            "close_clean": [0.0, 2000.0],
        }
    )

    df["price"] = df["price"].where(df["price"] > 0)
    df["close_clean"] = df["close_clean"].where(df["close_clean"] > 0)
    filled = reindex_and_fill_timeline(df, start, start + pd.Timedelta(hours=3))

    assert (filled["close_clean"] > 0).all()
    assert filled.loc[:1, "is_filled"].all()
    assert filled["close_clean"].tolist() == [2000.0] * 4


def test_inverse_quote_inverts_ohlc_and_turns_zeroes_into_missing_values():
    df = pd.DataFrame(
        {
            "token0Price": [0.0004],
            "token1Price": [2500.0],
            "open": [0.00039],
            "high": [0.00041],
            "low": [0.00038],
            "close": [0.0004],
        }
    )
    config = {
        "name": "WETH-USDT-TEST",
        "price_quote": "USD_per_WETH",
        "token0": {"symbol": "WETH"},
        "token1": {"symbol": "USDT"},
    }

    result = standardize_pool_price(df, config)

    assert np.isclose(result.loc[0, "high_clean"], 1 / 0.00038)
    assert np.isclose(result.loc[0, "low_clean"], 1 / 0.00041)
    assert np.isclose(result.loc[0, "close_clean"], 2500.0)

    zero_row = pd.DataFrame(
        {
            "token0Price": [0.0],
            "token1Price": [0.0],
            "open": [0.0],
            "high": [0.0],
            "low": [0.0],
            "close": [0.0],
        }
    )
    invalid = standardize_pool_price(zero_row, config)
    assert invalid[["price", "open_clean", "high_clean", "low_clean", "close_clean"]].isna().all().all()


def test_returns_and_garch_are_finite_with_invalid_price_bars():
    df = pd.DataFrame(
        {
            "close_clean": [100.0, 0.0, 110.0, 120.0],
            "vol_hist_24h": [0.0, 0.1, 0.2, 0.3],
        }
    )
    returns = calculate_returns_and_realized_vol(df, windows=[2])
    returns.loc[1, "log_return"] = np.inf
    result = calculate_garch_volatility(returns, min_obs=10)

    assert np.isfinite(result["log_return"]).all()
    assert np.isfinite(result["vol_garch_forecast"]).all()


def test_non_usd_pool_gas_uses_eth_reference_price():
    datetime = pd.date_range("2024-01-01", periods=2, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "datetime": datetime,
            "pool_name": "WBTC-WETH-005",
            "close_clean": [0.06, 0.06],
            "avg_gas_price_gwei": [50.0, 50.0],
            "volumeUSD": [0.0, 0.0],
            "tvlUSD": [1.0, 1.0],
            "feesUSD": [0.0, 0.0],
        }
    )
    eth_prices = pd.DataFrame(
        {"datetime": datetime, "close": [3000.0, 2500.0]}
    )

    result = calculate_liquidity_and_gas_features(df, df_eth_prices=eth_prices)

    assert result["cost_rebalance_usd"].tolist() == [45.0, 37.5]


def test_defillama_asof_join_accepts_different_timestamp_resolutions():
    timestamp = pd.Timestamp("2024-01-02T00:00:00Z")
    features = pd.DataFrame(
        {
            "datetime": pd.Series([timestamp]).astype("datetime64[ns, UTC]"),
            "close_clean": [2000.0],
        }
    )
    defillama = pd.DataFrame(
        {
            "datetime_available": pd.Series([timestamp]).astype("datetime64[us, UTC]"),
            "defillama_protocol_tvl_usd": [5_000_000.0],
        }
    )

    result = merge_defillama_tvl(features, defillama)

    assert result.loc[0, "defillama_protocol_tvl_usd"] == 5_000_000.0
    assert "datetime_available" not in result.columns


def test_preview_writes_fallback_when_standard_file_is_locked(tmp_path, monkeypatch):
    standard_path = tmp_path / "uniswap_v3_sample_preview.csv"
    original_to_csv = pd.DataFrame.to_csv
    attempted_paths = []

    def to_csv_with_locked_first_path(frame, path, *args, **kwargs):
        attempted_paths.append(path)
        if path == standard_path:
            raise PermissionError("file is locked")
        return original_to_csv(frame, path, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_csv", to_csv_with_locked_first_path)

    saved_path = save_sample_preview(pd.DataFrame({"value": [1]}), standard_path)

    assert saved_path != standard_path
    assert saved_path.exists()
    assert attempted_paths == [standard_path, saved_path]


def test_garch_rescales_small_returns_without_data_scale_warning():
    rng = np.random.default_rng(7)
    df = pd.DataFrame(
        {
            "log_return": rng.normal(0.0, 0.0006, size=250),
            "vol_hist_24h": np.full(250, 0.05),
        }
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = calculate_garch_volatility(
            df, refit_frequency=1000, min_obs=240
        )

    assert np.isfinite(result["vol_garch_forecast"]).all()
    assert not any("DataScaleWarning" in str(warning.category) for warning in caught)


def _valid_audit_frame():
    rows = []
    dates = pd.date_range("2024-01-01", periods=2, freq="h", tz="UTC")
    for pool_name in ["POOL-A", "POOL-B"]:
        for timestamp in dates:
            rows.append(
                {
                    "datetime": timestamp,
                    "pool_name": pool_name,
                    "price": 1.0,
                    "open_clean": 1.0,
                    "high_clean": 1.0,
                    "low_clean": 1.0,
                    "close_clean": 1.0,
                    "volumeUSD": 0.0,
                    "feesUSD": 0.0,
                    "tvlUSD": 1.0,
                    "log_return": 0.0,
                    "vol_hist_24h": 0.0,
                    "vol_garch_forecast": 0.0,
                    "volume_turnover": 0.0,
                    "fee_yield": 0.0,
                    "cost_rebalance_usd": 1.0,
                }
            )
    return pd.DataFrame(rows)


def test_audit_checks_panel_timestamps_within_pool(tmp_path):
    file_path = tmp_path / "panel.parquet"
    _valid_audit_frame().to_parquet(file_path, index=False)

    assert audit_parquet_file(file_path)


def test_audit_returns_false_for_nonpositive_price(tmp_path):
    file_path = tmp_path / "invalid.parquet"
    df = _valid_audit_frame()
    df.loc[0, "close_clean"] = 0.0
    df.to_parquet(file_path, index=False)

    assert not audit_parquet_file(file_path)


def test_audit_required_columns_match_test_frame():
    assert set(REQUIRED_COLUMNS).issubset(_valid_audit_frame().columns)
