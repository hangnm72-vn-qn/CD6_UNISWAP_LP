import math
import numpy as np

MIN_TICK = -887272
MAX_TICK = 887272

def get_valid_tick_bounds(tick_spacing: int) -> tuple:
    min_tick = math.ceil(MIN_TICK / tick_spacing) * tick_spacing
    max_tick = math.floor(MAX_TICK / tick_spacing) * tick_spacing
    return min_tick, max_tick

def align_tick(tick: int, tick_spacing: int) -> int:
    min_t, max_t = get_valid_tick_bounds(tick_spacing)
    aligned = int(math.floor(tick / tick_spacing) * tick_spacing)
    return max(min_t, min(aligned, max_t))

def tick_to_price(tick: int, dec0: int = 18, dec1: int = 6) -> float:
    return (1.0001 ** tick) * (10 ** (dec0 - dec1))

def price_to_tick(price: float, dec0: int = 18, dec1: int = 6) -> int:
    p_raw = price / (10 ** (dec0 - dec1))
    return int(math.floor(math.log(max(p_raw, 1e-18)) / math.log(1.0001)))

def calculate_liquidity_from_capital(C0_usd: float, P0: float, PL: float, PU: float, token1_usd: float = 1.0) -> tuple:
    sqrt_P = math.sqrt(P0)
    sqrt_PL = math.sqrt(PL)
    sqrt_PU = math.sqrt(PU)
    if P0 <= PL:
        val_per_L = P0 * (1.0 / sqrt_PL - 1.0 / sqrt_PU)
        L = (C0_usd / token1_usd) / val_per_L
        x0 = L * (1.0 / sqrt_PL - 1.0 / sqrt_PU)
        y0 = 0.0
    elif P0 >= PU:
        val_per_L = sqrt_PU - sqrt_PL
        L = (C0_usd / token1_usd) / val_per_L
        x0 = 0.0
        y0 = L * (sqrt_PU - sqrt_PL)
    else:
        val_per_L = 2.0 * sqrt_P - (P0 / sqrt_PU) - sqrt_PL
        L = (C0_usd / token1_usd) / val_per_L
        x0 = L * (1.0 / sqrt_P - 1.0 / sqrt_PU)
        y0 = L * (sqrt_P - sqrt_PL)
    return L, x0, y0

def get_position_amounts(P: float, PL: float, PU: float, L: float) -> tuple:
    sqrt_P, sqrt_PL, sqrt_PU = math.sqrt(P), math.sqrt(PL), math.sqrt(PU)
    if P <= PL:
        return L * (1.0 / sqrt_PL - 1.0 / sqrt_PU), 0.0
    elif P >= PU:
        return 0.0, L * (sqrt_PU - sqrt_PL)
    else:
        return L * (1.0 / sqrt_P - 1.0 / sqrt_PU), L * (sqrt_P - sqrt_PL)

def get_position_value_usd(P: float, PL: float, PU: float, L: float, token1_usd: float = 1.0) -> float:
    x, y = get_position_amounts(P, PL, PU, L)
    return (x * P + y) * token1_usd
