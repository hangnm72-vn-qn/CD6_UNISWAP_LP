"""Khối nhận xét ngắn đặt ngay dưới biểu đồ / bảng."""

from html import escape

import streamlit as st


def chart_note(text, accent, title="Nhận xét"):
    """Hiển thị nhận xét. `text` có thể là chuỗi hoặc danh sách các dòng."""
    lines = [text] if isinstance(text, str) else list(text)
    body = "<br>".join(escape(line) for line in lines)
    st.markdown(
        f'<div style="border-left:4px solid {accent}; border-radius:8px; padding:10px 14px; '
        f'margin:6px 0 18px 0; font-size:13.5px; line-height:1.6; color:var(--dashboard-text); '
        f'background:color-mix(in srgb, {accent} 8%, transparent);">'
        f'<b style="color:{accent};">{escape(title)}:</b> {body}</div>',
        unsafe_allow_html=True,
    )