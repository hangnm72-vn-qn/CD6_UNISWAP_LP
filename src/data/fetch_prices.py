import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

# Đảm bảo import đúng utils từ src
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

from src.data.utils import load_config, NetworkClient, save_raw_cache, logger

BINANCE_KLINES_LIMIT = 1000

# Ánh xạ các cặp giao dịch chính cần lấy giá tham chiếu
BINANCE_SYMBOLS = [
    {"symbol": "ETHUSDT", "quote": "USD_per_WETH"},
    {"symbol": "BTCUSDT", "quote": "USD_per_WBTC"},
    {"symbol": "USDCUSDT", "quote": "USDT_per_USDC"},
]


def fetch_binance_klines_paginated(
    client: NetworkClient,
    base_url: str,
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
) -> List[Dict[str, Any]]:
    """
    Cào nến OHLCV từ Binance REST API với cơ chế phân trang theo startTime.
    Khoảng nến trả về tối đa 1000 nến mỗi request.
    """
    records = []
    current_start = start_time_ms

    logger.info(f"Bắt đầu tải nến Binance {interval} cho cặp {symbol}...")

    while True:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": current_start,
            "endTime": end_time_ms,
            "limit": BINANCE_KLINES_LIMIT,
        }

        data = client.get_rest(base_url, params=params)
        if not data:
            break

        for item in data:
            # Cấu trúc Binance Kline: [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...]
            records.append({
                "open_time": int(item[0]),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
                "close_time": int(item[6]),
                "quote_asset_volume": float(item[7]),
                "number_of_trades": int(item[8]),
            })

        last_open_time = int(data[-1][0])
        logger.info(f"[{symbol} - {interval}] Đã tải {len(records)} nến | Đến {datetime.utcfromtimestamp(last_open_time / 1000)} UTC")

        if len(data) < BINANCE_KLINES_LIMIT or last_open_time >= end_time_ms:
            break

        # Tăng startTime lên 1ms sau open_time nến cuối để tránh lặp nến
        current_start = last_open_time + 1
        time.sleep(0.1)

    return records


def run_price_pipeline():
    """Chạy quy trình cào giá tham chiếu theo giờ và ngày."""
    config = load_config()
    client = NetworkClient()
    base_url = config["endpoints"]["binance_klines_url"]

    start_dt = datetime.fromisoformat(config["timeframe"]["start_date"].replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(config["timeframe"]["end_date"].replace("Z", "+00:00"))
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    for item in BINANCE_SYMBOLS:
        symbol = item["symbol"]

        # 1. Tải nến 1 giờ
        hourly_records = fetch_binance_klines_paginated(
            client=client,
            base_url=base_url,
            symbol=symbol,
            interval="1h",
            start_time_ms=start_ms,
            end_time_ms=end_ms,
        )
        save_raw_cache(hourly_records, f"data/raw/prices/{symbol}_1h.json")

        # 2. Tải nến 1 ngày
        daily_records = fetch_binance_klines_paginated(
            client=client,
            base_url=base_url,
            symbol=symbol,
            interval="1d",
            start_time_ms=start_ms,
            end_time_ms=end_ms,
        )
        save_raw_cache(daily_records, f"data/raw/prices/{symbol}_1d.json")

    logger.info("Hoàn tất cào giá tham chiếu từ Binance.")


if __name__ == "__main__":
    run_price_pipeline()