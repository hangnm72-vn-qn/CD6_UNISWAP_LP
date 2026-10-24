"""Thành phần giao diện dùng chung để 4 tab có cùng một khung trình bày.

Mỗi tab đều đi theo trình tự:
    Header (câu hỏi nghiên cứu) -> Khung lý thuyết -> Bước 1..n (kết quả)
    -> Cách đọc kết quả -> Cầu nối sang tab kế tiếp.

Lưu ý: HTML được viết không thụt lề / không có dòng trống để Markdown
không hiểu nhầm thành code block.
"""

from html import escape

import streamlit as st

TAB_ACCENTS = {1: "#2563eb", 2: "#d97706", 3: "#059669", 4: "#7c3aed"}


def section_header(code, rq, title, sub, accent, question=None):
    question_html = (
        f'<div class="section-question"><b>Câu hỏi nghiên cứu:</b> {escape(question)}</div>'
        if question
        else ""
    )
    st.markdown(
        f'<div class="section-header" style="--accent:{accent};">'
        f'<div class="section-meta"><span class="section-code">{escape(code)}</span>'
        f'<span class="section-rq">{escape(rq)}</span></div>'
        f'<div class="section-title">{escape(title)}</div>'
        f'<div class="section-sub">{escape(sub)}</div>'
        f"{question_html}</div>",
        unsafe_allow_html=True,
    )


def step_heading(label, title, accent, desc=None):
    """Tiêu đề từng bước, ví dụ: BƯỚC 2.1 · Phân rã cấu phần PnL."""
    desc_html = f'<div class="step-desc">{escape(desc)}</div>' if desc else ""
    st.markdown(
        f'<div class="step-heading" style="--accent:{accent};">'
        f'<span class="step-badge">{escape(label)}</span>'
        f'<span class="step-title">{escape(title)}</span></div>{desc_html}',
        unsafe_allow_html=True,
    )


def kpi_card(title, value, badge_text, accent, value_color=None):
    color = value_color or accent
    st.markdown(
        f'<div class="kpi-card-saas" style="--pool:{accent};">'
        f'<div class="kpi-title">{title}</div>'
        f'<div class="kpi-value" style="color:{color};">{value}</div>'
        f'<span class="kpi-badge badge-pos">{escape(badge_text)}</span></div>',
        unsafe_allow_html=True,
    )


def bridge(next_code, text, next_accent):
    """Cầu nối logic: kết quả của tab này dẫn tới câu hỏi của tab kế tiếp."""
    st.markdown(
        f'<div class="bridge-box" style="--accent:{next_accent};">'
        f'<span class="bridge-arrow">➜</span>'
        f'<div><div class="bridge-label">TIẾP THEO · {escape(next_code)}</div>'
        f'<div class="bridge-text">{escape(text)}</div></div></div>',
        unsafe_allow_html=True,
    )


def format_number(value, prefix="", suffix="", decimals=2):
    try:
        return f"{prefix}{float(value):,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def best_row_by(df, keyword):
    """Tìm hàng có giá trị lớn nhất ở cột có tên chứa `keyword` (không phân biệt hoa/thường).

    Trả về (tên dòng, giá trị, tên cột) hoặc None nếu không tìm được.
    """
    import pandas as pd

    for col in df.columns:
        if keyword in str(col).lower():
            numeric = pd.to_numeric(df[col], errors="coerce")
            if numeric.notna().any():
                idx = numeric.idxmax()
                return df.loc[idx, df.columns[0]], numeric[idx], col
    return None