"""LP strategy backtesting, evaluation metrics, and ledger exports."""

from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd

from src.features.build_features import OUTPUT_TABLES_DIR, ensure_market_features
from src.models.optimizer import calc_v_lp, get_amounts, get_liquidity, get_strategy_range

POOLS_CONFIG = {
    "P1": {"pool_id": "P1", "pair": "WETH/USDC", "fee_tier": 0.0005, "tick_spacing": 10, "dec0": 18, "dec1": 6},
    "P2": {"pool_id": "P2", "pair": "WETH/USDC", "fee_tier": 0.0030, "tick_spacing": 60, "dec0": 18, "dec1": 6},
    "P3": {"pool_id": "P3", "pair": "WETH/USDT", "fee_tier": 0.0030, "tick_spacing": 60, "dec0": 18, "dec1": 6},
    "P4": {"pool_id": "P4", "pair": "WBTC/WETH", "fee_tier": 0.0005, "tick_spacing": 10, "dec0": 8, "dec1": 18},
    "P5": {"pool_id": "P5", "pair": "USDC/USDT", "fee_tier": 0.0001, "tick_spacing": 1, "dec0": 6, "dec1": 6},
}
STRATEGIES = (
    "S1_FullRange",
    "S2_Fixed_0.10",
    "S3_VolScaled",
    "S4_RollingDynamic",
)


def run_backtest(
    daily_data: pd.DataFrame, initial_capital: float = 10_000.0
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run the four notebook LP strategies and return ledger, decomposition, metrics."""
    data = ensure_market_features(daily_data)
    all_ledgers = []
    all_decompositions = []
    metrics_summary = []

    for pool_id in data["pool_id"].unique():
        pool_config: Dict[str, Union[str, int, float]] = POOLS_CONFIG.get(
            pool_id,
            {
                "pool_id": pool_id,
                "pair": str(pool_id),
                "fee_tier": 0.0005,
                "tick_spacing": 10,
                "dec0": 18,
                "dec1": 6,
            },
        )
        pool_data = data[data["pool_id"] == pool_id].copy().reset_index(drop=True)
        if len(pool_data) < 2:
            continue

        for strategy in STRATEGIES:
            initial_price = float(pool_data["price"].iloc[0])
            lower_price, upper_price = get_strategy_range(
                strategy,
                initial_price,
                float(pool_data["volatility"].iloc[0]),
                pool_config,
            )
            amount0 = (initial_capital * 0.5) / max(initial_price, 1e-8)
            amount1 = initial_capital * 0.5
            liquidity = get_liquidity(
                initial_price, lower_price, upper_price, amount0, amount1
            )

            cumulative_fees, cumulative_gas, cumulative_rebalance = 0.0, 15.0, 0.0
            rebalance_count = 0
            previous_lp_value = initial_capital
            previous_hodl_value = initial_capital
            out_of_range_days = 0

            for index, row in pool_data.iterrows():
                current_price = float(row["price"])
                in_range = lower_price <= current_price <= upper_price
                if not in_range:
                    out_of_range_days += 1
                    fee = 0.0
                else:
                    share = min(
                        liquidity
                        / (max(row["tvl"], 1.0) / (2 * np.sqrt(max(current_price, 1e-6)))),
                        0.05,
                    )
                    fee = row["volume"] * float(pool_config["fee_tier"]) * max(share, 1e-5)
                cumulative_fees += fee

                rebalance_now = (
                    strategy == "S3_VolScaled" and index > 0 and index % 7 == 0
                ) or (
                    strategy == "S4_RollingDynamic"
                    and not in_range
                    and index % 3 == 0
                )
                gas, rebalance_cost = 0.0, 0.0
                if rebalance_now:
                    rebalance_count += 1
                    gas = 12.0
                    rebalance_cost = initial_capital * 0.001 * 0.5
                    cumulative_gas += gas
                    cumulative_rebalance += rebalance_cost
                    lower_price, upper_price = get_strategy_range(
                        strategy,
                        current_price,
                        row["volatility"],
                        pool_config,
                    )
                    current_amount0, current_amount1 = get_amounts(
                        current_price, lower_price, upper_price, liquidity
                    )
                    liquidity = get_liquidity(
                        current_price,
                        lower_price,
                        upper_price,
                        current_amount0,
                        current_amount1,
                    )

                lp_value = calc_v_lp(
                    current_price, lower_price, upper_price, liquidity
                )
                hodl_value = amount0 * current_price + amount1
                delta_lp = lp_value - previous_lp_value
                delta_hodl = hodl_value - previous_hodl_value
                excess_return_bps = (
                    10_000.0
                    * (delta_lp - delta_hodl + fee - gas - rebalance_cost)
                    / initial_capital
                )
                previous_lp_value, previous_hodl_value = lp_value, hodl_value
                net_excess_return = (
                    lp_value
                    + cumulative_fees
                    - cumulative_gas
                    - cumulative_rebalance
                    - hodl_value
                ) / initial_capital

                all_ledgers.append({
                    "timestamp": row["timestamp"],
                    "pool": pool_id,
                    "strategy": strategy,
                    "price": current_price,
                    "v_lp": lp_value,
                    "v_hodl": hodl_value,
                    "cum_fees": cumulative_fees,
                    "cum_gas": cumulative_gas,
                    "cum_reb": cumulative_rebalance,
                    "excess_return_bps": excess_return_bps,
                    "net_excess_return": net_excess_return,
                    "in_range": in_range,
                    "rebalance": int(rebalance_now),
                })

            terminal_inventory_loss = hodl_value - lp_value
            net_return_pct = (
                cumulative_fees
                - terminal_inventory_loss
                - cumulative_gas
                - cumulative_rebalance
            ) / initial_capital * 100.0
            all_decompositions.append({
                "pool_id": pool_id,
                "strategy": strategy,
                "C0": initial_capital,
                "V_HODL": hodl_value,
                "V_LP": lp_value,
                "Fees": cumulative_fees,
                "D_T": terminal_inventory_loss,
                "Gas": cumulative_gas,
                "C_reb": cumulative_rebalance,
                "Net_ER_pct": net_return_pct,
            })
            metrics_summary.append({
                "Pool": pool_id,
                "Pair": pool_config["pair"],
                "Strategy": strategy,
                "Net_ER_pct": net_return_pct,
                "TimeOOR_pct": out_of_range_days / len(pool_data) * 100.0,
                "Rebalances": rebalance_count,
            })

    return (
        pd.DataFrame(all_ledgers),
        pd.DataFrame(all_decompositions),
        pd.DataFrame(metrics_summary),
    )


def export_backtest_results(
    ledger: pd.DataFrame,
    decompositions: pd.DataFrame,
    metrics: pd.DataFrame,
    output_dir: Optional[Union[str, Path]] = None,
) -> None:
    """Write the position ledger, return decomposition, and metrics tables."""
    tables_dir = Path(output_dir) if output_dir is not None else OUTPUT_TABLES_DIR
    tables_dir.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(tables_dir / "03_position_ledger.csv", index=False)
    decompositions.to_csv(tables_dir / "04_decomposition.csv", index=False)
    metrics.to_csv(tables_dir / "06_backtest_metrics.csv", index=False)
