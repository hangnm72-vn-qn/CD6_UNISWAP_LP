import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

# Đảm bảo import đúng utils từ src
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

from src.data.utils import load_config, NetworkClient, save_raw_cache, logger


def fetch_etherscan_daily_gas(client: NetworkClient, api_url: str, api_key: str, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
    """
    Tải dữ liệu gas price lịch sử trung bình theo ngày từ Etherscan Gas Tracker API.
    Action: 'gasoracle' hoặc 'dailyavggasprice'.
    """
    logger.info("Đang gọi Etherscan API lấy dữ liệu Daily Average Gas Price...")
    params = {
        "module": "stats",
        "action": "dailyavggasprice",
        "startdate": start_dt.strftime("%Y-%m-%d"),
        "enddate": end_dt.strftime("%Y-%m-%d"),
        "sort": "asc",
        "apikey": api_key,
    }

    try:
        response = client.get_rest(api_url, params=params)
        if response.get("status") == "1" and "result" in response:
            results = response["result"]
            records = []
            for row in results:
                # Etherscan trả về gasPrice dạng Wei
                records.append({
                    "date": row.get("UTCDate"),
                    "timestamp": int(row.get("unixTimeStamp", 0)),
                    "avg_gas_price_wei": float(row.get("avgGasPrice_Wei", 0.0)),
                    "avg_gas_price_gwei": float(row.get("avgGasPrice_Wei", 0.0)) / 1e9,
                })
            logger.info(f"Đã tải {len(records)} mốc gas từ Etherscan.")
            return records
        else:
            logger.warning(f"Etherscan message: {response.get('message', 'Unknown error')}")
            return []
    except Exception as e:
        logger.warning(f"Không thể lấy gas từ Etherscan: {e}. Chuyển sang fallback.")
        return []


def generate_fallback_gas_series(start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
    """
    Cơ chế dự phòng: Tạo khung chuỗi giờ chuẩn nếu chưa cấu hình ETHERSCAN_API_KEY.
    Sử dụng baseline gas price trung bình 20-30 Gwei (đặc trưng sau EIP-1559/The Merge).
    """
    logger.info("Tạo fallback baseline gas series (25 Gwei benchmark)...")
    date_range = pd.date_range(start=start_dt, end=end_dt, freq="1h", tz="UTC")
    records = []
    for dt in date_range:
        records.append({
            "timestamp": int(dt.timestamp()),
            "datetime_utc": dt.isoformat(),
            "avg_gas_price_gwei": 25.0, # Baseline trung bình cho simulation
        })
    return records


def run_gas_pipeline():
    """Chạy quy trình cào Gas Price."""
    config = load_config()
    client = NetworkClient()
    api_url = config["endpoints"]["etherscan_api_url"]
    api_key = os.getenv("ETHERSCAN_API_KEY", "")

    start_dt = datetime.fromisoformat(config["timeframe"]["start_date"].replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(config["timeframe"]["end_date"].replace("Z", "+00:00"))

    records = []
    if api_key:
        records = fetch_etherscan_daily_gas(client, api_url, api_key, start_dt, end_dt)

    if not records:
        records = generate_fallback_gas_series(start_dt, end_dt)

    save_raw_cache(records, "data/raw/gas/ethereum_gas_history.json")
    logger.info("Hoàn tất lưu dữ liệu Gas.")


if __name__ == "__main__":
    run_gas_pipeline()