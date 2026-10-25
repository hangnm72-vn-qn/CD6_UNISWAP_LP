import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.formula.api import quantreg

def run_panel_fe_bootstrap(df_panel: pd.DataFrame, vol_col: str, n_bootstrap: int = 100, block_size: int = 7) -> tuple:
    df = df_panel.copy()
    df['log_vol'] = np.log1p(df['volume_lag'])
    pool_dummies = pd.get_dummies(df['pool'], drop_first=True, prefix='pool', dtype=float)
    feature_cols = [vol_col, 'log_vol', 'W', 'rebalance']
    X = pd.concat([df[feature_cols], pool_dummies], axis=1)
    X = sm.add_constant(X)
    y = df['Y_bps']

    base_model = sm.OLS(y, X).fit()
    base_params = base_model.params

    unique_dates = np.sort(df['timestamp'].unique())
    n_dates = len(unique_dates)
    n_blocks = int(np.ceil(n_dates / block_size))
    boot_coefs = []
    np.random.seed(42)

    for _ in range(n_bootstrap):
        rand_starts = np.random.randint(0, max(1, n_dates - block_size + 1), size=n_blocks)
        sampled_dates = []
        for s in rand_starts:
            sampled_dates.extend(unique_dates[s: s + block_size])
        sampled_dates = sampled_dates[:n_dates]

        b_sample = df[df['timestamp'].isin(sampled_dates)]
        b_dummies = pd.get_dummies(b_sample['pool'], drop_first=True, prefix='pool', dtype=float)
        b_X = pd.concat([b_sample[feature_cols], b_dummies], axis=1)
        b_X = sm.add_constant(b_X).reindex(columns=X.columns, fill_value=0.0)
        b_y = b_sample['Y_bps']
        try:
            b_res = sm.OLS(b_y, b_X).fit()
            boot_coefs.append(b_res.params)
        except Exception:
            continue

    boot_se = pd.DataFrame(boot_coefs).std(axis=0)
    rows = []
    for var in ['const'] + feature_cols:
        coef = base_params[var]
        se = boot_se.get(var, base_model.bse[var])
        t_stat = coef / se if se > 0 else np.nan
        rows.append({
            'Variable': var, 'Coefficient': coef, 'Bootstrap_SE': se, 't_stat': t_stat,
            'CI_95_Lower': coef - 1.96 * se, 'CI_95_Upper': coef + 1.96 * se,
            'p_value': 2 * (1 - sm.stats.norm.cdf(abs(t_stat))) if not np.isnan(t_stat) else np.nan
        })
    return pd.DataFrame(rows), base_model.rsquared

def run_fee_tier_pair_fe(df_panel: pd.DataFrame, vol_col: str) -> pd.DataFrame:
    df = df_panel.copy()
    df['log_vol'] = np.log1p(df['volume_lag'])
    pair_dummies = pd.get_dummies(df['pair'], drop_first=True, prefix='pair', dtype=float)
    X = pd.concat([df[[vol_col, 'log_vol', 'W', 'rebalance', 'fee_tier']], pair_dummies], axis=1)
    X = sm.add_constant(X)
    res = sm.OLS(df['Y_bps'], X).fit()
    return pd.DataFrame({'Variable': X.columns, 'Coefficient': res.params, 'Std_Error': res.bse, 't_stat': res.tvalues, 'p_value': res.pvalues})

def run_quantile_regression_panel(df_panel: pd.DataFrame, vol_col: str, tau_list=(0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)) -> pd.DataFrame:
    df = df_panel.copy()
    df['log_vol'] = np.log1p(df['volume_lag'])
    formula = f"Y_bps ~ {vol_col} + log_vol + W + rebalance + C(pool)"
    q_rows = []
    for tau in tau_list:
        try:
            q_res = quantreg(formula, df).fit(q=tau, max_iter=2500)
            for var in ['Intercept', vol_col, 'log_vol', 'W', 'rebalance']:
                q_rows.append({'Quantile': tau, 'Variable': var, 'Coef': q_res.params[var], 'Std_Err': q_res.bse[var], 'p_value': q_res.pvalues[var]})
        except Exception:
            continue
    return pd.DataFrame(q_rows)
