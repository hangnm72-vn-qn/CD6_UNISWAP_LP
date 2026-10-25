import math
import numpy as np
import pandas as pd
from src.models.uniswap_v3_math import calculate_liquidity_from_capital, get_position_value_usd
from src.features.market_features import compute_gas_cost_usd
from src.models.strategies import compute_strategy_bounds

class BacktestEngine:
    def __init__(self, initial_capital_usd: float = 10000.0, mint_gas: float = 120000,
                 rebal_gas: float = 250000, burn_gas: float = 80000, slippage_pct: float = 0.001):
        self.C0 = initial_capital_usd
        self.mint_gas = mint_gas
        self.rebal_gas = rebal_gas
        self.burn_gas = burn_gas
        self.slippage_pct = slippage_pct

    def run(self, df: pd.DataFrame, strategy_type: str, pool_cfg: dict, params: dict) -> tuple:
        fee_tier = pool_cfg['fee_tier']
        is_token1_usd = pool_cfg.get('is_token1_usd', True)
        def get_t1_usd(row):
            return 1.0 if is_token1_usd else float(row.get('eth_price', 2500.0))

        P0 = float(df['price'].iloc[0])
        t1_usd_0 = get_t1_usd(df.iloc[0])
        gas_price_0 = float(df['gas_price_gwei'].iloc[0]) if 'gas_price_gwei' in df.columns else 25.0
        eth_price_0 = float(df['eth_price'].iloc[0]) if 'eth_price' in df.columns else 2500.0

        vol_0 = float(df['vol_hist_day'].iloc[0]) if 'vol_hist_day' in df.columns and not pd.isna(df['vol_hist_day'].iloc[0]) else 0.03
        PL, PU = compute_strategy_bounds(strategy_type, P0, vol_0, pool_cfg, params)

        init_gas = compute_gas_cost_usd(self.mint_gas, gas_price_0, eth_price_0)
        curr_cap = self.C0 - init_gas
        L, x0, y0 = calculate_liquidity_from_capital(curr_cap, P0, PL, PU, t1_usd_0)
        _, x_hodl, y_hodl = calculate_liquidity_from_capital(self.C0, P0, PL, PU, t1_usd_0)

        cum_fees, cum_gas, cum_reb = 0.0, init_gas, 0.0
        rebal_count = 0
        rebal_history = []
        v_lp_prev, v_hodl_prev = curr_cap, self.C0
        hours_oor, last_rebal_idx = 0, 0
        ledger = []

        for t_idx, row in df.iterrows():
            P_t = float(row['price'])
            t1_usd_t = get_t1_usd(row)
            gas_p_t = float(row['gas_price_gwei']) if 'gas_price_gwei' in row else 25.0
            eth_p_t = float(row['eth_price']) if 'eth_price' in row else 2500.0

            in_range = (PL <= P_t <= PU)
            hours_oor = (hours_oor + 24) if not in_range else 0

            if in_range:
                L_pool = float(row['active_liquidity']) if 'active_liquidity' in row and row['active_liquidity'] > 0                          else (float(row['tvl']) / t1_usd_t) / (2.0 * math.sqrt(max(P_t, 1e-8)))
                share = min(L / max(L_pool, 1e-6), 0.05)
                fee_usd = float(row['volume']) * fee_tier * max(share, 1e-6)
            else:
                fee_usd = 0.0
            cum_fees += fee_usd

            need_rebal = False
            gas_reb_t, reb_cost_t = 0.0, 0.0
            if strategy_type == "S3":
                if t_idx > 0 and (t_idx - last_rebal_idx) >= 7:
                    v_lag = float(row['vol_hist_day']) if not pd.isna(row['vol_hist_day']) else 0.03
                    n_PL, n_PU = compute_strategy_bounds("S3", P_t, v_lag, pool_cfg, params)
                    if n_PL != PL or n_PU != PU:
                        need_rebal = True
            elif strategy_type == "S4":
                dist_e = min(math.log(PU / max(P_t, 1e-8)), math.log(max(P_t, 1e-8) / PL))
                t1 = (hours_oor >= params.get('oor_trigger_hours', 24))
                t2 = (dist_e <= params.get('delta_P', 0.02))
                if t1 or t2:
                    d_since = t_idx - last_rebal_idx
                    reb_30d = sum(1 for d in rebal_history if (t_idx - d) <= 30)
                    g1 = (d_since >= params.get('cooldown_days', 1))
                    g2 = (reb_30d < params.get('max_reb_30d', 5))
                    est_c = compute_gas_cost_usd(self.rebal_gas, gas_p_t, eth_p_t) + (curr_cap * self.slippage_pct)
                    g3 = (fee_usd * 14.0 > est_c)
                    if g1 and g2 and g3:
                        need_rebal = True

            if need_rebal:
                rebal_count += 1
                last_rebal_idx = t_idx
                rebal_history.append(t_idx)
                gas_reb_t = compute_gas_cost_usd(self.rebal_gas, gas_p_t, eth_p_t)
                reb_cost_t = curr_cap * self.slippage_pct
                cum_gas += gas_reb_t
                cum_reb += reb_cost_t

                inv_now = get_position_value_usd(P_t, PL, PU, L, t1_usd_t)
                curr_cap = max(inv_now - gas_reb_t - reb_cost_t, 100.0)
                v_now = float(row['vol_hist_day']) if not pd.isna(row['vol_hist_day']) else 0.03
                PL, PU = compute_strategy_bounds(strategy_type, P_t, v_now, pool_cfg, params)
                L, _, _ = calculate_liquidity_from_capital(curr_cap, P_t, PL, PU, t1_usd_t)

            v_lp_t = get_position_value_usd(P_t, PL, PU, L, t1_usd_t)
            v_hodl_t = (x_hodl * P_t + y_hodl) * t1_usd_t
            delta_lp = v_lp_t - v_lp_prev
            delta_hodl = v_hodl_t - v_hodl_prev
            er_bps = 10000.0 * (delta_lp - delta_hodl + fee_usd - gas_reb_t - reb_cost_t) / self.C0
            v_lp_prev, v_hodl_prev = v_lp_t, v_hodl_t

            ledger.append({
                'timestamp': row['timestamp'], 'pool': pool_cfg['pool_id'],
                'strategy': f"{strategy_type}_{params.get('name_ext', '')}",
                'price': P_t, 'v_lp': v_lp_t, 'v_hodl': v_hodl_t, 'fee_income_usd': fee_usd,
                'cum_fees_usd': cum_fees, 'cum_gas_usd': cum_gas, 'cum_reb_usd': cum_reb,
                'excess_return_bps': er_bps, 'in_range': in_range, 'rebalanced': int(need_rebal)
            })

        final_gp = float(df['gas_price_gwei'].iloc[-1]) if 'gas_price_gwei' in df.columns else 25.0
        final_ep = float(df['eth_price'].iloc[-1]) if 'eth_price' in df.columns else 2500.0
        burn_cost = compute_gas_cost_usd(self.burn_gas, final_gp, final_ep)
        cum_gas += burn_cost

        df_l = pd.DataFrame(ledger)
        v_lp_f, v_hd_f = df_l['v_lp'].iloc[-1], df_l['v_hodl'].iloc[-1]
        D_T = v_hd_f - v_lp_f
        net_er = cum_fees - D_T - cum_gas - cum_reb
        decomp = {
            'pool_id': pool_cfg['pool_id'], 'strategy': f"{strategy_type}_{params.get('name_ext', '')}",
            'C0': self.C0, 'V_HODL_T': v_hd_f, 'V_LP_T': v_lp_f, 'D_T_Inventory_Loss': D_T,
            'Fee_Income_F_T': cum_fees, 'Gas_Cost_G_T': cum_gas, 'Rebalance_Cost_C_reb': cum_reb,
            'Net_ER_USD': net_er, 'Net_ER_pct': (net_er / self.C0) * 100.0,
            'TimeOOR_pct': (1.0 - df_l['in_range'].mean()) * 100.0, 'Rebalance_Count': rebal_count
        }
        return df_l, decomp
