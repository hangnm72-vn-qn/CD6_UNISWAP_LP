"""Data loading, normalization, and feature preparation for notebook analysis."""

from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"
OUTPUT_FIGURES_DIR = PROJECT_ROOT / "outputs" / "figures"
DEFAULT_DAILY_DATA_PATH = PROJECT_ROOT / "data" / "processed" / "pools_daily.csv"

_COLUMN_ALIASES = {
    "timestamp": {"timestamp", "date", "datetime", "time", "day", "periodstartunix"},
    "pool_id": {
        "pool_id", "pool", "pool_name", "pair", "symbol", "pool_address",
        "address", "name",
    },
    "price": {"price", "close", "pool_price", "token_price"},
    "volume": {"volume", "volume_usd", "trading_volume", "volumeusd"},
    "tvl": {"tvl", "tvl_usd", "tvlusd", "totalvaluelockedusd"},
}


def map_to_pool_code(value: object) -> object:
    """Map common pool labels to the P1-P5 identifiers used in the notebook."""
    normalized = str(value).upper().replace("/", "-").replace("_", "-").replace(" ", "")
    if "USDC" in normalized and "USDT" in normalized:
        return "P5"
    if "BTC" in normalized:
        return "P4"
    if "USDT" in normalized and any(token in normalized for token in ("030", "0.3", "3000")):
        return "P3"
    if "USDC" in normalized and any(token in normalized for token in ("030", "0.3", "3000")):
        return "P2"
    if "USDC" in normalized and any(token in normalized for token in ("005", "0.05", "500")):
        return "P1"
    for pool_id in ("P1", "P2", "P3", "P4", "P5"):
        if pool_id in normalized:
            return pool_id
    return value


def prepare_daily_data(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize daily input columns, timestamps, and pool identifiers."""
    df_daily = data.copy()
    rename_map = {}
    for column in df_daily.columns:
        normalized = str(column).strip().lower()
        for canonical, aliases in _COLUMN_ALIASES.items():
            if normalized in aliases:
                rename_map[column] = canonical
                break
    df_daily = df_daily.rename(columns=rename_map)

    if "timestamp" not in df_daily.columns:
        if df_daily.empty and len(df_daily.columns) == 0:
            raise ValueError("Daily input must contain a timestamp column.")
        df_daily = df_daily.rename(columns={df_daily.columns[0]: "timestamp"})

    timestamps = df_daily["timestamp"]
    if pd.api.types.is_numeric_dtype(timestamps):
        if not timestamps.empty:
            unit = "ms" if timestamps.iloc[0] > 1e11 else "s"
            df_daily["timestamp"] = pd.to_datetime(timestamps, unit=unit, utc=True)
        else:
            df_daily["timestamp"] = pd.to_datetime(timestamps, utc=True)
    else:
        df_daily["timestamp"] = pd.to_datetime(timestamps, utc=True)

    if "pool_id" not in df_daily.columns:
        df_daily["pool_id"] = "P1"
    else:
        df_daily["pool_id"] = df_daily["pool_id"].apply(map_to_pool_code)

    return df_daily.sort_values(
        by=["pool_id", "timestamp"]
    ).reset_index(drop=True)


def load_daily_data(
    data_path: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """Load and normalize the project's daily pool data."""
    path = Path(data_path) if data_path is not None else DEFAULT_DAILY_DATA_PATH
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.is_file():
        raise FileNotFoundError(f"Daily pool data file was not found: {path}")
    return prepare_daily_data(pd.read_csv(path))


def ensure_market_features(data: pd.DataFrame) -> pd.DataFrame:
    """Ensure volume, log-return, and 14-day rolling volatility are available."""
    df = data.copy()
    if "volume" not in df.columns:
        df["volume"] = 10_000_000.0
    if "tvl" not in df.columns:
        df["tvl"] = 50_000_000.0

    if "volatility" not in df.columns:
        if "pool_id" in df.columns:
            grouped_prices = df.groupby("pool_id", sort=False)["price"]
            df["ret"] = grouped_prices.transform(
                lambda prices: np.log(prices / prices.shift(1))
            ).fillna(0.0)
            df["volatility"] = df.groupby("pool_id", sort=False)["ret"].transform(
                lambda returns: returns.rolling(14, min_periods=1).std()
            ).fillna(0.01)
        else:
            df["ret"] = np.log(df["price"] / df["price"].shift(1)).fillna(0.0)
            df["volatility"] = (
                df["ret"].rolling(14, min_periods=1).std().fillna(0.01)
            )
    return df
