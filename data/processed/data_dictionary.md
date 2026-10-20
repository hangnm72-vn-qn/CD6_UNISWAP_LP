# Data Dictionary & Source Log: Uniswap v3 Liquidity Provider Analytics

## 1. Source Log
- **Uniswap v3 Subgraph**: The Graph Network Gateway (Endpoint chính thức của Uniswap Labs trên Ethereum Mainnet). Cung cấp dữ liệu OHLC, sqrtPrice, tick, liquidity, feesUSD, volumeUSD, tvlUSD.
- **Binance REST API**: Nguồn giá tham chiếu off-chain (ETHUSDT, BTCUSDT, USDCUSDT) để đối chiếu chéo sai lệch giá (*arbitrage gap*) và kiểm định ngoại lai (*outlier detection*).
- **DefiLlama API**: Chuỗi TVL lịch sử của giao thức Uniswap v3 để kiểm chứng tính bền vững của thanh khoản. Dữ liệu ngày D được áp dụng cho ngày D+1 để loại bỏ hoàn toàn *look-ahead bias*.
- **Etherscan Gas Tracker**: Dữ liệu lịch sử gas price (Gwei) dùng để tính toán chi phí rebalance vị thế LP quy USD.

---

## 2. Trường dữ liệu trong bảng Processed (`data/processed/`)

| Tên cột | Kiểu dữ liệu | Đơn vị | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| `datetime` | `datetime64[ns, UTC]` | Timestamp UTC | Mốc thời gian bắt đầu của nến giờ (point-in-time). |
| `pool_name` | `string` | Categorical | Tên định danh pool (ví dụ: `WETH-USDC-005`). |
| `fee_tier` | `int64` | bps / 100 | Fee tier của pool (100 = 0.01%, 500 = 0.05%). |
| `tick` | `float64` | Integer index | Vị trí tick hiện tại của pool ($P = 1.0001^{\text{tick}}$). |
| `sqrtPrice` | `float64` | Q64.96 | Giá căn bậc hai định dạng Q64.96 từ smart contract. |
| `price` | `float64` | Quote Asset | Giá giao ngay chuẩn hóa theo quy ước `price_quote`. |
| `open_clean` | `float64` | Quote Asset | Giá mở cửa nến giờ chuẩn hóa. |
| `high_clean` | `float64` | Quote Asset | Giá cao nhất nến giờ chuẩn hóa. |
| `low_clean` | `float64` | Quote Asset | Giá thấp nhất nến giờ chuẩn hóa. |
| `close_clean` | `float64` | Quote Asset | Giá đóng cửa nến giờ chuẩn hóa. |
| `volumeUSD` | `float64` | USD | Tổng khối lượng swap trong 1 giờ. |
| `feesUSD` | `float64` | USD | Tổng phí thu về trong 1 giờ. |
| `tvlUSD` | `float64` | USD | Tổng giá trị khóa (TVL) ghi nhận tại pool. |
| `txCount` | `float64` | Số lượng | Số lượng giao dịch swap phát sinh trong giờ. |
| `is_filled` | `bool` | True/False | Đánh dấu nến không có swap (được ffill giá, volume = 0). |
| `is_outlier` | `bool` | True/False | Đánh dấu giá pool lệch > 15% so với benchmark Binance. |
| `log_return` | `float64` | Tỷ lệ | $\ln(P_t / P_{t-1})$. |
| `vol_hist_24h` | `float64` | Thường hóa năm | Độ biến động lịch sử rolling 24 giờ ($\times \sqrt{8760}$). |
| `vol_hist_168h` | `float64` | Thường hóa năm | Độ biến động lịch sử rolling 7 ngày. |
| `vol_hist_720h` | `float64` | Thường hóa năm | Độ biến động lịch sử rolling 30 ngày. |
| `vol_parkinson_24h`| `float64` | Thường hóa năm | Parkinson Range-based Volatility tính từ High và Low. |
| `vol_garch_forecast`| `float64` | Thường hóa năm | Dự báo $\sigma_{t+1}$ từ GARCH(1,1) Daily Refit (không look-ahead). |
| `volume_turnover` | `float64` | Tỷ số | $\text{volumeUSD} / \text{tvlUSD}$. |
| `fee_yield` | `float64` | Tỷ số | $\text{feesUSD} / \text{tvlUSD}$ (tỷ suất sinh lời từ phí). |
| `volume_log_change`| `float64` | Tỷ lệ | Biến động tương đối của Volume. |
| `tvl_log_change` | `float64` | Tỷ lệ | Biến động tương đối của TVL. |
| `avg_gas_price_gwei`| `float64`| Gwei | Gas price trung bình mạng Ethereum tại thời điểm $t$. |
| `cost_rebalance_usd`| `float64`| USD | Chi phí ước tính cho 1 lần rebalance vị thế LP (300,000 gas units). |
| `defillama_protocol_tvl_usd`| `float64` | USD | TVL Uniswap v3 từ DefiLlama (point-in-time từ ngày D-1). |