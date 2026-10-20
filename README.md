# Uniswap v3 LP Optimizer — Data Pipeline

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

Phạm vi thời gian và bốn pool hiện được cấu hình trong [`config/config.yaml`](config/config.yaml). Dữ liệu được lấy từ `2023-01-01 00:00` đến hết `2026-10-15` (mốc cuối `23:00`), theo UTC; dữ liệu pool-hour được dùng để tạo bộ dữ liệu đã xử lý.

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
| [`src/data/utils.py`](src/data/utils.py) | Đọc YAML, dựng URL The Graph, gọi REST/GraphQL có timeout và retry, lưu cache JSON. |
| [`src/data/fetch_subgraph.py`](src/data/fetch_subgraph.py) | Phân trang và tải dữ liệu pool theo giờ/ngày từ The Graph. |
| [`src/data/fetch_prices.py`](src/data/fetch_prices.py) | Tải nến tham chiếu 1 giờ và 1 ngày từ Binance. |
| [`src/data/fetch_tvl.py`](src/data/fetch_tvl.py) | Tải chuỗi TVL lịch sử từ DefiLlama. |
| [`src/data/fetch_gas.py`](src/data/fetch_gas.py) | Tải gas price ngày từ Etherscan; nếu không có dữ liệu/API key thì tạo chuỗi baseline 25 Gwei cho pipeline mô phỏng. |
| [`src/data/clean.py`](src/data/clean.py) | Đọc dữ liệu gốc, chuẩn hóa giá, căn lưới giờ, điền nến khuyết và gắn cờ outlier. |
| [`src/data/features.py`](src/data/features.py) | Tính biến động, GARCH, chỉ số thanh khoản và chi phí rebalance. |
| [`src/data/build_dataset.py`](src/data/build_dataset.py) | Kết nối các bước xử lý, xuất dữ liệu từng pool, panel tổng hợp và CSV preview. |
| [`src/data/export_requested_csv.py`](src/data/export_requested_csv.py) | Xuất CSV daily tổng hợp và CSV hourly lấy mẫu từ panel đã xử lý. |
| [`src/data/validate_processed.py`](src/data/validate_processed.py) | Kiểm tra schema, timestamp, khoảng trống, giá trị không hợp lệ, missing và phân phối. |
| [`tests/`](tests/) | Kiểm thử pipeline, feature và một số điều kiện chống look-ahead bias. |

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

Chỉnh `timeframe`, `pools` và `features` trong [`config/config.yaml`](config/config.yaml) trước khi cào dữ liệu. Hãy đảm bảo địa chỉ pool, thứ tự token, decimals và `price_quote` khớp với pool cần nghiên cứu. Các file và lệnh bên dưới dùng đường dẫn tương đối, vì vậy cần chạy từ thư mục gốc dự án.

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

- `<pool_name>_processed.parquet`: dữ liệu đã xử lý của từng pool.
- `uniswap_v3_panel_4pools.parquet`: dữ liệu panel gộp các pool.
- `uniswap_v3_sample_preview.csv`: tối đa 500 dòng đầu của panel để xem nhanh. Nếu file đang bị khóa, chương trình ghi preview sang tên có timestamp.

### 4.3. Xuất hai file CSV phục vụ phân tích

Sau khi có `uniswap_v3_panel_4pools.parquet`, chạy:

```powershell
python -m src.data.export_requested_csv
```

Lệnh tạo:

- `data/processed/pools_daily.csv`: tổng hợp từ dữ liệu hourly theo ngày và pool. OHLC lấy lần lượt giá mở đầu ngày, giá cao nhất, thấp nhất và giá đóng cuối ngày; volume, fees và số giao dịch được cộng; TVL lấy giá trị cuối ngày. `hours_observed` và `is_complete_day` cho biết ngày có đủ 24 giờ dữ liệu hay không. Đây là dữ liệu daily được tổng hợp từ hourly, không phải bản sao trực tiếp của `poolDayDatas` từ Subgraph.
- `data/processed/pools_hourly_subsample.csv`: lấy các dòng có giờ UTC là 00:00, 06:00, 12:00 hoặc 18:00 cho từng pool.

Script lọc theo khoảng thời gian trong `config/config.yaml`. Nếu vừa thay đổi khoảng ngày hoặc cần dữ liệu mới hơn, hãy chạy lại các bước tải nguồn và `python -m src.data.build_dataset` trước khi export. Nếu đưa CSV lên GitHub, kiểm tra quy tắc `.gitignore`; có thể stage riêng hai file này bằng `git add -f data/processed/pools_daily.csv data/processed/pools_hourly_subsample.csv`.

### 4.4. Kiểm định và kiểm thử

```powershell
python -m src.data.validate_processed
python -m pytest
```

Script kiểm định đọc mọi file `*.parquet` trong `data/processed/`, in báo cáo và trả mã thoát khác 0 nếu kiểm định thất bại. Khoảng trống thời gian lớn hơn một giờ và tỷ lệ missing cao được báo cảnh báo; xem chi tiết các cột và nguồn trong [`data/processed/data_dictionary.md`](data/processed/data_dictionary.md).

## 5. Đọc và khai thác dữ liệu

Ưu tiên dùng Parquet cho phân tích toàn bộ dữ liệu; CSV preview phù hợp để kiểm tra nhanh. Cần cài dependencies của dự án trước khi đọc Parquet.

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
```

Một số gợi ý:

- Dùng `pool_name` để lọc pool; `datetime` là timestamp UTC, theo lưới giờ.
- Dùng `close_clean` làm chuỗi giá đã chuẩn hóa; `is_filled` cho biết quan sát là nến được điền; `is_outlier` đánh dấu chênh lệch giá vượt ngưỡng tham chiếu.
- Dùng `volumeUSD`, `feesUSD`, `tvlUSD`, `volume_turnover` và `fee_yield` để khảo sát hoạt động/thanh khoản.
- Dùng `log_return`, `vol_hist_24h`/`168h`/`720h`, `vol_parkinson_24h` và `vol_garch_forecast` để phân tích biến động.
- Dùng `avg_gas_price_gwei` và `cost_rebalance_usd` để xem chi phí gas ước tính. Nếu pipeline dùng gas baseline, cần ghi rõ đây là dữ liệu mô phỏng, không phải gas lịch sử thực tế.
- Dùng `defillama_protocol_tvl_usd` như chỉ báo TVL giao thức; giá trị được căn thời điểm sẵn có theo ngày và có thể không trùng chính xác với TVL của từng pool.

Danh sách đầy đủ trường dữ liệu, đơn vị và mô tả nằm trong [`data/processed/data_dictionary.md`](data/processed/data_dictionary.md).
