import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.components.notes import chart_note
from dashboard.components.components import (
    TAB_ACCENTS,
    bridge,
    kpi_card,
    section_header,
    step_heading,
)

def _d(x):
    """Số chữ số thập phân thích hợp: pool stablecoin có giá trị rất nhỏ."""
    return 2 if abs(x) < 10 else 1


def _extreme(df, col, largest=True):
    s = df[col].dropna()
    if s.empty:
        return None
    idx = s.idxmax() if largest else s.idxmin()
    return df.loc[idx, "pool_code"], s.loc[idx]


def _summary_note(summary_num):
    parts = []
    tvl = _extreme(summary_num, "tvl_usd")
    vol = _extreme(summary_num, "volume_usd")
    low_vola = _extreme(summary_num, "volatility_7d", largest=False)
    if tvl:
        parts.append(f"TVL lớn nhất: {tvl[0]} ({tvl[1] / 1e6:,.2f}M USD)")
    if vol:
        parts.append(f"volume lớn nhất: {vol[0]} ({vol[1] / 1e6:,.2f}M USD/ngày)")
    if low_vola:
        parts.append(f"biến động thấp nhất: {low_vola[0]} ({low_vola[1]:.2f}%)")
    line1 = "Trong khoảng đã lọc, " + "; ".join(parts) + "." if parts else "Chưa đủ dữ liệu để so sánh."
    line2 = (
        "Thống kê mô tả chỉ xác lập bối cảnh, chưa đủ để kết luận pool nào tốt nhất cho LP; "
        "cần đối chiếu fee, inventory loss và chi phí ở Tab 02–03."
    )
    return [line1, line2]


def _ratio_note(summary_num):
    hi = _extreme(summary_num, "volume_tvl_ratio")
    lo = _extreme(summary_num, "volume_tvl_ratio", largest=False)
    line1 = ""
    if hi and lo:
        line1 = f"Vol/TVL cao nhất ở {hi[0]} ({hi[1]:.2f}x), thấp nhất ở {lo[0]} ({lo[1]:.2f}x). "
    return (
        line1
        + "Tỷ lệ cao nghĩa là vốn xoay vòng nhiều, tạo cơ hội phí lớn; nhưng phí LP thực nhận còn "
        "phụ thuộc fee tier và việc vị thế có đang active hay không."
    )


def _series_notes(df):
    notes = {}
    price = df["close_price"].dropna()
    if not price.empty:
        first, last = price.iloc[0], price.iloc[-1]
        dec = 4 if abs(last) < 10 else 2
        pct = (last / first - 1) * 100 if first else float("nan")
        notes["price"] = (
            f"Giá đi từ {first:,.{dec}f} đến {last:,.{dec}f} USD ({pct:+.1f}%), trong biên "
            f"{price.min():,.{dec}f}–{price.max():,.{dec}f}. Xu hướng giá kéo dài là nguyên nhân chính "
            "khiến range cố định bị bỏ lại phía sau (out-of-range) và làm tăng inventory loss."
        )
    vola = df["volatility_7d"].dropna()
    if not vola.empty:
        notes["vol"] = (
            f"Biến động trung bình {vola.mean():.{_d(vola.mean())}f}% (trung vị {vola.median():.{_d(vola.median())}f}%, "
            f"đỉnh {vola.max():.{_d(vola.max())}f}%). Biến động có tính cụm theo thời gian nên một range cố định "
            "thiết kế từ điều kiện trung bình khó phù hợp cả kỳ; đây là cơ sở cho chiến lược "
            "volatility-scaled/dynamic và Quantile Regression."
        )
    tvl = df["tvl_usd"].dropna()
    if not tvl.empty:
        first, last = tvl.iloc[0], tvl.iloc[-1]
        pct = (last / first - 1) * 100 if first else float("nan")
        notes["tvl"] = (
            f"TVL đầu kỳ {first / 1e6:,.1f}M, cuối kỳ {last / 1e6:,.1f}M USD ({pct:+.1f}%), trung bình "
            f"{tvl.mean() / 1e6:,.1f}M. Cùng một cặp tài sản vẫn có thể rất khác nhau về quy mô và mức sử dụng "
            "tùy cấu hình pool (ví dụ WETH/USDC 0,05% so với 0,30%)."
        )
    ratio = df["volume_tvl_ratio"].dropna()
    if not ratio.empty:
        skew = (
            "Mean cao hơn median cho thấy phân phối lệch phải do các ngày giao dịch đột biến; ngày bình thường "
            "tạo phí thấp hơn mức trung bình."
            if ratio.mean() > ratio.median()
            else "Mean không vượt median nên xoay vòng vốn tương đối ổn định, ít bị kéo bởi các ngày đột biến."
        )
        notes["ratio_ts"] = (
            f"Vol/TVL trung bình {ratio.mean():.2f}x, trung vị {ratio.median():.2f}x, đỉnh {ratio.max():.2f}x. "
            + skew
            + " Lợi nhuận LP còn phụ thuộc volume có rơi đúng lúc vị thế đang active hay không."
        )
    return notes


def render_tab1(
    df_daily,
    pool_mapping,
    pool_colors,
    research_table,
    style_fig,
    plot_config,
    accent_color,
):
    section_header(
        "SECTION 01",
        "DESCRIPTIVE",
        "Bối cảnh Thị trường & Cấu trúc Vi mô các Pool",
        "Mô tả dữ liệu đầu vào của 5 pool nghiên cứu: quy mô thanh khoản (TVL), "
        "khối lượng giao dịch (Volume), độ biến động thực hiện và tỷ lệ Volume/TVL. "
        "Đây là nền tảng để hiểu vì sao lợi nhuận LP ở các bước sau khác nhau giữa các pool.",
        accent_color,
        question="Các pool khác nhau thế nào về quy mô, hoạt động giao dịch và rủi ro giá?",
    )

    if df_daily.empty:
        st.error("⚠️ Không có dữ liệu lịch sử trong file pools_daily.csv")
        return

    # ---- Bộ điều khiển thử nghiệm pool (đặt ngay tại tab) ----
    min_date = df_daily["date"].min().date()
    max_date = df_daily["date"].max().date()
    with st.container(border=True):
        st.markdown("**🎛️ Thử nghiệm với pool & khoảng thời gian**")
        ctl_pool, ctl_date = st.columns(2)
        with ctl_pool:
            selected_pool_display = st.selectbox(
                "Chọn pool nghiên cứu",
                options=list(pool_mapping.keys()),
                key="tab1_pool",
            )
        with ctl_date:
            date_range = st.date_input(
                "Khoảng thời gian phân tích",
                [min_date, max_date],
                min_value=min_date,
                max_value=max_date,
                key="tab1_dates",
            )
    actual_pool_name = pool_mapping[selected_pool_display]
    current_pool_color = pool_colors[selected_pool_display]

    # ---- Khung lý thuyết (thu gọn để kết quả lên trước) ----
    with st.expander("📚 Khung đo lường & công thức thống kê mô tả", expanded=False):
        st.latex(
            r"Ret_{t} = \ln\left(\frac{P_t}{P_{t-1}}\right), \quad "
            r"Volatility_{7D} = \sqrt{365} \times \sigma_{7D}(Ret_t) \times 100\%"
        )
        st.latex(r"Ratio_{Vol/TVL} = \frac{Volume_{USD,t}}{TVL_{USD,t}}")
        st.caption(
            "Trong đó: $Ret_t$ là lợi suất log ngày; $Volatility_{7D}$ là độ biến động "
            "thực hiện cửa sổ 7 ngày, thường niên hóa với 365 ngày; "
            "$Ratio_{Vol/TVL}$ phản ánh mức độ xoay vòng vốn của LP."
        )

    # ---- Lọc theo khoảng thời gian (áp dụng cho mọi pool để so sánh công bằng) ----
    df_range = df_daily
    if len(date_range) == 2:
        start_d, end_d = date_range
        df_range = df_daily[
            (df_daily["date"].dt.date >= start_d)
            & (df_daily["date"].dt.date <= end_d)
        ]
    elif len(date_range) == 1:
        st.caption("ℹ️ Hãy chọn đủ ngày bắt đầu và kết thúc ở thanh bên để lọc khoảng thời gian.")

    df_selected = df_range[df_range["pool_code"] == actual_pool_name].copy()
    if df_selected.empty:
        st.warning("⚠️ Không có dữ liệu của pool này trong khoảng thời gian đã chọn.")
        return

    # =====================================================
    # BƯỚC 1.1 — Chân dung pool đang chọn
    # =====================================================
    step_heading(
        "BƯỚC 1.1",
        f"Chân dung pool đang chọn · {selected_pool_display}",
        accent_color,
        "Bốn chỉ số trung bình trong khoảng thời gian đã lọc.",
    )

    avg_tvl = df_selected["tvl_usd"].mean()
    avg_vol = df_selected["volume_usd"].mean()
    avg_fee = df_selected["fee_usd"].mean()
    avg_volatility = df_selected["volatility_7d"].mean()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("TVL Trung Bình", f"${avg_tvl / 1e6:.2f}M", "Quy mô thanh khoản", current_pool_color)
    with c2:
        kpi_card("Khối Lượng TB Ngày", f"${avg_vol / 1e6:.2f}M", "Hoạt động giao dịch", current_pool_color)
    with c3:
        kpi_card("Realized Volatility", f"{avg_volatility:.1f}%", "Thường niên hóa", current_pool_color)
    with c4:
        kpi_card("Phí TB Ngày / Pool", f"${avg_fee / 1e3:.1f}k", "Pool-level", current_pool_color)

    st.markdown("---")

    # =====================================================
    # BƯỚC 1.2 — So sánh 5 pool
    # =====================================================
    step_heading(
        "BƯỚC 1.2",
        "So sánh cấu trúc vi mô giữa 5 pool",
        accent_color,
        "Pool đang chọn được tô nổi bật. Số liệu tính trên cùng khoảng thời gian đã lọc.",
    )

    notes = _series_notes(df_selected)

    summary_num = (
        df_range.groupby("pool_code")
        .agg(
            tvl_usd=("tvl_usd", "mean"),
            volume_usd=("volume_usd", "mean"),
            volume_tvl_ratio=("volume_tvl_ratio", "mean"),
            volatility_7d=("volatility_7d", "mean"),
        )
        .reset_index()
    )

    summary_df = summary_num.copy()
    summary_df["tvl_usd"] = summary_df["tvl_usd"].map(lambda x: f"${x / 1e6:,.2f}M")
    summary_df["volume_usd"] = summary_df["volume_usd"].map(lambda x: f"${x / 1e6:,.2f}M")
    summary_df["volume_tvl_ratio"] = summary_df["volume_tvl_ratio"].map(lambda x: f"{x:.2f}x")
    summary_df["volatility_7d"] = summary_df["volatility_7d"].map(lambda x: f"{x:.2f}%")
    summary_df = summary_df.rename(
        columns={
            "pool_code": "Pool / Cặp Giao Dịch",
            "tvl_usd": "TVL Trung Bình",
            "volume_usd": "Volume TB Ngày",
            "volume_tvl_ratio": "Tỷ lệ Vol/TVL",
            "volatility_7d": "Độ Biến Động (Vol 7D)",
        }
    )
    research_table(summary_df, accent_color, actual_pool_name)
    chart_note(_summary_note(summary_num), accent_color)

    summary_num["Nhóm"] = summary_num["pool_code"].map(
        lambda p: "Pool đang chọn" if p == actual_pool_name else "Pool khác"
    )
    fig_ratio = px.bar(
        summary_num,
        x="pool_code",
        y="volume_tvl_ratio",
        color="Nhóm",
        color_discrete_map={"Pool đang chọn": current_pool_color, "Pool khác": "#94a3b8"},
        labels={"pool_code": "Pool", "volume_tvl_ratio": "Vol/TVL trung bình (x)"},
        text_auto=".2f",
    )
    style_fig(fig_ratio, "Mức độ xoay vòng vốn (Vol/TVL) theo pool")
    fig_ratio.update_layout(showlegend=False)
    st.plotly_chart(fig_ratio, use_container_width=True, config=plot_config, theme=None)
    chart_note(_ratio_note(summary_num), accent_color)

    st.markdown("---")

    # =====================================================
    # BƯỚC 1.3 — Diễn biến theo thời gian
    # =====================================================
    step_heading(
        "BƯỚC 1.3",
        f"Diễn biến theo thời gian · {selected_pool_display}",
        accent_color,
        "Hàng trên: giá và biến động (nguồn gốc của rủi ro IL). "
        "Hàng dưới: thanh khoản và xoay vòng vốn (nguồn gốc của phí).",
    )

    row1_a, row1_b = st.columns(2)
    with row1_a:
        fig_price = px.line(
            df_selected, x="date", y="close_price",
            labels={"date": "Ngày", "close_price": "Giá (USD)"},
        )
        style_fig(fig_price, "Giá đóng cửa", line_color=current_pool_color)
        st.plotly_chart(fig_price, use_container_width=True, config=plot_config, theme=None)
        if "price" in notes:
            chart_note(notes["price"], accent_color)
    with row1_b:
        fig_vol = px.line(
            df_selected, x="date", y="volatility_7d",
            labels={"date": "Ngày", "volatility_7d": "Độ biến động (%)"},
        )
        style_fig(fig_vol, "Biến động thực hiện 7D", line_color="#ec4899")
        st.plotly_chart(fig_vol, use_container_width=True, config=plot_config, theme=None)
        if "vol" in notes:
            chart_note(notes["vol"], accent_color)

    row2_a, row2_b = st.columns(2)
    with row2_a:
        fig_tvl = px.line(
            df_selected, x="date", y="tvl_usd",
            labels={"date": "Ngày", "tvl_usd": "TVL (USD)"},
        )
        style_fig(fig_tvl, "Tổng thanh khoản bị khóa (TVL)", line_color=current_pool_color)
        st.plotly_chart(fig_tvl, use_container_width=True, config=plot_config, theme=None)
        if "tvl" in notes:
            chart_note(notes["tvl"], accent_color)
    with row2_b:
        fig_ratio_ts = px.line(
            df_selected, x="date", y="volume_tvl_ratio",
            labels={"date": "Ngày", "volume_tvl_ratio": "Vol/TVL (x)"},
        )
        style_fig(fig_ratio_ts, "Tỷ lệ Volume/TVL theo ngày", line_color="#f59e0b")
        st.plotly_chart(fig_ratio_ts, use_container_width=True, config=plot_config, theme=None)
        if "ratio_ts" in notes:
            chart_note(notes["ratio_ts"], accent_color)

    # =====================================================
    # Nhận xét tự động từ dữ liệu (không viết cứng kết luận)
    # =====================================================
    vol_series = df_selected["volatility_7d"].dropna()
    ratio_pool = df_selected["volume_tvl_ratio"].mean()
    ratio_all = summary_num["volume_tvl_ratio"].mean()
    text = (
        f"📊 **Nhận xét thống kê mô tả:** trong giai đoạn đã chọn, **{selected_pool_display}** "
        f"có Vol/TVL trung bình **{ratio_pool:.2f}x** (trung bình 5 pool: {ratio_all:.2f}x)"
    )
    if not vol_series.empty:
        peak_idx = vol_series.idxmax()
        peak_date = df_selected.loc[peak_idx, "date"].strftime("%d/%m/%Y")
        text += f"; biến động 7D đạt đỉnh **{vol_series.max():.1f}%** vào {peak_date}"
    corr_df = df_selected[["volatility_7d", "volume_usd"]].dropna()
    if len(corr_df) > 3:
        corr = corr_df["volatility_7d"].corr(corr_df["volume_usd"])
        text += f"; tương quan giữa biến động và volume là **{corr:.2f}**"
    st.info(
        text + ". Volume/TVL cao cho thấy mỗi đồng vốn LP được xoay vòng nhiều hơn (tiềm năng phí lớn), "
        "nhưng biến động giá mạnh cũng làm tăng rủi ro tổn thất tạm thời (IL)."
    )

    bridge(
        "TAB 02 · RQ1",
        "Phí tiềm năng (Vol/TVL) và rủi ro giá (Volatility) đã rõ. Câu hỏi kế tiếp: "
        "sau khi trừ IL, gas và chi phí rebalance, LP có thực sự lời hơn HODL không?",
        TAB_ACCENTS[2],
    )