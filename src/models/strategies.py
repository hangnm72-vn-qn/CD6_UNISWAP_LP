import math
import numpy as np
from src.models.uniswap_v3_math import align_tick, price_to_tick, tick_to_price, get_valid_tick_bounds

def compute_strategy_bounds(strategy_type: str, P0: float, vol_day: float, pool_cfg: dict, params: dict) -> tuple:
    ts = pool_cfg['tick_spacing']
    dec0, dec1 = pool_cfg['dec0'], pool_cfg['dec1']
    if strategy_type == "S1":
        min_t, max_t = get_valid_tick_bounds(ts)
        return tick_to_price(min_t, dec0, dec1), tick_to_price(max_t, dec0, dec1)
    elif strategy_type == "S2":
        W = params.get('W', 0.10)
        PL_raw = P0 * math.exp(-W / 2.0)
        PU_raw = P0 * math.exp(W / 2.0)
    elif strategy_type in ["S3", "S4"]:
        k = params.get('k', 1.5)
        W = np.clip(k * vol_day * math.sqrt(7.0), params.get('W_min', 0.02), params.get('W_max', 0.80))
        PL_raw = P0 * math.exp(-W / 2.0)
        PU_raw = P0 * math.exp(W / 2.0)
    else:
        raise ValueError(f"Không rõ chiến lược: {strategy_type}")
    tL = align_tick(price_to_tick(PL_raw, dec0, dec1), ts)
    tU = align_tick(price_to_tick(PU_raw, dec0, dec1), ts)
    if tL >= tU:
        tU = tL + ts
    return tick_to_price(tL, dec0, dec1), tick_to_price(tU, dec0, dec1)
