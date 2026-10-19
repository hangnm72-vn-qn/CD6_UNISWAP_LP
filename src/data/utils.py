import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
import requests
import yaml
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Load biến môi trường từ .env
load_dotenv()

# Thiết lập logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("DataEngineUtils")


def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    """Tải và parse file cấu hình YAML."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file cấu hình tại {config_path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_subgraph_url(config: Dict[str, Any]) -> str:
    """Xây dựng GraphQL endpoint URL với API Key từ biến môi trường."""
    api_key = os.getenv("GRAPH_API_KEY")
    if not api_key:
        raise ValueError("Biến môi trường GRAPH_API_KEY chưa được thiết lập trong file .env.")

    subgraph_id = config["endpoints"]["thegraph_subgraph_id"]
    base_url = config["endpoints"]["thegraph_gateway_url"]
    return base_url.format(api_key=api_key, subgraph_id=subgraph_id)


class NetworkClient:
    """HTTP Client có tích hợp Retry, Exponential Backoff và Timeout."""
    def __init__(self, timeout: int = 25):
        self.session = requests.Session()
        self.timeout = timeout

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=30),
        retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.HTTPError)),
        reraise=True,
    )
    def post_graphql(self, url: str, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Thực thi truy vấn GraphQL có retry khi gặp lỗi mạng/rate limit."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        response = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)

        if response.status_code == 429:
            logger.warning("Gặp lỗi Rate Limit (429). Đang chờ trước khi retry...")
            response.raise_for_status()

        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            raise RuntimeError(f"GraphQL Query Error: {data['errors']}")
        return data.get("data", {})

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        reraise=True,
    )
    def get_rest(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Gọi API REST endpoint."""
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()


def save_raw_cache(data: Any, filepath: str) -> None:
    """Lưu dữ liệu thô vào thư mục data/raw/ để phục vụ tái lập và kiểm tra."""
    dest = Path(filepath)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Đã lưu raw cache tại: {filepath}")
