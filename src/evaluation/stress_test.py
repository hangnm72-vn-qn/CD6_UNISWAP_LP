import pandas as pd

def run_stress_test(engine, df_pool: pd.DataFrame, pool_cfg: dict) -> pd.DataFrame:
    scenarios = [
        {'id': 'SC1_Baseline', 'vol_mult': 1.0, 'volum_mult': 1.0, 'gas_mult': 1.0, 'price_shock': 0.0},
        {'id': 'SC2_Vol_Shock', 'vol_mult': 2.0, 'volum_mult': 1.0, 'gas_mult': 1.0, 'price_shock': 0.0},
        {'id': 'SC3_Volume_Collapse', 'vol_mult': 1.0, 'volum_mult': 0.3, 'gas_mult': 1.0, 'price_shock': 0.0},
        {'id': 'SC4_Gas_Spike', 'vol_mult': 1.0, 'volum_mult': 1.0, 'gas_mult': 5.0, 'price_shock': 0.0},
        {'id': 'SC5_Depeg_Crash', 'vol_mult': 2.5, 'volum_mult': 2.0, 'gas_mult': 2.0, 'price_shock': -0.20}
    ]
    results = []
    for sc in scenarios:
        df_sc = df_pool.copy()
        df_sc['vol_hist_day'] *= sc['vol_mult']
        df_sc['volume'] *= sc['volum_mult']
        df_sc['gas_price_gwei'] = df_sc.get('gas_price_gwei', 25.0) * sc['gas_mult']
        if sc['price_shock'] != 0.0:
            mid = len(df_sc) // 2
            df_sc.loc[df_sc.index >= mid, 'price'] *= (1.0 + sc['price_shock'])
        _, decomp = engine.run(df_sc, "S2", pool_cfg, {'W': 0.10, 'name_ext': 'Stress'})
        results.append({
            'Scenario': sc['id'], 'Net_ER_pct': decomp['Net_ER_pct'],
            'Fees_USD': decomp['Fee_Income_F_T'], 'Inventory_Loss_USD': decomp['D_T_Inventory_Loss'],
            'Gas_USD': decomp['Gas_Cost_G_T'], 'TimeOOR_pct': decomp['TimeOOR_pct']
        })
    return pd.DataFrame(results)
