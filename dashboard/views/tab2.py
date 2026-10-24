import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.notes import chart_note
from dashboard.components.components import (
    TAB_ACCENTS,
    bridge,
    format_number,
    kpi_card,
    section_header,
    step_heading,
)

LABELS = {
    "fee_earned": "Phí thu được (Fee)",
    "impermanent_loss": "Tổn thất tạm thời (IL)",
    "net_pnl": "Lợi nhuận ròng",
}
GREEN, RED, GREY = "#059669", "#dc2626", "#64748b"


def _waterfall_items(wf):
    """Trả về danh sách (nhãn, giá trị, loại) cho waterfall.

    Nếu JSON đúng 3 khóa fee_earned / impermanent_loss / net_pnl thì suy ra phần còn lại
    (gas, slippage, chi phí khác) = net - fee - IL để các cột cộng khớp với Net.
    """
    nums = {k: v for k, v in wf.items() if isinstance(v, (int, float))}
    if {"fee_earned", "impermanent_loss", "net_pnl"} <= set(nums):
        fee, il, net = nums["fee_earned"], nums["impermanent_loss"], nums["net_pnl"]
        other = round(net - fee - il, 2)
        items = [
            (LABELS["fee_earned"], fee, "relative"),
            (LABELS["impermanent_loss"], il, "relative"),
        ]
        if abs(other) >= 0.005:
            items.append(("Gas & chi phí khác", other, "relative"))
        items.append((LABELS["net_pnl"], net, "total"))
        return items
    return [(LABELS.get(k, str(k)), v, "relative") for k, v in nums.items()]


def _summary_note(df):
    n = len(df)
    neg = df[df["roi_percent"] < 0]
    pos = df[df["roi_percent"] > 0]
    lines = []
    if not neg.empty:
        zero_fee = int((neg["total_fee"] == 0).sum())
        lines.append(
            f"{len(neg)}/{n} pool có ROI âm (từ {neg['roi_percent'].min():.2f}% đến {neg['roi_percent'].max():.2f}%), "
            f"trong đó {zero_fee} pool không thu được phí nào; lỗ chủ yếu đến từ IL."
        )
    if not pos.empty:
        top = pos.loc[pos["roi_percent"].idxmax()]
        lines.append(
            f"{top['pool_name']} là pool lãi rõ nhất: Fee {top['total_fee']:,.0f} USD, ROI {top['roi_percent']:,.0f}%."
        )
        if top["roi_percent"] > 200:
            lines.append(
                "ROI cực lớn ở pool stablecoin là kết quả của biến động rất thấp và cấu hình mô phỏng; "
                "không nên ngoại suy cho các pool khác hay giai đoạn khác."
            )
    return lines


def render_tab2(
    data_tab2,
    research_table,
    style_fig,
    plot_config,
    accent_color,
    actual_pool_name=None,
):
    section_header(
        "SECTION 02",
        "RQ1",
        "Phân rã Lợi nhuận LP so với HODL",
        "Hạch toán lợi nhuận ròng của vị thế LP thành các cấu phần: Phí giao dịch (Fee), "
        "Tổn thất tạm thời (IL), Phí Gas và Chi phí Rebalance, rồi so với chiến lược nắm giữ (HODL).",
        accent_color,
        question="LP kiếm được bao nhiêu từ phí, mất bao nhiêu vì IL và chi phí vận hành, và kết quả ròng so với HODL ra sao?",
    )

    with st.expander("📚 Khung lý thuyết: đồng nhất thức PnL", expanded=False):
        st.latex(r"ER_T = \frac{V_{LP,T} + F_T - G_T - C_{reb,T} - V_{HODL,T}}{C_0}")
        st.latex(
            r"D_T = V_{HODL,T} - V_{LP,T} \implies "
            r"ER_T = \frac{F_T - D_T - G_T - C_{reb,T}}{C_0}"
        )
        st.caption(
            "Trong đó: $F_T$ là tổng phí thu được, $D_T$ là chênh lệch inventory (IL), "
            "$G_T$ là chi phí gas, $C_{reb,T}$ là chi phí rebalance, $C_0$ là vốn ban đầu."
        )

    if not data_tab2:
        st.warning("⚠️ Chưa có dữ liệu JSON cho Tab 2.")
        return

    ts_list = data_tab2.get("time_series", [])
    df_ts = pd.DataFrame(ts_list) if ts_list else pd.DataFrame()
    pool_id = data_tab2.get("pool_id")
    if pool_id:
        capital = f" · vốn ban đầu ≈ {df_ts['hodl_value'].iloc[0]:,.0f} USD" if not df_ts.empty else ""
        st.caption(f"Cấu hình backtest hiển thị ở bước 2.1 và 2.2: pool {pool_id}{capital}.")

    # =====================================================
    # BƯỚC 2.1 — Các cấu phần PnL
    # =====================================================
    waterfall_dict = data_tab2.get("waterfall_data", {})
    if waterfall_dict:
        step_heading(
            "BƯỚC 2.1",
            "Các cấu phần của lợi nhuận LP",
            accent_color,
            "Từ phí thu được, trừ IL và chi phí, ra lợi nhuận ròng.",
        )
        items = _waterfall_items(waterfall_dict)

        cols = st.columns(len(items))
        for col, (label, value, kind) in zip(cols, items):
            with col:
                if kind == "total":
                    badge, color = "Kết quả ròng", GREEN if value >= 0 else RED
                elif value > 0:
                    badge, color = "Đóng góp dương", GREEN
                elif value == 0:
                    badge, color = "Không phát sinh", GREY
                else:
                    badge, color = "Chi phí / tổn thất", RED
                kpi_card(label, format_number(value, prefix="$"), badge, accent_color, value_color=color)

        labels = [i[0] for i in items]
        values = [i[1] for i in items]
        fig_wf = go.Figure(
            go.Waterfall(
                x=labels,
                y=values,
                measure=[i[2] for i in items],
                text=[f"{v:+,.2f}" for v in values],
                textposition="outside",
                increasing=dict(marker=dict(color=GREEN)),
                decreasing=dict(marker=dict(color=RED)),
                totals=dict(marker=dict(color=GREY)),
                connector=dict(line=dict(color=GREY, width=1)),
            )
        )
        style_fig(fig_wf, "Cầu nối lợi nhuận: Fee → IL → Chi phí → Lợi nhuận ròng")
        fig_wf.update_layout(showlegend=False, yaxis_title="Giá trị ($)")
        st.plotly_chart(fig_wf, use_container_width=True, config=plot_config, theme=None)

        fee_v = next((v for lab, v, _ in items if lab == LABELS["fee_earned"]), None)
        net_v = items[-1][1]
        il_v = next((v for lab, v, _ in items if lab == LABELS["impermanent_loss"]), None)
        lines = []
        if fee_v is not None and il_v is not None:
            if fee_v <= 0:
                lines.append(
                    f"Fee bằng {fee_v:,.2f} USD nên không có khoản thu nào bù cho IL ({il_v:,.2f} USD); "
                    f"gần như toàn bộ khoản lỗ ròng ({net_v:,.2f} USD) đến từ IL."
                )
            else:
                lines.append(
                    f"Fee {fee_v:,.2f} USD so với IL {il_v:,.2f} USD: LP "
                    + ("bù được" if fee_v + il_v > 0 else "chưa bù được")
                    + f" tổn thất inventory; lợi nhuận ròng là {net_v:,.2f} USD."
                )
        lines.append(
            "LP chỉ vượt HODL khi Fee bù đủ IL và toàn bộ chi phí; concentrated liquidity tự thân không đảm bảo điều đó (RQ1)."
        )
        chart_note(lines, accent_color)
        st.markdown("---")

    # =====================================================
    # BƯỚC 2.2 — Diễn biến theo thời gian
    # =====================================================
    if not df_ts.empty:
        step_heading(
            "BƯỚC 2.2",
            "Diễn biến giá trị vị thế LP so với HODL theo thời gian",
            accent_color,
            "Cho thấy khoản chênh lệch hình thành dần ra sao và LP có thu được phí ở giai đoạn nào không.",
        )
        df_ts["timestamp"] = pd.to_datetime(df_ts["timestamp"])
        col_a, col_b = st.columns(2)

        with col_a:
            df_val = df_ts.rename(columns={"lp_value": "Vị thế LP", "hodl_value": "HODL"})
            fig_val = px.line(
                df_val, x="timestamp", y=["Vị thế LP", "HODL"],
                color_discrete_map={"Vị thế LP": accent_color, "HODL": "#0f172a"},
                labels={"value": "Giá trị (USD)", "timestamp": "Ngày", "variable": ""},
            )
            style_fig(fig_val, "Giá trị vị thế: LP vs HODL")
            st.plotly_chart(fig_val, use_container_width=True, config=plot_config, theme=None)

            lp_last, h_last, h_first = df_ts["lp_value"].iloc[-1], df_ts["hodl_value"].iloc[-1], df_ts["hodl_value"].iloc[0]
            lines = [
                f"Cuối kỳ HODL đạt {h_last:,.0f} USD (từ {h_first:,.0f}), còn vị thế LP là {lp_last:,.0f} USD."
            ]
            if df_ts["lp_value"].iloc[1:].nunique() == 1:
                lines.append(
                    "Giá trị LP không đổi từ kỳ đầu đến cuối kỳ, phù hợp với trạng thái vị thế nằm ngoài range, "
                    "không còn hưởng lợi khi giá thay đổi."
                )
            chart_note(lines, accent_color)

        with col_b:
            df_fi = df_ts.rename(columns={"fee_accumulated": "Fee tích lũy", "il_accumulated": "IL tích lũy"})
            fig_fi = px.line(
                df_fi, x="timestamp", y=["Fee tích lũy", "IL tích lũy"],
                color_discrete_map={"Fee tích lũy": GREEN, "IL tích lũy": RED},
                labels={"value": "Giá trị (USD)", "timestamp": "Ngày", "variable": ""},
            )
            style_fig(fig_fi, "Fee tích lũy vs IL tích lũy")
            st.plotly_chart(fig_fi, use_container_width=True, config=plot_config, theme=None)

            il = df_ts["il_accumulated"]
            worst_date = df_ts.loc[il.idxmin(), "timestamp"].strftime("%d/%m/%Y")
            lines = [
                f"IL tích lũy sâu nhất {il.min():,.0f} USD (vào {worst_date}), cuối kỳ {il.iloc[-1]:,.0f} USD; "
                "IL biến động theo giá của HODL."
            ]
            if df_ts["fee_accumulated"].max() == 0:
                lines.append("Fee tích lũy bằng 0 trong toàn bộ kỳ, nên không có khoản phí nào bù lại IL.")
            chart_note(lines, accent_color)
        st.markdown("---")

    # =====================================================
    # BƯỚC 2.3 — So sánh giữa các pool
    # =====================================================
    summary_list = data_tab2.get("summary_table", [])
    if summary_list:
        step_heading(
            "BƯỚC 2.3",
            "Bảng phân rã chi tiết theo pool",
            accent_color,
            "So sánh Fee, IL và ROI của từng pool trong cùng cấu hình backtest.",
        )
        df_sum = pd.DataFrame(summary_list)
        disp = df_sum.rename(
            columns={
                "pool_name": "Pool",
                "total_fee": "Tổng phí thu được ($)",
                "total_il": "IL ($)",
                "net_pnl": "Lợi nhuận ròng ($)",
                "roi_percent": "ROI (%)",
            }
        )
        for col in ("Tổng phí thu được ($)", "IL ($)", "Lợi nhuận ròng ($)"):
            if col in disp:
                disp[col] = disp[col].map(lambda x: f"{x:,.2f}")
        if "ROI (%)" in disp:
            disp["ROI (%)"] = disp["ROI (%)"].map(lambda x: f"{x:,.2f}%")
        research_table(disp, accent_color, actual_pool_name)
        if {"roi_percent", "total_fee", "pool_name"} <= set(df_sum.columns):
            chart_note(_summary_note(df_sum), accent_color)

    st.info(
        "💡 **Cách đọc kết quả (RQ1):** so sánh phí giao dịch $F_T$ với tổn thất tạm thời $D_T$ cùng chi phí "
        "vận hành $G_T + C_{reb,T}$. Nếu $F_T$ không bù đắp được các khoản còn lại thì LP kém hơn HODL."
    )

    bridge(
        "TAB 03 · RQ2–RQ4",
        "Mức lãi/lỗ ròng phụ thuộc vào cách đặt và điều chỉnh dải giá. Tab kế tiếp mô phỏng "
        "4 chiến lược LP và dùng hồi quy để chỉ ra yếu tố nào quyết định hiệu quả.",
        TAB_ACCENTS[3],
    )