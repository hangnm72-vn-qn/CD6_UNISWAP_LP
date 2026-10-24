"""Uniswap v3 range mathematics and regression models."""

from pathlib import Path
from typing import Dict, Optional, Tuple, Union
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import minimize
import statsmodels.api as sm
from statsmodels.formula.api import quantreg

from src.features.build_features import OUTPUT_TABLES_DIR, ensure_market_features

def tick_to_price(tick: int, dec0: int = 18, dec1: int = 6) -> float:
    return (1.0001 ** tick) * (10 ** (dec0 - dec1))


def price_to_tick(price: float, dec0: int = 18, dec1: int = 6) -> int:
    raw_price = price / (10 ** (dec0 - dec1))
    return int(np.floor(np.log(raw_price) / np.log(1.0001)))


def align_tick(tick: int, tick_spacing: int) -> int:
    remainder = tick % tick_spacing
    return tick if remainder == 0 else tick - remainder


def get_liquidity(
    price: float, lower_price: float, upper_price: float, amount0: float, amount1: float
) -> float:
    sqrt_price, sqrt_lower, sqrt_upper = (
        np.sqrt(price), np.sqrt(lower_price), np.sqrt(upper_price)
    )
    if price <= lower_price:
        return amount0 * (sqrt_lower * sqrt_upper) / (sqrt_upper - sqrt_lower)
    if price >= upper_price:
        return amount1 / (sqrt_upper - sqrt_lower)
    liquidity0 = amount0 * (sqrt_price * sqrt_upper) / (sqrt_upper - sqrt_price)
    liquidity1 = amount1 / (sqrt_price - sqrt_lower)
    return min(liquidity0, liquidity1)


def get_amounts(
    price: float, lower_price: float, upper_price: float, liquidity: float
) -> Tuple[float, float]:
    sqrt_price, sqrt_lower, sqrt_upper = (
        np.sqrt(price), np.sqrt(lower_price), np.sqrt(upper_price)
    )
    if price <= lower_price:
        return (
            liquidity * (sqrt_upper - sqrt_lower) / (sqrt_lower * sqrt_upper),
            0.0,
        )
    if price >= upper_price:
        return 0.0, liquidity * (sqrt_upper - sqrt_lower)
    return (
        liquidity * (sqrt_upper - sqrt_price) / (sqrt_price * sqrt_upper),
        liquidity * (sqrt_price - sqrt_lower),
    )


def calc_v_lp(price: float, lower_price: float, upper_price: float, liquidity: float) -> float:
    amount0, amount1 = get_amounts(price, lower_price, upper_price, liquidity)
    return amount0 * price + amount1


def get_strategy_range(
    strategy_name: str,
    initial_price: float,
    daily_volatility: float,
    pool_config: Dict[str, Union[str, int, float]],
    width: float = 0.10,
    volatility_multiplier: float = 1.5,
) -> Tuple[float, float]:
    tick_spacing = int(pool_config["tick_spacing"])
    dec0, dec1 = int(pool_config["dec0"]), int(pool_config["dec1"])

    if strategy_name == "S1_FullRange":
        lower_tick = align_tick(-887272, tick_spacing)
        upper_tick = align_tick(887272, tick_spacing)
    elif strategy_name.startswith("S2_Fixed"):
        lower_raw = initial_price * np.exp(-width / 2.0)
        upper_raw = initial_price * np.exp(width / 2.0)
        lower_tick = align_tick(price_to_tick(lower_raw, dec0, dec1), tick_spacing)
        upper_tick = align_tick(price_to_tick(upper_raw, dec0, dec1), tick_spacing)
    elif strategy_name.startswith(("S3", "S4")):
        volatility_width = np.clip(
            volatility_multiplier * daily_volatility * np.sqrt(7), 0.02, 0.80
        )
        lower_raw = initial_price * np.exp(-volatility_width / 2.0)
        upper_raw = initial_price * np.exp(volatility_width / 2.0)
        lower_tick = align_tick(price_to_tick(lower_raw, dec0, dec1), tick_spacing)
        upper_tick = align_tick(price_to_tick(upper_raw, dec0, dec1), tick_spacing)
    else:
        raise ValueError(f"Unsupported LP strategy: {strategy_name}")

    if lower_tick >= upper_tick:
        upper_tick = lower_tick + tick_spacing
    return (
        tick_to_price(lower_tick, dec0, dec1),
        tick_to_price(upper_tick, dec0, dec1),
    )


def run_regressions(
    daily_data: pd.DataFrame,
    ledger: pd.DataFrame,
    output_dir: Optional[Union[str, Path]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, object]:
    """Fit panel fixed-effects OLS and quantile regressions; export their tables."""
    daily_data = ensure_market_features(daily_data)
    regression_data = ledger[ledger["strategy"] == "S2_Fixed_0.10"].copy()
    columns_to_merge = ["timestamp", "pool_id", "volatility", "volume"]
    regression_data = regression_data.merge(
        daily_data[columns_to_merge],
        left_on=["timestamp", "pool"],
        right_on=["timestamp", "pool_id"],
        how="left",
    )

    regression_data["vol_lag"] = (
        regression_data.groupby("pool")["volatility"].shift(1).bfill().fillna(0.02)
    )
    regression_data["volume_lag"] = (
        regression_data.groupby("pool")["volume"].shift(1).bfill().fillna(1_000_000.0)
    )
    regression_data["log_volume"] = np.log1p(regression_data["volume_lag"])
    regression_data["W"] = 0.10
    regression_data["Y_bps"] = regression_data["excess_return_bps"].fillna(0.0)
    regression_data["rebalance"] = regression_data["rebalance"].fillna(0)

    pool_dummies = pd.get_dummies(
        regression_data["pool"], drop_first=True, prefix="pool", dtype=float
    )
    design_matrix = pd.concat(
        [regression_data[["vol_lag", "log_volume", "W", "rebalance"]], pool_dummies],
        axis=1,
    )
    design_matrix = sm.add_constant(design_matrix)
    target = regression_data["Y_bps"]
    ols_model = sm.OLS(target, design_matrix).fit(
        cov_type="HAC", cov_kwds={"maxlags": 7}
    )
    panel_results = pd.DataFrame({
        "Variable": design_matrix.columns,
        "Coefficient": ols_model.params.values,
        "Std_Error": ols_model.bse.values,
        "t_stat": ols_model.tvalues.values,
        "p_value": ols_model.pvalues.values,
    })

    quantile_formula = "Y_bps ~ vol_lag + log_volume + W + rebalance"
    quantile_rows = []
    quantiles = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
    for quantile in quantiles:
        try:
            result = quantreg(quantile_formula, regression_data).fit(
                q=quantile, max_iter=2000
            )
        except Exception as exc:
            warnings.warn(
                f"Quantile regression did not converge for tau={quantile}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        for variable in ["Intercept", "vol_lag", "log_volume", "W", "rebalance"]:
            quantile_rows.append({
                "Quantile": quantile,
                "Variable": variable,
                "Coef": result.params[variable],
                "Std_Err": result.bse[variable],
                "p_value": result.pvalues[variable],
            })
    quantile_results = pd.DataFrame(quantile_rows)

    tables_dir = Path(output_dir) if output_dir is not None else OUTPUT_TABLES_DIR
    tables_dir.mkdir(parents=True, exist_ok=True)
    panel_results.to_csv(tables_dir / "05_regression_panel_fe.csv", index=False)
    panel_results.to_latex(
        tables_dir / "table_4_5_panel_fe.tex",
        index=False,
        float_format="%.4f",
    )
    quantile_results.to_csv(
        tables_dir / "05_regression_quantiles.csv", index=False
    )
    return regression_data, panel_results, quantile_results, ols_model
