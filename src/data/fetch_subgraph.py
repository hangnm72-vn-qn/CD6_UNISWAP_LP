import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

# Đảm bảo đường dẫn import đúng module trong src
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

from src.data.utils import load_config, get_subgraph_url, NetworkClient, save_raw_cache, logger

SUBGRAPH_PAGE_SIZE = 1000

# GraphQL Query lấy dữ liệu nến giờ theo mốc thời gian tăng dần
HOURLY_DATA_QUERY = """
query GetPoolHourData($poolAddress: String!, $startTime: Int!, $first: Int!) {
  poolHourDatas(
    first: $first
    where: { pool: $poolAddress, periodStartUnix_gt: $startTime }
    orderBy: periodStartUnix
    orderDirection: asc
  ) {
    id
    periodStartUnix
    tick
    sqrtPrice
    token0Price
    token1Price
    feesUSD
    tvlUSD
    volumeUSD
    volumeToken0
    volumeToken1
    txCount
    open
    high
    low
    close
  }
}
"""

# GraphQL Query lấy dữ liệu nến ngày
DAILY_DATA_QUERY = """
query GetPoolDayData($poolAddress: String!, $startTime: Int!, $first: Int!) {
  poolDayDatas(
    first: $first
    where: { pool: $poolAddress, date_gt: $startTime }
    orderBy: date
    orderDirection: asc
  ) {
    id
    date
    tick
    sqrtPrice
    token0Price
    token1Price
    feesUSD
    tvlUSD
    volumeUSD
    volumeToken0
    volumeToken1
    txCount
    open
    high
    low
    close
  }
}
"""


def fetch_pool_data_paginated(
    client: NetworkClient,
    subgraph_url: str,
    query: str,
    pool_address: str,
    start_timestamp: int,
    end_timestamp: int,
    data_key: str,
    time_field: str,
) -> List[Dict[str, Any]]:
    """Cào toàn bộ lịch sử nến bằng kỹ thuật cursor-based pagination qua timestamp."""
    all_records = []
    current_start = start_timestamp

    logger.info(f"Bắt đầu tải {data_key} cho pool {pool_address} từ unix {start_timestamp}...")

    while True:
        variables = {
            "poolAddress": pool_address.lower(),
            "startTime": current_start,
            "first": SUBGRAPH_PAGE_SIZE,
        }
        
        response_data = client.post_graphql(subgraph_url, query, variables)
        records = response_data.get(data_key, [])

        if not records:
            break

        all_records.extend(records)
        last_timestamp = int(records[-1][time_field])
        current_start = last_timestamp

        logger.info(f"Đã tải {len(records)} dòng | Mốc hiện tại: {datetime.utcfromtimestamp(last_timestamp)} UTC")

        # Dừng nếu đã vượt quá thời gian kết thúc hoặc trang trả về chưa đầy
        if last_timestamp >= end_timestamp or len(records) < SUBGRAPH_PAGE_SIZE:
            break

        time.sleep(0.15)  # Tránh nghẽn request

    # Lọc lại chính xác trong khung [start_timestamp, end_timestamp]
    filtered_records = [
        r for r in all_records
        if start_timestamp <= int(r[time_field]) <= end_timestamp
    ]
    return filtered_records


def run_subgraph_pipeline():
    """Hàm chạy chính để tải các pool đã cấu hình và lưu cache thô."""
    config = load_config()
    subgraph_url = get_subgraph_url(config)
    client = NetworkClient()

    start_dt = datetime.fromisoformat(config["timeframe"]["start_date"].replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(config["timeframe"]["end_date"].replace("Z", "+00:00"))
    start_unix = int(start_dt.timestamp())
    end_unix = int(end_dt.timestamp())

    for pool in config["pools"]:
        pool_name = pool["name"]
        pool_address = pool["address"]
        logger.info(f"=== Đang xử lý Pool: {pool_name} ({pool_address}) ===")

        # 1. Cào dữ liệu theo giờ
        hourly_records = fetch_pool_data_paginated(
            client=client,
            subgraph_url=subgraph_url,
            query=HOURLY_DATA_QUERY,
            pool_address=pool_address,
            start_timestamp=start_unix,
            end_timestamp=end_unix,
            data_key="poolHourDatas",
            time_field="periodStartUnix",
        )
        save_raw_cache(hourly_records, f"data/raw/subgraph/{pool_name}_hourly.json")

        # 2. Cào dữ liệu theo ngày
        daily_records = fetch_pool_data_paginated(
            client=client,
            subgraph_url=subgraph_url,
            query=DAILY_DATA_QUERY,
            pool_address=pool_address,
            start_timestamp=start_unix,
            end_timestamp=end_unix,
            data_key="poolDayDatas",
            time_field="date",
        )
        save_raw_cache(daily_records, f"data/raw/subgraph/{pool_name}_daily.json")

    logger.info("Hoàn thành cào dữ liệu Subgraph cho tất cả các pools.")


if __name__ == "__main__":
    run_subgraph_pipeline()