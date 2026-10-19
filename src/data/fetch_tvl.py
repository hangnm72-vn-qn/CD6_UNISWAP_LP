import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Đảm bảo import đúng utils từ src
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

from src.data.utils import load_config, NetworkClient, save_raw_cache, logger


def fetch_defillama_protocol_tvl(client: NetworkClient, url: str) -> List[Dict[str, Any]]:
    """Tải chuỗi TVL lịch sử của giao thức Uniswap v3 trên DefiLlama."""
    logger.info("Đang gọi DefiLlama API để lấy lịch sử TVL Uniswap v3...")
    data = client.get_rest(url)

    # DefiLlama trả về dict chứa tvl theo chain
    tvl_series = data.get("tvl", [])
    chain_tvls = data.get("chainTvls", {})
    ethereum_tvl = chain_tvls.get("Ethereum", {}).get("tvl", [])

    records = []
    # Ưu tiên lấy TVL riêng của Ethereum chain để khớp với mainnet pool
    target_series = ethereum_tvl if ethereum_tvl else tvl_series

    for item in target_series:
        records.append({
            "date": int(item.get("date", 0)),
            "tvl_usd": float(item.get("totalLiquidityUSD", 0.0)),
        })

    logger.info(f"Đã tải thành công {len(records)} mốc TVL từ DefiLlama.")
    return records


def run_tvl_pipeline():
    """Chạy quy trình cào TVL và lưu cache thô."""
    config = load_config()
    client = NetworkClient()
    url = config["endpoints"]["defillama_protocol_url"]

    records = fetch_defillama_protocol_tvl(client, url)
    save_raw_cache(records, "data/raw/defillama/uniswap_v3_ethereum_tvl.json")
    logger.info("Hoàn tất lưu cache TVL từ DefiLlama.")


if __name__ == "__main__":
    run_tvl_pipeline()
