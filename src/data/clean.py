import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

# Đảm bảo import đúng utils từ src
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

from src.data.utils import load_config, logger


def load_raw_json(filepath: str) -> List[Dict[str, Any]]:
    """Đọc dữ liệu thô từ file JSON trong data/raw/."""
    path = Path(filepath)
    if not path.exists():
        logger.warning(f"File không tồn tại: {filepath}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def standardize_pool_price(df: pd.DataFrame, pool_config: Dict[str, Any]) -> pd.DataFrame:
    """
    Chuẩn hóa cột giá theo đúng quy ước tài chính price_quote.
    Trong dữ liệu Subgraph đang dùng, OHLC khớp với token0Price; token1Price
    là chiều giá nghịch đảo.
    """
    price_quote = pool_config["price_quote"]
    t0_sym = pool_config["token0"]["symbol"]
    t1_sym = pool_config["token1"]["symbol"]

    # Ép kiểu dữ liệu số
    numeric_cols = [
        "token0Price", "token1Price", "sqrtPrice", "tick",
        "feesUSD", "tvlUSD", "volumeUSD", "volumeToken0", "volumeToken1",
        "txCount", "open", "high", "low", "close"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Các bản ghi khởi tạo của Subgraph đôi khi chứa giá bằng 0.
    invalid_price_cols = [
        "price", "open", "high", "low", "close", "token0Price", "token1Price"
    ]
    for col in invalid_price_cols:
        if col in df.columns:
            df[col] = df[col].where(df[col] > 0)

    # Chọn trường giá theo đơn vị yêu cầu và thứ tự token của pool.
    if price_quote == "USD_per_WETH":
        if t0_sym in ["USDC", "USDT"] and t1_sym == "WETH":
            price_col = "token0Price"
        elif t0_sym == "WETH" and t1_sym in ["USDC", "USDT"]:
            price_col = "token1Price"
        else:
            raise ValueError(f"Không thể chuẩn hóa USD_per_WETH cho pool {pool_config['name']}.")
    elif price_quote == "WETH_per_WBTC":
        if t0_sym == "WBTC" and t1_sym == "WETH":
            price_col = "token1Price"
        elif t0_sym == "WETH" and t1_sym == "WBTC":
            price_col = "token0Price"
        else:
            raise ValueError(f"Không thể chuẩn hóa WETH_per_WBTC cho pool {pool_config['name']}.")
    elif price_quote == "USDT_per_USDC":
        if t0_sym == "USDC" and t1_sym == "USDT":
            price_col = "token0Price"
        elif t0_sym == "USDT" and t1_sym == "USDC":
            price_col = "token1Price"
        else:
            raise ValueError(f"Không thể chuẩn hóa USDT_per_USDC cho pool {pool_config['name']}.")
    else:
        price_col = "close"

    df["price"] = df[price_col]
    if price_col == "token1Price":
        df["open_clean"] = 1.0 / df["open"]
        df["high_clean"] = 1.0 / df["low"]
        df["low_clean"] = 1.0 / df["high"]
    else:
        df["open_clean"] = df["open"]
        df["high_clean"] = df["high"]
        df["low_clean"] = df["low"]
    df["close_clean"] = df["price"]

    for col in ["open_clean", "high_clean", "low_clean", "close_clean"]:
        df[col] = df[col].where(df[col] > 0)

    return df


def reindex_and_fill_timeline(
    df: pd.DataFrame,
    start_dt: pd.Timestamp,
    end_dt: pd.Timestamp,
    freq: str = "1h"
) -> pd.DataFrame:
    """
    Tạo lưới thời gian liên tục UTC.
    Forward-fill giá đóng, set volume/fees = 0 cho các bar không có swap.
    """
    df = df.copy()
    if "datetime" not in df.columns:
        raise ValueError("Thiếu cột 'datetime' trong DataFrame.")

    if "price" not in df.columns:
        raise ValueError("Thiếu cột 'price' trong DataFrame.")

    for col in ["price", "open_clean", "high_clean", "low_clean", "close_clean"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df[col] = df[col].where(df[col] > 0)
    if "close_clean" not in df.columns:
        df["close_clean"] = df["price"]

    valid_prices = df.loc[df["price"].notna(), "datetime"]
    if valid_prices.empty:
        raise ValueError("Không có giá hợp lệ để điền chuỗi thời gian.")
    pool_genesis = valid_prices.min()

    df = df.drop_duplicates(subset=["datetime"]).sort_values("datetime")
    df = df.set_index("datetime")

    full_idx = pd.date_range(start=start_dt, end=end_dt, freq=freq, tz="UTC", name="datetime")
    df_reindexed = df.reindex(full_idx)

    # Mọi bar không có giá hợp lệ trong dữ liệu gốc (kể cả trước genesis) là filled.
    df_reindexed["is_filled"] = df_reindexed["price"].isna()

    # Forward fill cho giá và tick (giữ nguyên trạng thái thị trường khi không có lệnh mới)
    price_cols = ["price", "open_clean", "high_clean", "low_clean", "close_clean", "tick", "sqrtPrice", "tvlUSD"]
    for col in price_cols:
        if col in df_reindexed.columns:
            df_reindexed[col] = df_reindexed[col].ffill().bfill()

    df_reindexed["close_clean"] = df_reindexed["close_clean"].fillna(
        df_reindexed["price"]
    )
    df_reindexed.loc[df_reindexed.index < pool_genesis, "is_filled"] = True
    for col in ["price", "close_clean"]:
        if col in df_reindexed.columns and (
            df_reindexed[col].isna().any() or (df_reindexed[col] <= 0).any()
        ):
            raise ValueError(f"Không thể tạo chuỗi giá dương, đầy đủ ở cột '{col}'.")

    # Flow variables (Volume, Fees, txCount) đặt bằng 0 khi không có hoạt động
    zero_fill_cols = ["volumeUSD", "feesUSD", "volumeToken0", "volumeToken1", "txCount"]
    for col in zero_fill_cols:
        if col in df_reindexed.columns:
            df_reindexed[col] = df_reindexed[col].fillna(0.0)

    df_reindexed = df_reindexed.reset_index()
    return df_reindexed


def flag_outliers(
    df_pool: pd.DataFrame,
    df_ref: Optional[pd.DataFrame],
    max_deviation: float = 0.15
) -> pd.DataFrame:
    """
    Gắn cờ outlier nếu giá pool lệch quá max_deviation so với giá nến Binance tham chiếu.
    Không xóa dòng dữ liệu, chỉ gắn nhãn để phục vụ nghiên cứu và regression.
    """
    df_pool["is_outlier"] = False
    if df_ref is None or df_ref.empty:
        return df_pool

    # Merge với giá tham chiếu theo timestamp
    merged = pd.merge(
        df_pool[["datetime", "price"]],
        df_ref[["datetime", "close"]].rename(columns={"close": "ref_price"}),
        on="datetime",
        how="left"
    )

    deviation = np.abs(merged["price"] - merged["ref_price"]) / merged["ref_price"]
    outlier_mask = deviation > max_deviation
    df_pool["is_outlier"] = outlier_mask.fillna(False).values
    df_pool["price_deviation_ref"] = deviation.values

    return df_pool


def process_clean_pool(
    pool_config: Dict[str, Any],
    start_dt: pd.Timestamp,
    end_dt: pd.Timestamp,
    freq: str = "1h"
) -> pd.DataFrame:
    """Thực thi pipeline làm sạch hoàn chỉnh cho 1 pool."""
    pool_name = pool_config["name"]
    logger.info(f"Đang làm sạch dữ liệu cho {pool_name}...")

    # Đọc dữ liệu Subgraph
    raw_subgraph = load_raw_json(f"data/raw/subgraph/{pool_name}_hourly.json")
    if not raw_subgraph:
        raise ValueError(f"Không có dữ liệu thô cho pool {pool_name}. Hãy chạy fetch_subgraph.py trước.")

    df = pd.DataFrame(raw_subgraph)
    df["datetime"] = pd.to_datetime(df["periodStartUnix"].astype(int), unit="s", utc=True)

    # 1. Chuẩn hóa giá
    df = standardize_pool_price(df, pool_config)

    # 2. Reindex lưới thời gian liên tục
    df = reindex_and_fill_timeline(df, start_dt, end_dt, freq=freq)

    # 3. Đọc dữ liệu Binance tương ứng để đối chiếu (nếu có)
    ref_file = "data/raw/prices/ETHUSDT_1h.json" if "WETH" in pool_name else "data/raw/prices/USDCUSDT_1h.json"
    raw_ref = load_raw_json(ref_file)
    df_ref = None
    if raw_ref:
        df_ref = pd.DataFrame(raw_ref)
        df_ref["datetime"] = pd.to_datetime(df_ref["open_time"] / 1000, unit="s", utc=True)

    # 4. Gắn cờ Outlier
    df = flag_outliers(df, df_ref)
    df["pool_name"] = pool_name
    df["fee_tier"] = pool_config["fee_tier"]

    return df


def run_clean_pipeline():
    """Hàm chạy chính lưu kết quả trung gian vào data/interim/."""
    config = load_config()
    start_dt = pd.to_datetime(config["timeframe"]["start_date"])
    end_dt = pd.to_datetime(config["timeframe"]["end_date"])

    out_dir = Path("data/interim")
    out_dir.mkdir(parents=True, exist_ok=True)

    for pool in config["pools"]:
        df_clean = process_clean_pool(pool, start_dt, end_dt)
        dest_path = out_dir / f"{pool['name']}_clean.parquet"
        df_clean.to_parquet(dest_path, index=False)
        logger.info(f"Đã lưu dữ liệu làm sạch tại {dest_path} ({len(df_clean)} dòng)")


if __name__ == "__main__":
    run_clean_pipeline()
