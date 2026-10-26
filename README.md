# 🦄 CD6_UNISWAP_LP: Uniswap v3 Quantitative Research & LP Optimizer

Đánh giá hiệu quả cung cấp thanh khoản tập trung và tối ưu vùng giá trên Uniswap v3.

> 🌐 **Trải nghiệm Demo trực tuyến:** [Uniswap v3 LP Optimizer Dashboard](https://cd6uniswaplp-amjoduvffdbhvrz5tjaq9i.streamlit.app)  
> *Lưu ý: Đây là công cụ mô phỏng nghiên cứu (Research Simulator), không phải là khuyến nghị hay lời khuyên đầu tư tài chính.*

---

## Uniswap v3 LP Optimizer — Data Pipeline

Dự án thu thập, chuẩn hóa và tạo bộ dữ liệu chuỗi thời gian phục vụ phân tích pool thanh khoản Uniswap v3 trên Ethereum Mainnet. Dữ liệu đầu ra kết hợp hoạt động của pool, giá tham chiếu, gas và TVL giao thức; đồng thời bổ sung các đặc trưng biến động, thanh khoản và chi phí tái cân bằng.

## 1. Những phần đã triển khai

- Thu thập nến theo giờ/ngày của các pool Uniswap v3 qua The Graph Subgraph.
- Tải giá OHLCV tham chiếu từ Binance cho ETHUSDT, BTCUSDT và USDCUSDT.
- Tải lịch sử TVL Uniswap v3 từ DefiLlama và gas Ethereum từ Etherscan.
- Lưu dữ liệu gốc dạng JSON để có thể kiểm tra và chạy lại bước xử lý mà không cần gọi API.
- Chuẩn hóa chiều giá theo cấu hình token của từng pool; tạo lưới thời gian theo giờ, xử lý nến khuyết và gắn cờ giá ngoại lai.
- Tạo các đặc trưng log return, biến động lịch sử, GARCH, turnover, fee yield, gas price và chi phí rebalance.
- Xuất Parquet riêng cho từng pool, Parquet panel tổng hợp và CSV mẫu để xem nhanh.
- Có script kiểm định dữ liệu đã xử lý và bộ kiểm thử cho tính liên tục, công thức feature và look-ahead bias.

Phạm vi thời gian và bốn pool hiện được cấu hình trong `config/config.yaml`. Dữ liệu được lấy từ `2023-01-01 00:00` đến hết `2026-10-15` (mốc cuối `23:00`), theo UTC; dữ liệu pool-hour được dùng để tạo bộ dữ liệu đã xử lý.

## 2. Kiến trúc và module

Quy trình dữ liệu:

```text
API nguồn
  ├─ The Graph ───────────────────┐
  ├─ Binance ─────────────────────┤
  ├─ DefiLlama ───────────────────┤
  └─ Etherscan (hoặc gas baseline)┘
                 ↓
          data/raw/*.json
                 ↓
       clean.py + features.py
                 ↓
      data/processed/*.parquet
                 ↓
    validate_processed.py / phân tích

```

| Module | Vai trò |
| --- | --- |
| `src/data/utils.py` | Đọc YAML, dựng URL The Graph, gọi REST/GraphQL có timeout và retry, lưu cache JSON. |
| `src/data/fetch_subgraph.py` | Phân trang và tải dữ liệu pool theo giờ/ngày từ The Graph. |
| `src/data/fetch_prices.py` | Tải nến tham chiếu 1 giờ và 1 ngày từ Binance. |
| `src/data/fetch_tvl.py` | Tải chuỗi TVL lịch sử từ DefiLlama. |
| `src/data/fetch_gas.py` | Tải gas price ngày từ Etherscan; nếu không có dữ liệu/API key thì tạo chuỗi baseline 25 Gwei cho pipeline mô phỏng. |
| `src/data/clean.py` | Đọc dữ liệu gốc, chuẩn hóa giá, căn lưới giờ, điền nến khuyết và gắn cờ outlier. |
| `src/data/features.py` | Tính biến động, GARCH, chỉ số thanh khoản và chi phí rebalance. |
| `src/data/build_dataset.py` | Kết nối các bước xử lý, xuất dữ liệu từng pool, panel tổng hợp và CSV preview. |
| `src/data/validate_processed.py` | Kiểm tra schema, timestamp, khoảng trống, giá trị không hợp lệ, missing và phân phối. |
| `src/features/build_features.py` | Chuẩn hóa dữ liệu daily, nhận diện pool và bổ sung volume, log return, volatility cho notebook phân tích. |
| `src/models/optimizer.py` | Công thức tick/liquidity/range của Uniswap v3, fixed-effects OLS và quantile regression. |
| `src/evaluation/backtest.py` | Chạy các chiến lược LP, tính metrics và xuất position ledger/decomposition. |
| `notebooks/tong_hop.ipynb` | Notebook phân tích gọi các module trong `src/`; bảng và biểu đồ được lưu ở `outputs/tables/` và `outputs/figures/` tại thư mục gốc. |
| `tests/` | Kiểm thử pipeline, feature và một số điều kiện chống look-ahead bias. |

TVL DefiLlama được đưa vào dữ liệu từ ngày kế tiếp ngày ghi nhận nhằm tránh dùng thông tin chưa sẵn có tại thời điểm quan sát. Các nến thiếu hoạt động được đánh dấu `is_filled`; giá được giữ theo quan sát trước đó, còn volume/fees được đặt bằng 0. Outlier được đánh dấu chứ không bị xóa.

## 3. Thiết lập cơ bản

Chạy các lệnh dưới đây từ thư mục gốc dự án.

### 3.1. Tạo môi trường và cài dependencies (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

```

Nếu PowerShell không cho phép kích hoạt môi trường, có thể gọi Python trong virtual environment trực tiếp bằng `.\.venv\Scripts\python.exe`.

### 3.2. Cấu hình API key

Tạo file `.env` ở thư mục gốc với nội dung:

```dotenv
GRAPH_API_KEY=your_the_graph_api_key
ETHERSCAN_API_KEY=your_etherscan_api_key

```

`GRAPH_API_KEY` là bắt buộc để chạy bước tải Subgraph. `ETHERSCAN_API_KEY` là tùy chọn; khi không có key hoặc không lấy được dữ liệu gas, pipeline sử dụng baseline gas để tiếp tục. Không đưa API key lên kho mã nguồn hoặc chia sẻ công khai.

### 3.3. Cấu hình dữ liệu

Chỉnh `timeframe`, `pools` và `features` trong `config/config.yaml` trước khi cào dữ liệu. Hãy đảm bảo địa chỉ pool, thứ tự token, decimals và `price_quote` khớp với pool cần nghiên cứu. Các file và lệnh bên dưới dùng đường dẫn tương đối, vì vậy cần chạy từ thư mục gốc dự án.

## 4. Chạy pipeline

### 4.1. Tải dữ liệu gốc

```powershell
python -m src.data.fetch_subgraph
python -m src.data.fetch_prices
python -m src.data.fetch_tvl
python -m src.data.fetch_gas

```

Các script tạo cache trong `data/raw/`. Có thể chạy lại từng lệnh tương ứng để cập nhật cache. Bước dựng dataset bên dưới đọc các file cache này, không tự gọi các API.

### 4.2. Làm sạch, tạo feature và xuất dữ liệu

```powershell
python -m src.data.build_dataset

```

Kết quả được lưu vào `data/processed/`:

* `<pool_name>_processed.parquet`: dữ liệu đã xử lý của từng pool.
* `uniswap_v3_panel_4pools.parquet`: dữ liệu panel gộp các pool.
* `uniswap_v3_sample_preview.csv`: tối đa 500 dòng đầu của panel để xem nhanh.

### 4.3. Kiểm định và kiểm thử

```powershell
python -m src.data.validate_processed
python -m pytest

```

Script kiểm định đọc mọi file `*.parquet` trong `data/processed/`, in báo cáo và trả mã thoát khác 0 nếu kiểm định thất bại. Xem chi tiết các cột và nguồn trong `data/processed/data_dictionary.md`.

### 4.4. Chạy dashboard

```powershell
streamlit run dashboard/app.py

```

Dashboard đọc dữ liệu daily từ `data/processed/pools_daily.csv`, các bảng JSON từ `outputs/tables/` và ảnh notebook từ `outputs/figures/`.

## 5. Đọc và khai thác dữ liệu

Ưu tiên dùng Parquet cho phân tích toàn bộ dữ liệu; CSV preview phù hợp để kiểm tra nhanh.

```python
import pandas as pd

panel = pd.read_parquet("data/processed/uniswap_v3_panel_4pools.parquet")

# Chọn một pool, sắp xếp theo thời gian và xem các biến thường dùng
pool = (
    panel.loc[panel["pool_name"] == "WETH-USDC-005"]
    .sort_values("datetime")
)
print(pool[[
    "datetime",
    "close_clean",
    "volumeUSD",
    "feesUSD",
    "tvlUSD",
    "log_return",
    "vol_hist_24h",
    "vol_garch_forecast",
    "volume_turnover",
    "fee_yield",
    "cost_rebalance_usd",
]].head())