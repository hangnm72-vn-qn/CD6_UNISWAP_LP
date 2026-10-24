import re

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.components.notes import chart_note
from dashboard.components.components import (
    TAB_ACCENTS,
    best_row_by,
    bridge,
    section_header,
    step_heading,
)

# Tên cột trong JSON -> nhãn hiển thị (giả định: moderate = S3, rebalance = S4)
SERIES = {
    "strategy_full_range": ("S1", "S1 Full Range", "#2563eb"),
    "strategy_narrow": ("S2", "S2 Narrow", "#f59e0b"),
    "strategy_moderate": ("S3", "S3 Moderate", "#dc2626"),
    "strategy_rebalance": ("S4", "S4 Rebalance", "#7c3aed"),
}
HODL_KEY, HODL_LABEL = "benchmark_hodl", "HODL (benchmark)"
VAR_LABELS = {
    "const": "Hằng số",
    "vol_hist_lag": "Historical Volatility (trễ 1 kỳ)",
    "log_vol": "log(Volume)",
    "W": "Range Width (W)",
    "rebalance": "Rebalance",
}


def _fmt_p(p):
    try:
        p = float(p)
    except (TypeError, ValueError):
        return str(p)
    return "<0.001" if p < 0.001 else f"{p:.4f}"


def _cum_note(df):
    last = df.iloc[-1]
    parts = []
    flat, beat = [], []
    hodl = last[HODL_KEY] if HODL_KEY in df else None
    for key, (_, label, _) in SERIES.items():
        if key not in df:
            continue
        v = last[key]
        parts.append(f"{label} {v:.1f} ({v - 100:+.1f}%)")
        if df[key].max() - df[key].min() < 2:
            flat.append(label)
        if hodl is not None and v > hodl:
            beat.append(label)
    lines = ["Giá trị cuối kỳ (gốc = 100): " + "; ".join(parts) + (f"; HODL {hodl:.1f} ({hodl - 100:+.1f}%)." if hodl else ".")]
    if flat:
        lines.append(
            f"{', '.join(flat)} gần như đi ngang quanh mức ban đầu, dấu hiệu vị thế không tạo thêm giá trị (thường do ra ngoài range)."
        )
    if hodl is not None:
        lines.append(
            f"Chiến lược kết thúc cao hơn HODL: {', '.join(beat)}." if beat else "Không chiến lược nào kết thúc cao hơn HODL."
        )
    return lines


def _consistency_issues(df_metrics, df_cum):
    """So tổng lợi nhuận trong bảng với mức thay đổi cuối kỳ của đường cong (gốc 100)."""
    issues = []
    code_to_key = {code: key for key, (code, _, _) in SERIES.items()}
    if "total_return" not in df_metrics or "strategy_name" not in df_metrics:
        return issues
    for _, row in df_metrics.iterrows():
        m = re.search(r"\((S\d)\)", str(row["strategy_name"]))
        key = code_to_key.get(m.group(1)) if m else None
        if key and key in df_cum:
            curve = df_cum[key].iloc[-1] - 100
            if abs(curve - row["total_return"]) > 5:
                issues.append(f"{m.group(1)}: bảng {row['total_return']:+.2f}% ≠ đường cong {curve:+.2f}%")
    return issues


def render_tab3(data_tab3, research_table, style_fig, plot_config, accent_color):
    section_header(
        "SECTION 03",
        "RQ2 · RQ3 · RQ4",
        "Chiến lược LP & Yếu tố quyết định Hiệu quả",
        "Đi từ kết quả đến nguyên nhân: (1) backtest 4 chiến lược LP so với HODL, "
        "(2) hồi quy xác định yếu tố tác động tới lợi nhuận, "
        "(3) kiểm định giả thuyết để đánh giá độ tin cậy.",
        accent_color,
        question="Chiến lược dải giá nào hiệu quả nhất, nhờ yếu tố nào, và kết luận có đủ vững về mặt thống kê không?",
    )

    if not data_tab3:
        st.warning("⚠️ Chưa có dữ liệu JSON cho Tab 3.")
        return

    if data_tab3.get("pool_id"):
        st.caption(f"Cấu hình backtest: pool {data_tab3['pool_id']}.")

    # =====================================================
    # BƯỚC 3.1 — Backtest 4 chiến lược
    # =====================================================
    step_heading(
        "BƯỚC 3.1",
        "Backtest 4 chiến lược LP so với HODL",
        accent_color,
        "Kết quả: chiến lược nào sinh lời tốt hơn và rủi ro ra sao.",
    )

    with st.expander("📚 Công thức chỉ số hiệu suất", expanded=False):
        st.latex(
            r"Sharpe = \frac{\mathbb{E}[R_{LP} - R_f]}{\sigma_{LP}}, \quad "
            r"Sortino = \frac{\mathbb{E}[R_{LP} - R_f]}{\sigma_{downside}}"
        )

    cum_returns = data_tab3.get("cumulative_returns", [])
    df_cum = pd.DataFrame(cum_returns) if cum_returns else pd.DataFrame()
    if not df_cum.empty:
        rename = {k: v[1] for k, v in SERIES.items()}
        rename[HODL_KEY] = HODL_LABEL
        df_plot = df_cum.rename(columns=rename)
        y_cols = [c for c in df_plot.columns if c != "timestamp"]
        color_map = {v[1]: v[2] for v in SERIES.values()}
        color_map[HODL_LABEL] = "#0f172a"
        fig_cum = px.line(
            df_plot, x="timestamp", y=y_cols, color_discrete_map=color_map,
            labels={"value": "Giá trị danh mục (gốc = 100)", "timestamp": "Thời gian", "variable": "Chiến lược"},
        )
        for tr in fig_cum.data:
            if tr.name == HODL_LABEL:
                tr.line.dash = "dash"
        fig_cum.add_hline(y=100, line_dash="dot", line_color="#94a3b8")
        style_fig(fig_cum, "Giá trị danh mục của 4 chiến lược LP vs HODL")
        st.plotly_chart(fig_cum, use_container_width=True, config=plot_config, theme=None)
        chart_note(_cum_note(df_cum), accent_color)

    metrics = data_tab3.get("performance_metrics", [])
    if metrics:
        df_metrics = pd.DataFrame(metrics)
        disp = df_metrics.rename(
            columns={
                "strategy_name": "Chiến lược",
                "total_return": "Tổng lợi nhuận (%)",
                "sharpe_ratio": "Sharpe",
                "sortino_ratio": "Sortino",
                "max_drawdown": "Max Drawdown (%)",
            }
        )
        research_table(disp, accent_color)

        issues = _consistency_issues(df_metrics, df_cum) if not df_cum.empty else []
        if issues:
            st.warning(
                "⚠️ **Bảng chỉ số không khớp đường cong tích lũy** (cùng một file JSON): "
                + "; ".join(issues)
                + ". Cần kiểm tra lại pipeline backtest trước khi dùng các chỉ số này để kết luận."
            )
        else:
            best = best_row_by(df_metrics, "sharpe")
            if best:
                name, value, col = best
                st.success(
                    f"📌 **Kết quả backtest (RQ4):** theo chỉ số {col}, chiến lược tốt nhất là **{name}** "
                    f"(giá trị {value:.3f}). Đối chiếu thêm Sortino và Max Drawdown để đánh giá cả mặt rủi ro."
                )
        chart_note(
            "Sharpe và Sortino đo hiệu quả điều chỉnh theo rủi ro (Sortino chỉ phạt biến động xuống), còn Max Drawdown đo "
            "mức sụt giảm sâu nhất. Không nên xếp hạng chiến lược chỉ theo tổng lợi nhuận.",
            accent_color,
        )

    st.markdown("---")

    # =====================================================
    # BƯỚC 3.2 — Hồi quy
    # =====================================================
    step_heading(
        "BƯỚC 3.2",
        "Hồi quy kinh tế lượng: yếu tố nào quyết định lợi nhuận?",
        accent_color,
        "Giải thích: tác động của biến động giá, volume, độ rộng dải giá và rebalance lên lợi nhuận vượt trội.",
    )

    with st.expander("📚 Phương trình hồi quy cơ sở", expanded=False):
        st.latex(
            r"Y_{i,p,t} = \beta_0 + \beta_1 \sigma_{p,t-1} + \beta_2 \ln(1 + Volume_{p,t-1}) "
            r"+ \beta_3 W_{i,p,t} + \alpha_p + \varepsilon_{i,p,t}"
        )

    reg_output = data_tab3.get("regression_output", {})
    if reg_output:
        if reg_output.get("dependent_variable"):
            st.caption(f"Biến phụ thuộc: {reg_output['dependent_variable']}")
        col_r2, col_adj = st.columns(2)
        col_r2.metric("R² Score", f"{reg_output.get('r_squared', 0):.4f}")
        col_adj.metric("R² Hiệu chỉnh", f"{reg_output.get('adj_r_squared', 0):.4f}")

        coefs = reg_output.get("coefficients", [])
        if coefs:
            df_coef = pd.DataFrame(coefs)
            disp = df_coef.copy()
            if "variable" in disp:
                disp["variable"] = disp["variable"].map(lambda v: VAR_LABELS.get(v, v))
            for col in ("coef", "std_err", "t_stat"):
                if col in disp:
                    disp[col] = disp[col].map(lambda x: f"{x:,.4f}" if col != "t_stat" else f"{x:,.2f}")
            if "p_value" in disp:
                disp["p_value"] = disp["p_value"].map(_fmt_p)
            disp = disp.rename(
                columns={"variable": "Biến", "coef": "Hệ số", "std_err": "Sai số chuẩn", "t_stat": "t-stat", "p_value": "p-value"}
            )
            st.write("**Bảng hệ số hồi quy chi tiết**")
            research_table(disp, accent_color)

            sig, non_sig = [], []
            for _, r in df_coef.iterrows():
                if r.get("variable") == "const":
                    continue
                label = VAR_LABELS.get(r["variable"], r["variable"])
                (sig if r["p_value"] < 0.05 else non_sig).append(
                    f"{label} ({r['coef']:+.3f})" if r["p_value"] < 0.05 else f"{label} (p = {r['p_value']:.3f})"
                )
            lines = []
            if sig:
                lines.append("Có ý nghĩa thống kê ở mức 5%: " + "; ".join(sig) + ".")
            if non_sig:
                lines.append("Không có ý nghĩa: " + "; ".join(non_sig) + ".")
            lines.append(
                f"R² hiệu chỉnh = {reg_output.get('adj_r_squared', 0):.3f}: mô hình tuyến tính trung bình giải thích rất ít "
                "biến thiên lợi nhuận. Hệ số rebalance là mối liên hệ thống kê, chưa chắc là quan hệ nhân quả vì rebalance "
                "thường xảy ra khi thị trường đã bất lợi."
            )
            chart_note(lines, accent_color)
    else:
        st.caption("Chưa có kết quả hồi quy trong file JSON.")

    st.markdown("---")

    # =====================================================
    # BƯỚC 3.3 — Kiểm định
    # =====================================================
    step_heading(
        "BƯỚC 3.3",
        "Kiểm định giả thuyết & chẩn đoán mô hình",
        accent_color,
        "Độ tin cậy: các kiểm định thống kê xác nhận mô hình hồi quy ở bước 3.2 có phù hợp không.",
    )
    tests = data_tab3.get("hypothesis_tests", [])
    if tests:
        df_tests = pd.DataFrame(tests)
        disp = df_tests.rename(
            columns={"test_name": "Kiểm định", "statistic": "Thống kê", "p_value": "p-value", "conclusion": "Kết luận"}
        )
        if "Thống kê" in disp:
            disp["Thống kê"] = disp["Thống kê"].map(lambda x: f"{x:,.2f}")
        if "p-value" in disp:
            disp["p-value"] = disp["p-value"].map(_fmt_p)
        research_table(disp, accent_color)
        if {"test_name", "p_value"} <= set(df_tests.columns):
            lines = [
                f"{r['test_name']}: p-value = {_fmt_p(r['p_value'])} → "
                + ("bác bỏ" if r["p_value"] < 0.05 else "không bác bỏ")
                + " H0 ở mức 5%."
                for _, r in df_tests.iterrows()
            ]
            lines.append("Ý nghĩa thống kê của kiểm định khác với khả năng giải thích tổng thể của mô hình (xem R² hiệu chỉnh ở bước 3.2).")
            chart_note(lines, accent_color)
    else:
        st.caption("Chưa có bảng kiểm định trong file JSON.")

    bridge(
        "TAB 04 · RQ5",
        "Đã biết chiến lược nào hiệu quả và yếu tố nào chi phối. Bước cuối cùng: dùng mô phỏng "
        "Monte Carlo với ràng buộc CVaR để chọn dải giá [Pmin, Pmax] tối ưu.",
        TAB_ACCENTS[4],
    )