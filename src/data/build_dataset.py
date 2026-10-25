import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

# Đảm bảo import đúng utils từ src
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

from src.data.utils import load_config, logger
from src.data.clean import process_clean_pool
from src.data.features import generate_pool_features


def load_gas_data(filepath: str = "data/raw/gas/ethereum_gas_history.json") -> Optional[pd.DataFrame]:
    """Tải và chuẩn hóa chuỗi Gas Price."""
    path = Path(filepath)
    if not path.exists():
        logger.warning(f"Chưa có file gas tại {filepath}. Sử dụng baseline gas.")
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        return None
    df = pd.DataFrame(data)
    if "timestamp" in df.columns:
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    elif "date" in df.columns:
        df["datetime"] = pd.to_datetime(df["date"], utc=True)
    return df


def load_eth_price_data(filepath: str = "data/raw/prices/ETHUSDT_1h.json") -> Optional[pd.DataFrame]:
    """Load hourly ETH/USDT closes for USD gas-cost conversion."""
    path = Path(filepath)
    if not path.exists():
        logger.warning(f"Chưa có file giá ETH tại {filepath}. Sử dụng baseline 3000 USD.")
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        logger.warning(f"File giá ETH rỗng tại {filepath}. Sử dụng baseline 3000 USD.")
        return None
    df = pd.DataFrame(data)
    if "open_time" not in df.columns or "close" not in df.columns:
        raise ValueError(f"File giá ETH không có open_time/close: {filepath}")
    df["datetime"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df[["datetime", "close"]]


def load_defillama_tvl(filepath: str = "data/raw/defillama/uniswap_v3_ethereum_tvl.json") -> Optional[pd.DataFrame]:
    """
    Tải TVL từ DefiLlama và shift lùi 1 ngày (+1 day) để chống look-ahead bias.
    TVL ngày D chỉ được dùng cho các quan sát từ ngày D+1 trở đi.
    """
    path = Path(filepath)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        return None
    df = pd.DataFrame(data)
    # Timestamp của DefiLlama là 00:00 UTC của ngày ghi nhận
    df["datetime"] = pd.to_datetime(df["date"], unit="s", utc=True)
    # Dịch chuyển 1 ngày để đảm bảo tính point-in-time
    df["datetime_available"] = df["datetime"] + pd.Timedelta(days=1)
    df = df.rename(columns={"tvl_usd": "defillama_protocol_tvl_usd"})
    return df[["datetime_available", "defillama_protocol_tvl_usd"]]


def merge_defillama_tvl(df_feat: pd.DataFrame, df_defillama: pd.DataFrame) -> pd.DataFrame:
    """As-of join TVL using the same UTC timestamp resolution on both sides."""
    left = df_feat.copy()
    right = df_defillama.copy()
    timestamp_dtype = "datetime64[ns, UTC]"
    left["datetime"] = pd.to_datetime(left["datetime"], utc=True).astype(timestamp_dtype)
    right["datetime_available"] = pd.to_datetime(
        right["datetime_available"], utc=True
    ).astype(timestamp_dtype)

    merged = pd.merge_asof(
        left.sort_values("datetime"),
        right.sort_values("datetime_available"),
        left_on="datetime",
        right_on="datetime_available",
        direction="backward"
    )
    return merged.drop(columns=["datetime_available"], errors="ignore")


def save_sample_preview(panel_df: pd.DataFrame, sample_csv_path: Path) -> Path:
    """Write the preview, using a unique file if the standard path is locked."""
    sample = panel_df.head(500)
    try:
        sample.to_csv(sample_csv_path, index=False)
        return sample_csv_path
    except PermissionError as exc:
        timestamp = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%S%fZ")
        fallback_path = sample_csv_path.with_name(
            f"{sample_csv_path.stem}_{timestamp}{sample_csv_path.suffix}"
        )
        logger.warning(
            f"Không thể ghi đè file preview {sample_csv_path} (có thể đang mở). "
            f"Thử ghi sang {fallback_path}: {exc}"
        )
        sample.to_csv(fallback_path, index=False)
        return fallback_path


def build_all_pools_dataset():
    """Chạy quy trình hợp nhất và xuất dữ liệu sang data/processed/."""
    config = load_config()
    start_dt = pd.to_datetime(config["timeframe"]["start_date"])
    end_dt = pd.to_datetime(config["timeframe"]["end_date"])

    processed_dir = Path("data/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)

    # 1. Đọc Gas data
    df_gas = load_gas_data()

    # 2. Đọc ETH/USD để quy đổi gas cho các pool không có giá ETH/USD.
    df_eth_prices = load_eth_price_data()

    # 3. Đọc DefiLlama TVL data
    df_defillama = load_defillama_tvl()

    combined_pools = []

    for pool in config["pools"]:
        pool_name = pool["name"]
        logger.info(f"--- Đang build dataset cho pool: {pool_name} ---")

        # Làm sạch cơ bản
        df_clean = process_clean_pool(pool, start_dt, end_dt)

        # Tạo Features (Vol, GARCH, Liquidity, Gas Rebalance Cost)
        df_feat = generate_pool_features(
            df_clean, df_gas=df_gas, df_eth_prices=df_eth_prices
        )

        # Gộp DefiLlama TVL (as-of join theo datetime_available)
        if df_defillama is not None and not df_defillama.empty:
            df_feat = merge_defillama_tvl(df_feat, df_defillama)

        # Xuất file Parquet riêng lẻ cho từng pool
        pool_parquet_path = processed_dir / f"{pool_name}_processed.parquet"
        df_feat.to_parquet(pool_parquet_path, index=False)
        logger.info(f"Đã lưu pool dataset tại: {pool_parquet_path}")

        combined_pools.append(df_feat)

    # 3. Tạo Panel Dataset tổng hợp cho Regression (theo Mục 2.5 của đề bài)
    if combined_pools:
        panel_df = pd.concat(combined_pools, ignore_index=True)
        panel_df = panel_df.sort_values(
            by=["pool_name", "datetime"]
        ).reset_index(drop=True)
        panel_parquet_path = processed_dir / "uniswap_v3_panel_4pools.parquet"
        panel_df.to_parquet(panel_parquet_path, index=False)
        
        # Xuất file mẫu CSV nhỏ cho kiểm tra nhanh
        sample_csv_path = processed_dir / "uniswap_v3_sample_preview.csv"
        saved_preview_path = save_sample_preview(panel_df, sample_csv_path)
        logger.info(f"Đã lưu file mẫu CSV tại: {saved_preview_path}")
        logger.info(f"Đã lưu Panel Dataset tổng hợp tại: {panel_parquet_path}")

    logger.info("Hoàn thành toàn bộ pipeline xử lý dữ liệu!")


if __name__ == "__main__":
    build_all_pools_dataset()