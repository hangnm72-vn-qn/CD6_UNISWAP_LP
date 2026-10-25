import numpy as np
import pandas as pd

def calculate_market_features(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    df = df.copy()
    df['ret'] = np.log(df['price'] / df['price'].shift(1))
    df['vol_hist_day'] = df['ret'].rolling(window=window).std()
    df['vol_hist_annual'] = df['vol_hist_day'] * np.sqrt(365)

    rets = df['ret'].fillna(0.0).values
    n = len(rets)
    garch_vol = np.zeros(n)
    init_w = max(30, window)
    for i in range(min(init_w, n)):
        garch_vol[i] = np.std(rets[:max(2, i+1)]) * np.sqrt(365)

    omega, alpha, beta = 1e-5, 0.08, 0.90
    var_t = np.var(rets[:init_w]) if n >= init_w else 1e-4
    for t in range(init_w, n):
        var_t = omega + alpha * (rets[t-1] ** 2) + beta * var_t
        garch_vol[t] = np.sqrt(max(var_t, 1e-8)) * np.sqrt(365)
    df['vol_garch_annual'] = garch_vol
    return df

def compute_gas_cost_usd(gas_used: float, gas_price_gwei: float, eth_price_usd: float) -> float:
    return gas_used * gas_price_gwei * 1e-9 * eth_price_usd
