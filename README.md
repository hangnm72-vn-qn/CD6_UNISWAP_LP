# CD6_UNISWAP_LP
Đánh giá hiệu quả cung cấp thanh khoản tập trung và tối ưu vùng giá trên Uniswap v3
---

## 1. Xác định vấn đề nghiên cứu 

### 1.1. Thực trạng cung cấp thanh khoản tập trung trên Uniswap v3
Sự ra đời của cơ chế Nhà tạo lập thị trường tự động thanh khoản tập trung (Concentrated Liquidity Automated Market Maker - CLMM) trên Uniswap v3 đã tạo nên bước ngoặt cấu trúc trong tài chính phi tập trung. Khác với mô hình CPMM ($x \cdot y = k$) truyền thống của Uniswap v2 phân bổ vốn trên toàn dải giá $(0, \infty)$, Uniswap v3 cProvidercung cấp thanh khoản (Liquidity Provider - LP) tập trung vốn trong một dải giá hữu hạn $[P_L, P_U]$.

Mặc dù hiệu quả sử dụng vốn danh nghĩa có thể tăng lên hàng nghìn lần, thực tiễn vận hành bộc lộ nghịch lý lớn:
- Phần lớn LP cá nhân ghi nhận **lợi nhuận ròng âm** so với chiến lược thụ động nắm giữ (HODL), do phí thu được không bù đắp nổi tổn thất tạm thời (Impermanent Loss - IL) khuếch đại và chi phí tái cân bằng.
- Cạnh tranh bất đối xứng: Các nhà tạo lập thị trường chuyên nghiệp (JIT - Just-In-Time liquidity bots, MEV searchers) liên tục rút/bơm thanh khoản xung quanh các giao dịch lớn, chèn ép lợi nhuận của các LP thụ động.

### 1.2. Khi nào LP có lợi hơn HODL?
Một vị thế LP $i$ vượt trội hơn chiến lược HODL cùng danh mục tài sản cơ sở khi và chỉ khi phần thặng dư hiệu năng (Excess Return) dương:

$$\Delta R_i = R^{LP}_i - R^{HODL}_i > 0$$

Điều này đòi hỏi tổng phí giao dịch thu được ($Fees_i$) phải bù đắp được 3 thành tố suy giảm giá trị:
1. **Impermanent Loss khuếch đại ($IL_i$):** Phát sinh từ chênh lệch giá so với thời điểm mở vị thế.
2. **Chi phí Gas mạng lưới ($Gas_i$):** Phí mint, burn và collect fee trên Layer-1/Layer-2.
3. **Chi phí trượt giá & Rebalance ($RebalancingCost_i$):** Tổn thất khi tái cơ cấu dải giá khi giá thị trường lệch khỏi $[P_L, P_U]$.

LP chỉ có lợi hơn HODL trong các điều kiện thị trường biên:
- Tài sản dao động tích lũy trong một dải biến động xác định với khối lượng giao dịch cao ($Volume / TVL$ cao).
- Biến động thực tế thấp hơn mức biến động hàm ý được định giá qua phí pool.

### 1.3. Trade-off tứ giác cốt lõi 
LP trên Uniswap v3 luôn đối mặt với bài toán tối ưu đa biến giữa 4 yếu tố xung đột:

```
                  [Fee Income (Thu nhập phí)]
                            ▲
                           / \
                          /   \
                         /     \
   [Out-of-Range Risk] ◄─────────► [Rebalancing & Gas Cost]
                         \     /
                          \   /
                           \ /
                            ▼
              [Impermanent Loss Amplification]
```

1. **Fee Income vs. Out-of-Range Risk:** 
   - Thu hẹp biên độ $[P_L, P_U]$ giúp phóng đại thanh khoản ảo $L$, tối đa hóa tỷ lệ nhận phí giao dịch khi giá nằm trong vùng.
   - Tuy nhiên, biên hẹp làm tăng xác suất giá văng ra ngoài dải, khiến vị thế ngừng tạo ra dòng tiền và rơi vào trạng thái 100% tài sản mất giá.
2. **Out-of-Range Risk vs. Rebalancing & Gas Cost:** 
   - Để khắc phục việc lệch vùng, LP buộc phải tái cân bằng (đóng vị thế cũ, swap cân bằng tài sản, mở vị thế mới).
   - Tần suất tái cân bằng càng cao thì chi phí gas và trượt giá giao dịch càng bào mòn tổng lợi nhuận.
3. **Fee Income vs. Impermanent Loss:** 
   - Đòn bẩy thanh khoản càng cao thì tốc độ hội tụ tài sản về phía đồng tiền giảm giá càng nhanh khi có xu hướng, làm gia tăng tổn thất IL theo cấp số nhân so với Uniswap v2.

---

## 2. Mục tiêu, Phạm vi và Câu hỏi nghiên cứu (RQs)

### 2.1. Mục tiêu nghiên cứu
- **Mục tiêu tổng quát:** Xây dựng cơ sở lý thuyết, mô hình định lượng và công cụ thực nghiệm nhằm giải thích hiệu quả kinh tế của việc cung cấp thanh khoản tập trung trên Uniswap v3; từ đó phát triển thuật toán tối ưu hóa dải giá $[P_L, P_U]$ thích ứng với biến động thị trường.
- **Mục tiêu cụ thể:**
  1. Phân rã cấu trúc lợi nhuận của LP trên dữ liệu thực tế (Fee Income, Impermanent Loss, Rebalancing Cost, Inventory Return).
  2. Đo lường tác động của độ rộng dải giá và các biến số kinh tế vĩ mô của pool (Volatility, Volume, TVL, Fee tier) lên tỷ suất sinh lời điều chỉnh theo rủi ro.
  3. Xây dựng và kiểm định 4 chiến lược dải giá (Wide, Fixed Symmetric, Volatility-Scaled, Dynamic Rolling).
  4. Đóng gói mô hình thành một công cụ định lượng (DeFi LP Optimizer & Interactive Dashboard) triển khai qua GitHub Pages/Streamlit.

### 2.2. Phạm vi nghiên cứu (Scope of Study)

#### Không gian tài sản (Asset Space)
Lựa chọn 4 pool đại diện phản ánh 4 cấu trúc vi mô điển hình:
- **WETH/USDC (Fee 0.05% & 0.3%):** Cặp biến động/ổn định (Volatile/Stable) có thanh khoản và khối lượng dẫn dắt thị trường; cho phép phân tích độ nhạy của Fee Tier.
- **WETH/USDT (Fee 0.3%):** Cặp đối chứng thanh khoản và độ lệch chênh lệch giá.
- **WBTC/WETH (Fee 0.05%):** Cặp tài sản tiền mã hóa tương quan dương cao, biến động giá tương đối thấp hơn cặp Stablecoin.
- **USDC/USDT (Fee 0.01%):** Cặp tiền tệ ổn định, $IL \approx 0$, đóng vai trò Benchmark kiểm chứng mô hình thuần về phí và rủi ro depeg.

#### Khung thời gian và Tần suất dữ liệu
- **Giai đoạn nghiên cứu:** 01/01/2025 – 30/09/2026 (21 tháng liên tục).
- **Tần suất dữ liệu phân tích:**
  - *Tập chính (Baseline - Pool-day):* 21 tháng dữ liệu ngày phục vụ phân tích kinh tế lượng và backtest tổng thể.
  - *Tập bổ trợ (Sub-sample - Pool-hour):* 1–3 tháng gần nhất tần suất giờ dùng cho Robustness check, Stress test và kiểm định tần suất tái cân bằng nội ngày.

---

### 2.3. Hệ thống 5 Câu hỏi nghiên cứu (Research Questions - RQs)

* **RQ1 (Decomposition & Profitability):** Lợi nhuận ròng của LP trên Uniswap v3 có thực sự tạo ra giá trị thặng dư so với chiến lược nắm giữ thụ động (HODL) hay phần lớn fee income thu được bị lấn át hoàn toàn bởi tổn thất tạm thời và chi phí giao dịch?
* **RQ2 (Range Width Dynamics):** Độ rộng của dải giá ($\Delta P = P_U - P_L$) tác động phi tuyến như thế nào đến tỷ suất sinh lời điều chỉnh theo rủi ro của vị thế thanh khoản?
* **RQ3 (Empirical Drivers):** Biến động giá (Realized/GARCH Volatility), Khối lượng giao dịch, Tỷ lệ tập trung vốn và Hạng mức phí giải thích mức độ chênh lệch lợi nhuận ròng ($\Delta R_i$) giữa các pool như thế nào?
* **RQ4 (Static vs. Dynamic Strategy Trade-off):** Các chiến lược dải giá động có duy trì được hiệu quả vượt trội so với các chiến lược dải giá tĩnh sau khi đã hạch toán đầy đủ chi phí trượt giá và phí gas blockchain hay không?
* **RQ5 (Quantitative Optimization):** Liệu có thể xây dựng một thuật toán tối ưu hóa cho phép dự phóng tự động biên độ $[P_L^*, P_U^*]$ tối ưu dựa trên biến động dự báo (GARCH/EWMA) và khối lượng kỳ vọng nhằm cực đại hóa lợi nhuận kỳ vọng có ràng buộc rủi ro?

---

## 3. Cơ sở lý thuyết: Toán học Uniswap v3 và Cơ chế Range Width

### 3.1. Mô hình Thanh khoản tập trung 
Trong Uniswap v2, phương trình cân bằng liên tục là $x \cdot y = k$, với thanh khoản $L = \sqrt{x \cdot y}$ và giá giao ngay $P = y / x$ (với $y$ là token quy ước, ví dụ USDC; $x$ là token cơ sở, ví dụ WETH).

Trong Uniswap v3, thanh khoản thực được dịch chuyển bằng khái niệm **Virtual Reserves (Dự trữ ảo)**. Khi LP cung cấp thanh khoản trong dải $[P_L, P_U]$ với $P_L < P_U$, đường cong cân bằng trở thành:

$$(x + x_{virtual})(y + y_{virtual}) = L^2$$

Trong đó, các đại lượng dự trữ ảo $x_{virtual}$ và $y_{virtual}$ được xác định bởi biên giới hạn:

$$x_{virtual} = \frac{L}{\sqrt{P_U}}, \quad y_{virtual} = L \cdot \sqrt{P_L}$$

Do đó, phương trình trạng thái viết lại theo các tham số biên:

$$\left( x + \frac{L}{\sqrt{P_U}} \right) \left( y + L \sqrt{P_L} \right) = L^2$$

#### Số lượng token thực tế cần ký quỹ ($x, y$) theo mức giá hiện tại $P$
Tùy thuộc vào vị trí của giá hiện tại $P$ so với khoảng $[P_L, P_U]$, lượng token thực tế được chia thành 3 trạng thái:

1. **Khi $P \le P_L$ (Giá nằm dưới dải):** Vị thế bao gồm $100\%$ Token $X$ (tài sản giảm giá):
   $$x = L \left( \frac{1}{\sqrt{P_L}} - \frac{1}{\sqrt{P_U}} \right), \quad y = 0$$

2. **Khi $P_L < P < P_U$ (Giá nằm trong dải kích hoạt):** Vị thế gồm cả 2 token:
   $$x = L \left( \frac{1}{\sqrt{P}} - \frac{1}{\sqrt{P_U}} \right)$$
   $$y = L \left( \sqrt{P} - \sqrt{P_L} \right)$$

3. **Khi $P \ge P_U$ (Giá vượt lên trên dải):** Vị thế chuyển đổi hoàn toàn thành $100\%$ Token $Y$:
   $$x = 0, \quad y = L \left( \sqrt{P_U} - \sqrt{P_L} \right)$$

#### Giá trị vị thế LP ($V_{LP}(P)$)
Định giá vị thế thanh khoản theo đồng tiền định giá $Y$ tại mức giá $P$:

$$V_{LP}(P) = x \cdot P + y$$

- Khi $P \le P_L$: 
  $$V_{LP}(P) = P \cdot L \left( \frac{1}{\sqrt{P_L}} - \frac{1}{\sqrt{P_U}} \right)$$
- Khi $P_L < P < P_U$:
  $$V_{LP}(P) = L \left( 2\sqrt{P} - \sqrt{P_L} - \frac{P}{\sqrt{P_U}} \right)$$
- Khi $P \ge P_U$:
  $$V_{LP}(P) = L \left( \sqrt{P_U} - \sqrt{P_L} \right)$$

---

### 3.2. Cơ chế Rời rạc hóa giá: Tick Math
Nhằm tối ưu hóa tính toán on-chain trên máy ảo EVM, Uniswap v3 rời rạc hóa dải giá liên tục thành các mốc rời rạc gọi là **Ticks**:

$$P(i) = 1.0001^i$$

Trong đó $i \in \mathbb{Z}$ là chỉ số tick index. Tương ứng:

$$\sqrt{P(i)} = 1.0001^{\frac{i}{2}}$$

- **Tick Spacing ($t_s$):** Tùy thuộc vào Fee Tier ($\gamma$), hợp đồng quy định khoảng cách giữa các tick khởi tạo hợp lệ để giảm thiểu phí gas khi hoán đổi quét qua nhiều tick:
  - Phí $0.01\% \implies t_s = 1$ (Bước giá $\approx 0.01\%$)
  - Phí $0.05\% \implies t_s = 10$ (Bước giá $\approx 0.10\%$)
  - Phí $0.30\% \implies t_s = 60$ (Bước giá $\approx 0.60\%$)
  - Phí $1.00\% \implies t_s = 200$ (Bước giá $\approx 2.02\%$)

Biên dải giá $[P_L, P_U]$ được ánh xạ trực tiếp sang các chỉ số nguyên $[i_L, i_U]$ với $i_L, i_U \equiv 0 \pmod{t_s}$.

---

### 3.3. Tổn thất tạm thời (Impermanent Loss) trong Uniswap v3

So với vị thế HODL cùng danh mục ban đầu $(x_0, y_0)$ tại thời điểm giá $P_0 \in [P_L, P_U]$, giá trị danh mục HODL tại giá $P$ là:

$$V_{HODL}(P) = x_0 \cdot P + y_0 = L \left[ \left( \frac{1}{\sqrt{P_0}} - \frac{1}{\sqrt{P_U}} \right) P + \left( \sqrt{P_0} - \sqrt{P_L} \right) \right]$$

Khi giá vẫn nằm trong dải ($P_L < P < P_U$), mức Impermanent Loss tuyệt đối được định nghĩa:

$$IL(P) = V_{LP}(P) - V_{HODL}(P) = L \left( 2\sqrt{P} - \sqrt{P_0} - \frac{P}{\sqrt{P_0}} \right) \le 0$$

Mức tổn thất tạm thời tương đối:

$$IL_{\text{\%}}(P) = \frac{V_{LP}(P) - V_{HODL}(P)}{V_{HODL}(P)}$$

**Tính chất khuếch đại (Amplification Factor):**  
So với v2 (vốn có $P_L \to 0, P_U \to \infty$), tỷ lệ suy giảm giá trị trên mỗi đơn vị dịch chuyển giá $dP$ của v3 lớn hơn gấp nhiều lần. Tỷ số khuếch đại vốn xấp xỉ:

$$\alpha = \frac{1}{1 - \left( \frac{P_L}{P_U} \right)^{1/4}}$$

Biên dải càng hẹp ($P_L \to P_U$), $\alpha \to \infty$, độ nhạy cảm tổn thất danh mục đối với dịch chuyển giá càng cực đoan.

---

### 3.4. Mô hình Kinh tế lượng và Tối ưu hóa Dải giá

#### Phân rã hiệu quả vị thế
Tỷ suất sinh lời vượt trội tại thời điểm đóng vị thế $T$:

$$\Delta R = \frac{\int_0^T d(Fees) + V_{LP}(P_T) - Gas - Rebalance}{V_{HODL}(P_T)} - 1$$

#### Mô hình hồi quy bảng (Panel Fixed-Effects / Quantile Regression)
Để giải quyết RQ2 và RQ3, thiết lập phương trình hồi quy:

$$ExcessReturn_{i,t} = \alpha_i + \beta_1 Volatility_{p,t} + \beta_2 \ln(Volume_{p,t}) + \beta_3 RangeWidth_{i,t} + \beta_4 FeeTier_p + \beta_5 Rebalance_{i,t} + \varepsilon_{i,t}$$

Trong đó:
- $RangeWidth_{i,t} = \frac{P_{U,i} - P_{L,i}}{P_{current}}$: Chiều rộng dải giá chuẩn hóa.
- $Volatility_{p,t}$: Biến động thực tế hoặc biến động GARCH(1,1) ước lượng từ chuỗi giá tham chiếu Binance.
- Kiểm định phân vị (Quantile Regression tại $\tau \in \{0.1, 0.25, 0.5, 0.75, 0.9\}$) để kiểm soát đặc tính đuôi dày (fat tails) và rủi ro sụt giảm nghiêm trọng (drawdown) của LP.

#### Mô hình Tối ưu hóa Lựa chọn Biên độ $[P_L^*, P_U^*]$
Bài toán tối ưu hóa danh mục cho LP:

$$\max_{P_L, P_U} \quad \mathbb{E} \left[ \int_0^T d(Fees(P_L, P_U, V_t, L_t)) \right] - \mathbb{E} \left[ |IL(P_T; P_L, P_U)| \right] - \mathbb{E} [C_{gas} \cdot N_{rebalance}]$$

Ràng buộc:
- $\mathbb{P}\left( \inf_{t \le T} P_t < P_L \cup \sup_{t \le T} P_t > P_U \right) \le \alpha_{max}$ (Giới hạn xác suất trượt khỏi dải).
- $P_L = P_0 \cdot e^{-k \cdot \sigma \sqrt{\Delta t}}, \quad P_U = P_0 \cdot e^{k \cdot \sigma \sqrt{\Delta t}}$ (Thiết lập dải đối xứng theo độ lệch chuẩn biến động $\sigma$).

---

## 4. Tổng quan tài liệu nghiên cứu 

Bảng tổng hợp dưới đây phân tích các nghiên cứu nền tảng về AMM, Uniswap v3 và cơ chế thanh khoản tập trung:

| STT | Tác giả & Năm | Tên công trình | Đóng góp & Trọng tâm nghiên cứu | Cơ chế Toán học & Mô hình hóa liên quan | Khoảng trống / Ứng dụng vào đề tài |
| :-- | :--- | :--- | :--- | :--- | :--- |
| **1** | Adams et al. (2021) | *Uniswap v3 Core* (Whitepaper) | Khởi xướng cơ chế Concentrated Liquidity, Virtual Reserves và hệ thống Tick. | - Đường cong $(x + x_v)(y + y_v) = L^2$<br>- $P(i) = 1.0001^i$<br>- Rời rạc hóa trạng thái thanh khoản. | Là tài liệu cơ sở quy định cấu trúc dữ liệu on-chain và logic tính toán vị thế của đồ án. |
| **2** | Loesch et al. (2021) | *Impermanent Loss in Uniswap v3* | Chứng minh tính chất toán học của Impermanent Loss bị phóng đại trong v3 so với v2. | - Đạo hàm hàm giá trị vị thế $V_{LP}(P)$<br>- Tính toán tỷ số khuếch đại IL theo hàm của $(P_L, P_U)$. | Cung cấp công thức giải tích chuẩn xác để module hóa thành phần IL trong code backtesting. |
| **3** | Fan et al. (2023) | *Strategic Liquidity Provision in Uniswap V3* (AFT 2023) | Phân tích lý thuyết trò chơi và động thái cạnh tranh chiến lược giữa các LP trong việc đặt dải giá. | - Mô hình hóa phân bổ thanh khoản cân bằng Nash.<br>- Trade-off giữa độ rộng dải và xác suất hứng dòng lệnh. | Cơ sở lý giải hành vi của các dải hẹp và tác động của cạnh tranh thanh khoản lên Fee share. |
| **4** | Deng, Zong, & Wang (2023) | *Static replication of impermanent loss for concentrated liquidity provision* | Tiếp cận tài chính định lượng: Chứng minh vị thế Uniswap v3 tương đương với một danh mục quyền chọn Short Put/Call. | - Phân rã payoff của LP thành các danh mục quyền chọn chuẩn (Black-Scholes framework).<br>- Tái lập cấu trúc rủi ro phi tuyến. | Cung cấp góc nhìn phái sinh giúp chuẩn hóa các chỉ số đo lường rủi ro (Greeks, Delta hedge cho LP). |
| **5** | Hashemseresht & Pourpouneh (2022) | *Concentrated liquidity analysis in Uniswap V3* | Đánh giá thực nghiệm hiệu quả thanh khoản, phân tích cấu trúc chi phí gas và hành vi rebalance. | - Đo lường empirical return của LP trên cặp ETH/USDC.<br>- Ước lượng điểm hòa vốn dựa trên Gas costs. | Đóng góp trực tiếp vào khung giả định chi phí giao dịch và tần suất tái cân bằng trong mô hình hồi quy. |
| **6** | Hasbrouck, Rivera, & Saleh (2025) | *An economic model of a decentralized exchange with concentrated liquidity* | Xây dựng mô hình cân bằng kinh tế vi mô giải thích động lực tạo lập thị trường phi tập trung. | - Hàm chi phí thông tin của nhà đầu tư.<br>- Mối quan hệ giữa Volume, Price discovery và chi phí trích xuất giá trị MEV. | Cung cấp cơ sở lý luận kinh tế để lựa chọn các biến ngoại sinh (Volume, Volatility, Fee Tier) cho RQ3. |
| **7** | Lyandres & Zaidelson (2026) | *Quantitative Investments in Decentralized Finance* | Phương pháp luận đầu tư định lượng trong DeFi, tối ưu hóa danh mục yield farming và LP strategies. | - Backtesting framework cho chiến lược DeFi.<br>- Định lượng Sharpe ratio điều chỉnh cho các phân phối phi chuẩn (Fat tails). | Khung tham chiếu chuẩn để thiết kế 4 chiến lược backtest và cấu trúc hệ thống Metric trên Dashboard. |

---

## 5. Tổng kết khung nối kết (Mapping: RQs - Phương pháp - Dữ liệu - Output)

```
[Câu hỏi NC]      [Dữ liệu sử dụng]                [Phương pháp / Mô hình]             [Output Báo cáo & Dashboard]
   RQ1       ──►  Daily Pool Data (21 tháng)  ──►  Performance Decomposition      ──►  Bảng phân rã Fee vs IL; Tỷ lệ LP > HODL
   RQ2       ──►  Pool Data & Tick States     ──►  Sensitivity Analysis           ──►  Biểu đồ tương quan Range Width vs Sharpe
   RQ3       ──►  Binance (Vol) + Subgraph    ──►  Panel Fixed-Effects/Quantile   ──►  Bảng kết quả hồi quy kinh tế lượng
   RQ4       ──►  Hourly Data (1-3 tháng)     ──►  Dynamic Strategy Backtesting   ──►  Đường cong vốn (Equity Curve) 4 chiến lược
   RQ5       ──►  Historical & GARCH Vol      ──►  Constrained Numerical Opt      ──►  Công cụ DeFi LP Optimizer Widget
```
