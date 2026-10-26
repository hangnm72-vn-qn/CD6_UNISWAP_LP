import math
import numpy as np
import pandas as pd
from src.models.uniswap_v3_math import align_tick, price_to_tick, tick_to_price, calculate_liquidity_from_capital, get_position_value_usd

class LPOptimizerEngine:
    def __init__(self, pool_cfg: dict, q_max: float = 0.40, max_rebal_limit: int = 4, cvar_loss_limit_pct: float = 0.15, capital_max: float = 10000.0):
        self.pool_cfg = pool_cfg
        self.q_max = q_max
        self.max_rebal_limit = max_rebal_limit
        self.L_max = cvar_loss_limit_pct
        self.capital_max = capital_max

    def optimize_W(self, P0: float, sigma_annual: float, expected_daily_volume: float, C0: float = 10000.0, H_days: int = 14,
                candidates_W=(0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50)) -> pd.DataFrame:
         M = 5000
         n_steps = H_days * 24
         dt = 1.0 / (365.0 * 24.0)
         paths = np.zeros((M, n_steps + 1))
         paths[:, 0] = P0
         sigma = max(sigma_annual, 0.05)
         np.random.seed(42)
         for t in range(n_steps):
             z = np.random.normal(0, 1, M)
             paths[:, t + 1] = paths[:, t] * np.exp((-0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * z)

         ts, dec0, dec1 = self.pool_cfg['tick_spacing'], self.pool_cfg['dec0'], self.pool_cfg['dec1']
         records = []

         for W in candidates_W:
             PL_raw = P0 * math.exp(-W / 2.0)
             PU_raw = P0 * math.exp(W / 2.0)
             tL = align_tick(price_to_tick(PL_raw, dec0, dec1), ts)
             tU = align_tick(price_to_tick(PU_raw, dec0, dec1), ts)
             if tL >= tU: tU = tL + ts
             PL, PU = tick_to_price(tL, dec0, dec1), tick_to_price(tU, dec0, dec1)
             aligned_W = math.log(PU / PL)
             L, x0, y0 = calculate_liquidity_from_capital(C0, P0, PL, PU)

             oor_paths = 0
             time_oor = 0.0
             excess_returns = np.zeros(M)
             rebal_viols = 0

             for m in range(M):
                 path = paths[m, :]
                 is_out = (path < PL) | (path > PU)
                 if np.any(is_out): oor_paths += 1
                 time_oor += np.mean(is_out)
                 if np.sum(np.diff(is_out.astype(int)) > 0) > self.max_rebal_limit:
                     rebal_viols += 1
                 P_end = path[-1]
                 v_lp = get_position_value_usd(P_end, PL, PU, L)
                 v_hd = x0 * P_end + y0
                 fee = (expected_daily_volume * H_days * self.pool_cfg['fee_tier'] * 0.0005) * np.mean(~is_out)
                 excess_returns[m] = (v_lp + fee - v_hd) / C0

             P_OOR = oor_paths / M
             TimeOOR = time_oor / M
             Exp_ER = np.mean(excess_returns) * 100.0
             var_5 = np.percentile(excess_returns, 5)
             cvar_5 = np.mean(excess_returns[excess_returns <= var_5])

             viols = []
             if P_OOR > self.q_max: viols.append(f"P_OOR ({P_OOR:.1%}) > q_max ({self.q_max:.1%})")
             if cvar_5 < -self.L_max: viols.append(f"CVaR5% ({cvar_5:.1%}) < -L_max ({-self.L_max:.1%})")
             if (rebal_viols / M) > 0.05: viols.append("Rebalances > Limit on >5% paths")
             is_feasible = (len(viols) == 0)

             records.append({
                 'Candidate_W': W, 'Aligned_W': aligned_W, 'Tick_L': tL, 'Tick_U': tU,
                 'P_L': PL, 'P_U': PU, 'Expected_ER_pct': Exp_ER, 'P_OOR': P_OOR, 'TimeOOR': TimeOOR,
                 'CVaR_5pct': cvar_5, 'Feasible': is_feasible, 'Violations': "; ".join(viols) if not is_feasible else "None"
             })
         return pd.DataFrame(records)
