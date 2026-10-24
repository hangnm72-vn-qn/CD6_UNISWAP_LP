import math
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.notes import chart_note
from dashboard.components.components import (
    kpi_card,
    section_header,
    step_heading,
)


def _bin_bounds(label):
    """'< -15%' -> (-inf, -15); '-15% to -10%' -> (-15, -10); '> 10%' -> (10, inf)."""
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(label))]
    text = str(label).strip()
    if text.startswith("<") and nums:
        return -math.inf, nums[0]
    if text.startswith(">") and nums:
        return nums[0], math.inf
    if len(nums) >= 2:
        return nums[0], nums[1]
    return None


def _mc_tail_check(mc_dist, var_95):
    """Ước lượng cận trên của phân vị 5% từ histogram, so với VaR 95% đã báo cáo (đơn vị %)."""
    total = sum(b["frequency"] for b in mc_dist)
    if not total:
        return None
    cum = 0
    for b in mc_dist:
        cum += b["frequency"]
        if cum / total >= 0.05:
            bounds = _bin_bounds(b["return_bin"])
            if bounds and math.isfinite(bounds[1]):
                return bounds[1], var_95 - bounds[1] > 1
            return None
    return None


def _frontier_frame(frontier):
    df = pd.DataFrame(frontier)
    df["W"] = (df["p_max"] / df["p_min"]).map(math.log)
    return df.sort_values("W").reset_index(drop=True)


def render_tab4(
    data_tab4,
    research_table,
    style_fig,
    plot_config,
    accent_color,
    text_main_color,
):
    section_header(
        "SECTION 04",
        "RQ5",
        "Tối ưu Dải giá bằng Monte Carlo & CVaR",
        "Bước kết luận của nghiên cứu: xác định dải giá [Pmin, Pmax] tối ưu bằng mô phỏng kịch bản "
        "Monte Carlo dưới ràng buộc rủi ro đuôi (Conditional Value-at-Risk).",
        accent_color,
        question="Nên đặt thanh khoản trong dải giá nào để lợi nhuận kỳ vọng cao mà rủi ro đuôi vẫn nằm trong ngưỡng chịu đựng?",
    )

    with st.expander("📚 Định nghĩa rủi ro đuôi CVaR", expanded=False):
        st.latex(r"CVaR_{\alpha}(ER) = \mathbb{E}\left[ ER \mid ER \le q_{\alpha}(ER) \right]")
        st.caption(
            r"Trong đó: $q_{\alpha}(ER)$ là phân vị mức $\alpha = 5\%$ (Value-at-Risk). "
            r"CVaR phản ánh mức lỗ trung bình trong 5% kịch bản thị trường bất lợi nhất."
        )

    if not data_tab4:
        st.warning("⚠️ Chưa có dữ liệu JSON cho Tab 4.")
        return

    if data_tab4.get("pool_id"):
        st.caption(f"Cấu hình tối ưu hóa: pool {data_tab4['pool_id']}.")

    # =====================================================
    # BƯỚC 4.1 — Dải giá khuyến nghị
    # =====================================================
    opt_range = data_tab4.get("optimal_range", {})
    p_min = opt_range.get("price_min", 0)
    p_max = opt_range.get("price_max", 0)
    p_cur = opt_range.get("current_price", 0)
    if opt_range:
        step_heading(
            "BƯỚC 4.1",
            "Dải giá tối ưu được khuyến nghị",
            accent_color,
            "Kết quả cuối cùng của thuật toán, đặt cạnh giá hiện tại làm mốc tham chiếu.",
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            kpi_card("Giá Min (Pmin)", f"${p_min:,.2f}", "Cận dưới khuyến nghị", accent_color)
        with col2:
            kpi_card("Giá Hiện Tại", f"${p_cur:,.2f}", "Mốc tham chiếu", accent_color, text_main_color)
        with col3:
            kpi_card("Giá Max (Pmax)", f"${p_max:,.2f}", "Cận trên khuyến nghị", accent_color)

        if p_cur and p_min < p_max:
            down_pct = (p_min / p_cur - 1) * 100
            up_pct = (p_max / p_cur - 1) * 100
            fig_range = go.Figure()
            fig_range.add_trace(
                go.Scatter(
                    x=[p_min, p_max], y=[0, 0], mode="lines+markers+text",
                    line=dict(width=12, color=accent_color),
                    marker=dict(size=16, color=accent_color),
                    text=[f"Pmin ({down_pct:+.1f}%)", f"Pmax ({up_pct:+.1f}%)"],
                    textposition="top center", hoverinfo="x",
                )
            )
            fig_range.add_trace(
                go.Scatter(
                    x=[p_cur], y=[0], mode="markers+text",
                    marker=dict(size=20, symbol="diamond", color=text_main_color),
                    text=["Giá hiện tại"], textposition="bottom center", hoverinfo="x",
                )
            )
            style_fig(fig_range, "Vị trí giá hiện tại trong dải giá khuyến nghị")
            fig_range.update_yaxes(visible=False, range=[-1, 1])
            fig_range.update_layout(showlegend=False, height=230)
            st.plotly_chart(fig_range, use_container_width=True, config=plot_config, theme=None)
            width_pct = (p_max - p_min) / p_cur * 100
            chart_note(
                [
                    f"Dải khuyến nghị lệch {down_pct:+.1f}% ở cận dưới và {up_pct:+.1f}% ở cận trên so với giá hiện tại "
                    f"(độ rộng khoảng {width_pct:.1f}% giá hiện tại).",
                    "Dải tương đối rộng: tối ưu không đồng nghĩa với thu hẹp range tối đa mà là cân bằng giữa "
                    "concentration, nguy cơ out-of-range và tail risk.",
                ],
                accent_color,
            )
        st.markdown("---")

    # =====================================================
    # BƯỚC 4.2 — Monte Carlo & rủi ro đuôi
    # =====================================================
    step_heading(
        "BƯỚC 4.2",
        "Phân phối lợi nhuận Monte Carlo & rủi ro đuôi",
        accent_color,
        "Phân phối lợi nhuận mô phỏng cùng VaR / CVaR ở mức 95%.",
    )

    mc_dist = data_tab4.get("monte_carlo_distribution", [])
    cvar_info = data_tab4.get("cvar_metrics", {})
    if mc_dist:
        df_mc = pd.DataFrame(mc_dist)
        fig_mc = px.bar(
            df_mc, x="return_bin", y="frequency",
            category_orders={"return_bin": list(df_mc["return_bin"])},
            labels={"return_bin": "Kịch bản lợi nhuận", "frequency": "Số kịch bản"},
        )
        style_fig(fig_mc, "Phân phối tần suất lợi nhuận theo kịch bản giá", line_color=accent_color)
        st.plotly_chart(fig_mc, use_container_width=True, config=plot_config, theme=None)

        total = int(df_mc["frequency"].sum())
        neg_share = df_mc[df_mc["return_bin"].map(lambda b: (_bin_bounds(b) or (0, 0))[1] <= 0)]["frequency"].sum() / total * 100
        chart_note(
            f"Trong {total:,} kịch bản, khoảng {neg_share:.0f}% cho lợi nhuận âm. Hình dạng phân phối, nhất là đuôi trái, "
            "quan trọng không kém lợi nhuận trung bình vì hai phương án cùng kỳ vọng có thể khác nhau về đuôi âm.",
            accent_color,
        )

    if cvar_info:
        m1, m2 = st.columns(2)
        m1.metric("VaR (95%)", f"{cvar_info.get('var_95', 'N/A')}%")
        m2.metric("CVaR (95%)", f"{cvar_info.get('cvar_95', 'N/A')}%")
        try:
            var_v, cvar_v = float(cvar_info["var_95"]), float(cvar_info["cvar_95"])
            lines = [
                f"VaR 95% = {var_v}% và CVaR 95% = {cvar_v}%: "
                + ("hai giá trị gần như trùng nhau và sát 0, nghĩa là đuôi lỗ của dải giá được chọn rất nhẹ."
                   if abs(var_v - cvar_v) < 0.05 and abs(cvar_v) < 1
                   else "CVaR cho biết độ sâu của đuôi mà VaR không thể hiện.")
            ]
            check = _mc_tail_check(mc_dist, var_v) if mc_dist else None
            if check and check[1]:
                st.warning(
                    f"⚠️ **Phân phối Monte Carlo không khớp VaR/CVaR:** theo histogram, 5% kịch bản xấu nhất nằm ở mức "
                    f"lợi nhuận khoảng {check[0]:.0f}% trở xuống, trong khi VaR 95% báo cáo là {var_v}%. "
                    "Histogram có thể thuộc một dải giá khác với dải khuyến nghị; cần kiểm tra lại."
                )
        except (KeyError, TypeError, ValueError):
            lines = ["CVaR cho biết độ sâu của đuôi mà VaR không thể hiện."]
        chart_note(lines, accent_color)

    st.markdown("---")

    # =====================================================
    # BƯỚC 4.3 — Đường biên hiệu quả
    # =====================================================
    step_heading(
        "BƯỚC 4.3",
        "Đường biên hiệu quả (Efficient Frontier)",
        accent_color,
        "Các phương án dải giá theo lợi nhuận kỳ vọng và rủi ro đuôi CVaR. W = ln(Pmax / Pmin).",
    )
    frontier = data_tab4.get("efficient_frontier", [])
    if frontier:
        fr = _frontier_frame(frontier)
        opt_mask = (
            ((fr["p_min"] - p_min).abs() < 0.01) & ((fr["p_max"] - p_max).abs() < 0.01)
            if opt_range else pd.Series(False, index=fr.index)
        )
        fr["label"] = fr["W"].map(lambda w: f"W={w:.2f}")

        fig_ef = px.line(
            fr, x="risk_cvar", y="expected_return", text="label", markers=True,
            labels={"risk_cvar": "Rủi ro: CVaR 5% (độ lớn tổn thất, %)", "expected_return": "Lợi nhuận kỳ vọng (%)"},
        )
        style_fig(fig_ef, "Đánh đổi lợi nhuận kỳ vọng và rủi ro đuôi giữa các dải giá", line_color=accent_color)
        fig_ef.update_traces(textposition="top center")
        if opt_mask.any():
            o = fr[opt_mask].iloc[0]
            fig_ef.add_trace(
                go.Scatter(
                    x=[o["risk_cvar"]], y=[o["expected_return"]], mode="markers+text",
                    marker=dict(size=18, symbol="star", color="#f59e0b"),
                    text=["Khuyến nghị"], textposition="bottom center", showlegend=False,
                )
            )
        st.plotly_chart(fig_ef, use_container_width=True, config=plot_config, theme=None)

        disp = fr.copy()
        disp["Khuyến nghị"] = ["★" if m else "" for m in opt_mask]
        disp = disp[["W", "p_min", "p_max", "expected_return", "risk_cvar", "Khuyến nghị"]].rename(
            columns={
                "W": "W = ln(Pmax/Pmin)",
                "p_min": "Pmin ($)",
                "p_max": "Pmax ($)",
                "expected_return": "Lợi nhuận kỳ vọng (%)",
                "risk_cvar": "CVaR 5% (%)",
            }
        )
        disp["W = ln(Pmax/Pmin)"] = disp["W = ln(Pmax/Pmin)"].map(lambda x: f"{x:.2f}")
        for c in ("Pmin ($)", "Pmax ($)"):
            disp[c] = disp[c].map(lambda x: f"{x:,.2f}")
        for c in ("Lợi nhuận kỳ vọng (%)", "CVaR 5% (%)"):
            disp[c] = disp[c].map(lambda x: f"{x:,.2f}")
        research_table(disp, accent_color)

        first, last = fr.iloc[0], fr.iloc[-1]
        if fr["expected_return"].is_monotonic_increasing and fr["risk_cvar"].is_monotonic_decreasing:
            trend = (
                f"Khi W tăng từ {first['W']:.2f} lên {last['W']:.2f}, lợi nhuận kỳ vọng tăng từ {first['expected_return']:+.2f}% "
                f"lên {last['expected_return']:+.2f}% và CVaR giảm từ {first['risk_cvar']:.2f}% xuống {last['risk_cvar']:.2f}%. "
                "Trong tập phương án này, range rộng hơn vừa sinh lời cao hơn vừa ít rủi ro đuôi hơn, nên ràng buộc rủi ro "
                "chủ yếu có tác dụng loại các range quá hẹp."
            )
        else:
            trend = "Lợi nhuận kỳ vọng và CVaR không thay đổi đơn điệu theo W, cho thấy có đánh đổi giữa các phương án."
        lines = [trend]
        if opt_mask.any():
            o = fr[opt_mask].iloc[0]
            lines.append(
                f"Phương án khuyến nghị (★) có W = {o['W']:.2f}, kỳ vọng {o['expected_return']:+.2f}% và CVaR {o['risk_cvar']:.2f}%."
            )
        chart_note(lines, accent_color)

    st.warning(
        r"🎯 **Cách đọc kết quả (RQ5):** dải giá hẹp tập trung thanh khoản hơn nên thu phí nhiều hơn khi giá ở trong dải, "
        r"nhưng dễ bị lệch dải và chịu rủi ro đuôi lớn hơn. Dải giá được khuyến nghị cần giữ $CVaR_{5\%}$ trong "
        r"ngưỡng chịu đựng mà vẫn tối đa hóa lợi nhuận kỳ vọng."
    )

    st.markdown("---")
    step_heading("TỔNG KẾT", "Chuỗi lập luận của toàn bộ nghiên cứu", accent_color)
    st.markdown(
        "1. **Bối cảnh (Tab 01):** các pool khác nhau về thanh khoản, xoay vòng vốn và biến động.\n"
        "2. **Phân rã (Tab 02, RQ1):** phí giao dịch bù đắp được bao nhiêu IL và chi phí vận hành so với HODL.\n"
        "3. **Chiến lược & yếu tố (Tab 03, RQ2–RQ4):** chiến lược nào hiệu quả và vì sao, có kiểm định kèm theo.\n"
        "4. **Tối ưu (Tab 04, RQ5):** dải giá [Pmin, Pmax] tối ưu dưới ràng buộc CVaR."
    )