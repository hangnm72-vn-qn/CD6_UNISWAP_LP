import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from arch import arch_model

# Đảm bảo import đúng utils từ src
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

from src.data.utils import load_config, logger


def calculate_returns_and_realized_vol(
    df: pd.DataFrame,
    windows: List[int] = [24, 168, 720],
    annualization_factor: int = 8760
) -> pd.DataFrame:
    """
    Tính log return và Historical Rolling Volatility theo nhiều khung thời gian.
    Chỉ dùng dữ liệu quá khứ (không dùng center=True để tránh look-ahead bias).
    """
    df = df.copy()
    # Log return của giá chuẩn
    valid_close = pd.to_numeric(df["close_clean"], errors="coerce")
    valid_close = valid_close.where(valid_close > 0)
    df["log_return"] = np.log(valid_close / valid_close.shift(1))
    df["log_return"] = df["log_return"].replace([np.inf, -np.inf], 0.0).fillna(0.0)

    # Rolling standard deviation (annualized)
    for w in windows:
        col_name = f"vol_hist_{w}h"
        # Đòi hỏi tối thiểu min_periods = w // 2 để tránh NaN quá nhiều ở đầu chuỗi
        df[col_name] = (
            df["log_return"].rolling(window=w, min_periods=max(2, w // 2)).std()
            * np.sqrt(annualization_factor)
        )

    # Parkinson Range-based Volatility (nếu có High và Low)
    if "high_clean" in df.columns and "low_clean" in df.columns:
        high_low_ratio = np.log(df["high_clean"] / df["low_clean"].replace(0, np.nan))
        high_low_ratio = high_low_ratio.fillna(0.0)
        parkinson_instant_var = (high_low_ratio ** 2) / (4.0 * np.log(2.0))

        # Smooth Parkinson volatility bằng rolling 24h
        df["vol_parkinson_24h"] = np.sqrt(
            parkinson_instant_var.rolling(window=24, min_periods=12).mean() * annualization_factor
        )

    return df


def calculate_garch_volatility(
    df: pd.DataFrame,
    refit_frequency: int = 24,
    min_obs: int = 240,
    annualization_factor: int = 8760
) -> pd.DataFrame:
    """
    Dự báo độ biến động bằng mô hình GARCH(1,1) One-Step-Ahead (Expanding/Rolling).
    Áp dụng Daily Refit - Hourly Forecast để không look-ahead bias và tối ưu hiệu năng.
    """
    df = df.copy()
    df["log_return"] = pd.to_numeric(
        df["log_return"], errors="coerce"
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    scale_factor = 1000.0
    returns = df["log_return"].values * scale_factor
    n = len(returns)
    garch_forecast = np.full(n, np.nan)

    logger.info(f"Đang ước lượng GARCH(1,1) trên chuỗi {n} bars (refit mỗi {refit_frequency}h)...")

    # Bắt đầu dự báo sau khi đã tích lũy đủ min_obs quan sát
    last_res = None
    for t in range(min_obs, n):
        # Tái ước lượng tham số định kỳ mỗi refit_frequency giờ (ví dụ 24h một lần)
        if (t - min_obs) % refit_frequency == 0 or last_res is None:
            train_returns = returns[:t]
            try:
                am = arch_model(train_returns, mean="Zero", vol="GARCH", p=1, q=1, dist="Normal")
                last_res = am.fit(disp="off", show_warning=False)
            except Exception as exc:
                # Nếu không hội tụ, giữ nguyên mô hình trước đó
                logger.warning(f"GARCH không hội tụ tại bar {t}: {exc}")

        if last_res is not None:
            # 1-step ahead forecast tại thời điểm t cho bar tiếp theo
            omega = last_res.params.get("omega", 0.01)
            alpha = last_res.params.get("alpha[1]", 0.05)
            beta = last_res.params.get("beta[1]", 0.90)

            # Tính sigma có điều kiện theo công thức truy hồi: sigma^2_{t} = omega + alpha*eps_{t-1}^2 + beta*sigma_{t-1}^2
            prev_resid = returns[t - 1]
            prev_sigma2 = (last_res.conditional_volatility[-1]) ** 2 if hasattr(last_res, "conditional_volatility") else 1.0
            sigma2_t = omega + alpha * (prev_resid ** 2) + beta * prev_sigma2
            sigma2_t = np.clip(sigma2_t, 1e-4, 1e4)
            sigma_t = np.sqrt(sigma2_t) / scale_factor

            garch_forecast[t] = sigma_t * np.sqrt(annualization_factor)

    historical_vol = pd.to_numeric(
        df.get("vol_hist_24h", pd.Series(0.0, index=df.index)), errors="coerce"
    )
    historical_vol = historical_vol.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    garch_forecast = pd.Series(garch_forecast, index=df.index).replace(
        [np.inf, -np.inf], np.nan
    )
    df["vol_garch_forecast"] = garch_forecast.fillna(historical_vol)

    return df


def _merge_asof_column(
    df: pd.DataFrame,
    reference: pd.DataFrame,
    reference_time_col: str,
    value_col: str,
    output_col: str
) -> pd.DataFrame:
    """As-of join an hourly reference series while preserving input row order."""
    left = df.copy()
    left["_row_order"] = np.arange(len(left))
    left["datetime"] = pd.to_datetime(left["datetime"], utc=True).astype(
        "datetime64[ns, UTC]"
    )
    right = reference[[reference_time_col, value_col]].copy()
    right[reference_time_col] = pd.to_datetime(
        right[reference_time_col], utc=True
    ).astype("datetime64[ns, UTC]")
    right[value_col] = pd.to_numeric(right[value_col], errors="coerce")
    right = right.rename(columns={reference_time_col: "datetime", value_col: output_col})
    merged = pd.merge_asof(
        left.sort_values("datetime"),
        right.dropna(subset=["datetime"]).sort_values("datetime"),
        on="datetime",
        direction="backward"
    )
    return merged.sort_values("_row_order").drop(columns="_row_order").reset_index(drop=True)


def calculate_liquidity_and_gas_features(
    df: pd.DataFrame,
    df_gas: Optional[pd.DataFrame] = None,
    estimated_gas_units: int = 300000,
    df_eth_prices: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Tính các chỉ số thanh khoản (Turnover, Fee Yield) và chi phí Gas cho Rebalance.
    """
    df = df.copy()

    # 1. Turnover & Fee Yield
    safe_tvl = df["tvlUSD"].replace(0, np.nan)
    df["volume_turnover"] = df["volumeUSD"] / safe_tvl
    df["fee_yield"] = df["feesUSD"] / safe_tvl
    df["volume_turnover"] = df["volume_turnover"].fillna(0.0)
    df["fee_yield"] = df["fee_yield"].fillna(0.0)

    # 2. Log changes
    df["volume_log_change"] = np.log((df["volumeUSD"] + 1.0) / (df["volumeUSD"].shift(1) + 1.0))
    df["tvl_log_change"] = np.log((df["tvlUSD"] + 1.0) / (df["tvlUSD"].shift(1) + 1.0))
    df["volume_log_change"] = df["volume_log_change"].fillna(0.0)
    df["tvl_log_change"] = df["tvl_log_change"].fillna(0.0)

    # 3. Chi phí Gas Rebalance (quy USD)
    if "avg_gas_price_gwei" not in df.columns and df_gas is not None and not df_gas.empty:
        df = _merge_asof_column(
            df, df_gas, "datetime", "avg_gas_price_gwei", "avg_gas_price_gwei"
        )
    if "avg_gas_price_gwei" not in df.columns:
        df["avg_gas_price_gwei"] = 50.0
    df["avg_gas_price_gwei"] = pd.to_numeric(
        df["avg_gas_price_gwei"], errors="coerce"
    ).replace([np.inf, -np.inf], np.nan).fillna(50.0)

    pool_name = str(df["pool_name"].iloc[0]) if "pool_name" in df and not df.empty else None
    pool_tokens = pool_name.split("-") if pool_name is not None else []
    if len(pool_tokens) >= 2 and pool_tokens[0] == "WETH" and pool_tokens[1] in {"USDC", "USDT"}:
        eth_price = pd.to_numeric(df["close_clean"], errors="coerce")
    elif df_eth_prices is not None and not df_eth_prices.empty and "datetime" in df.columns:
        df = _merge_asof_column(
            df, df_eth_prices, "datetime", "close", "eth_price_usd"
        )
        eth_price = pd.to_numeric(df["eth_price_usd"], errors="coerce")
    elif pool_name is None:
        eth_price = pd.to_numeric(df["close_clean"], errors="coerce")
    else:
        eth_price = pd.Series(3000.0, index=df.index)
    eth_price = eth_price.replace([np.inf, -np.inf], np.nan)
    eth_price = eth_price.where(eth_price > 0).fillna(3000.0)

    # Chi phí USD = gas_units * (gas_price * 1e-9 ETH) * ETH_price_USD
    df["cost_rebalance_usd"] = (
        estimated_gas_units * (df["avg_gas_price_gwei"] * 1e-9) * eth_price
    )

    return df


def generate_pool_features(
    df_clean: pd.DataFrame,
    df_gas: Optional[pd.DataFrame] = None,
    df_eth_prices: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """Tạo toàn bộ feature cho DataFrame đã làm sạch của một pool."""
    config = load_config()
    vol_windows = config["features"]["volatility_windows"]
    annual_factor = config["features"]["annualization_factor_hourly"]
    refit_freq = config["features"]["garch"]["refit_frequency_hours"]
    est_gas_units = config["features"]["gas"]["estimated_rebalance_gas_units"]

    # 1. Historical & Parkinson Volatility
    df_feat = calculate_returns_and_realized_vol(df_clean, windows=vol_windows, annualization_factor=annual_factor)

    # 2. GARCH(1,1) Volatility Forecast
    df_feat = calculate_garch_volatility(df_feat, refit_frequency=refit_freq, annualization_factor=annual_factor)

    # 3. Thanh khoản, Turnover & Gas Cost
    df_feat = calculate_liquidity_and_gas_features(
        df_feat,
        df_gas=df_gas,
        estimated_gas_units=est_gas_units,
        df_eth_prices=df_eth_prices
    )

    return df_feat
