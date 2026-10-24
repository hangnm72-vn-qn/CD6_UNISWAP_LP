from html import escape
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.components.components import section_header, step_heading
from dashboard.views.tab1 import render_tab1
from dashboard.views.tab2 import render_tab2
from dashboard.views.tab3 import render_tab3
from dashboard.views.tab4 import render_tab4
from src.features.build_features import (
    OUTPUT_FIGURES_DIR,
    OUTPUT_TABLES_DIR,
    ensure_market_features,
    prepare_daily_data,
)
from src.models.optimizer import run_regressions
from src.evaluation.backtest import export_backtest_results, run_backtest

# ---------------------------------------------------------
# 1. CẤU HÌNH TRANG STREAMLIT
# ---------------------------------------------------------
st.set_page_config(
    page_title="Uniswap v3 LP Analytics",
    page_icon="🦄",
    layout="wide",
    initial_sidebar_state="expanded",
)

POOL_MAPPING = {
    "P1: WETH/USDC 0.05%": "WETH-USDC-005",
    "P2: WETH/USDC 0.30%": "WETH-USDC-030",
    "P3: WETH/USDT 0.30%": "WETH-USDT-030",
    "P4: WBTC/WETH 0.05%": "WBTC-WETH-005",
    "P5: USDC/USDT 0.01%": "USDC-USDT-001",
}

POOL_COLORS = {
    "P1: WETH/USDC 0.05%": "#2563eb",
    "P2: WETH/USDC 0.30%": "#d97706",
    "P3: WETH/USDT 0.30%": "#059669",
    "P4: WBTC/WETH 0.05%": "#dc2626",
    "P5: USDC/USDT 0.01%": "#7c3aed",
}

TAB_ACCENTS = {1: "#2563eb", 2: "#d97706", 3: "#059669", 4: "#7c3aed"}
TAB_ACTIVE_COLORS = {
    1: "#1d4ed8",
    2: "#92400e",
    3: "#065f46",
    4: "#5b21b6",
}

# ---------------------------------------------------------
# 2. HÀM LOAD DỮ LIỆU CSV LỊCH SỬ & JSON TỪ TV5
# ---------------------------------------------------------
@st.cache_data
def load_csv_data():
    path = PROJECT_ROOT / "data" / "processed" / "pools_daily.csv"
    if not path.is_file():
        st.error(f"Không tìm thấy dữ liệu lịch sử: {path}")
        return pd.DataFrame()

    try:
        raw_df = pd.read_csv(path)
        if "pool_name" in raw_df.columns:
            raw_df["_dashboard_pool_code"] = raw_df["pool_name"]
        elif "pool_id" in raw_df.columns:
            raw_df["_dashboard_pool_code"] = raw_df["pool_id"]

        df = prepare_daily_data(raw_df)
        if "_dashboard_pool_code" in df.columns:
            df["pool_code"] = df["_dashboard_pool_code"]
            df = df.drop(columns="_dashboard_pool_code")
        else:
            df["pool_code"] = df["pool_id"]

        df = ensure_market_features(df)
        df["date"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None)
        df["close_price"] = df["price"]
        df["tvl_usd"] = df["tvl"]
        df["volume_usd"] = df["volume"]
        df["fee_usd"] = df["feesUSD"] if "feesUSD" in df.columns else 0.0
    except (OSError, ValueError, pd.errors.ParserError, KeyError) as exc:
        st.error(f"Không thể đọc hoặc chuẩn hóa dữ liệu {path}: {exc}")
        return pd.DataFrame()

    df = df.sort_values(["pool_code", "date"])
    df["log_ret"] = df["ret"]
    df["volatility_7d"] = df.groupby("pool_code")["log_ret"].transform(
        lambda x: x.rolling(7).std() * np.sqrt(365) * 100
    )
    df["volume_tvl_ratio"] = np.where(
        df["tvl_usd"] > 0, df["volume_usd"] / df["tvl_usd"], 0
    )

    return df


@st.cache_data
def load_json_data(filename):
    file_path = OUTPUT_TABLES_DIR / filename
    if not file_path.is_file():
        return None, f"Không tìm thấy: {file_path}"
    try:
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"Không thể đọc {file_path}: {exc}"


# Nạp dữ liệu vào các biến toàn cục
df_daily = load_csv_data()
data_tab2, tab2_error = load_json_data("tab2_return_decomposition.json")
data_tab3, tab3_error = load_json_data("tab3_strategy_backtest.json")
data_tab4, tab4_error = load_json_data("tab4_lp_optimizer.json")
for tab_data, error in (
    (data_tab2, tab2_error),
    (data_tab3, tab3_error),
    (data_tab4, tab4_error),
):
    if tab_data is None:
        st.warning(error)

# ---------------------------------------------------------
# 3. SETUP THEME SÁNG / TỐI & CSS GIAO DIỆN
# ---------------------------------------------------------
if "is_dark" not in st.session_state:
    st.session_state.is_dark = False

is_dark = st.session_state.is_dark
plotly_template = "plotly_dark" if is_dark else "plotly_white"


def toggle_theme():
    st.session_state.is_dark = not st.session_state.is_dark


bg_app = "#0b1220" if is_dark else "#f4f6fa"
bg_sidebar = "#111a2e" if is_dark else "#ffffff"
bg_card = "#16213a" if is_dark else "#ffffff"
bg_input = "#1c2a47" if is_dark else "#e2e8f0"
text_main = "#ffffff" if is_dark else "#0f172a"
text_sub = "#a5b4cc" if is_dark else "#334155"
border_color = "#2b3a57" if is_dark else "#cbd5e1"
grid_color = "#27375a" if is_dark else "#e6eaf1"
table_head_bg = "#1d2b4a" if is_dark else "#eef2f8"
table_row_alt = (
    "rgba(255,255,255,0.03)" if is_dark else "rgba(15,23,42,0.025)"
)
table_row_hover = (
    "rgba(255,255,255,0.07)" if is_dark else "rgba(15,23,42,0.06)"
)
tab_bg_normal = "#16213a" if is_dark else "#ffffff"
tab_text_normal = "#ffffff" if is_dark else "#0f172a"
tab_border_normal = "#3b4d70" if is_dark else "#64748b"
tab_shadow = (
    "0 4px 12px rgba(0,0,0,0.45)"
    if is_dark
    else "0 4px 12px rgba(15,23,42,0.08)"
)
chip_bg = "rgba(255,255,255,0.07)" if is_dark else "rgba(15,23,42,0.05)"
toggle_label = "☀️" if is_dark else "🌙"
sidebar_header_color = "#60a5fa" if is_dark else "#1e40af"

# ---------------------------------------------------------
# ĐIỀU HƯỚNG SIDEBAR (4 tab + phụ lục)
# ---------------------------------------------------------
NAV_ITEMS = {
    1: "01 · Bối cảnh Thị trường",
    2: "02 · Phân rã Lợi nhuận",
    3: "03 · Chiến lược & Kinh tế lượng",
    4: "04 · Tối ưu Dải giá",
    5: "📎 Phụ lục",
}
NAV_COLORS = {**TAB_ACTIVE_COLORS, 5: "#475569"}

if "page" not in st.session_state:
    st.session_state.page = 1

# Giữ lại lựa chọn pool / ngày khi chuyển trang (widget ngoài màn hình sẽ bị Streamlit xoá state)
for _k in ("tab1_pool", "tab1_dates"):
    if _k in st.session_state:
        st.session_state[_k] = st.session_state[_k]

nav_css = ""
for _i, _color in NAV_COLORS.items():
    _active = st.session_state.page == _i
    _bg = _color if _active else "transparent"
    _fg = "#ffffff" if _active else "var(--dashboard-text)"
    nav_css += f"""
    section[data-testid="stSidebar"] .st-key-nav_{_i} button {{
        width: 100% !important; min-height: 50px !important; justify-content: flex-start !important;
        text-align: left !important; padding: 8px 14px !important; border-radius: 10px !important;
        border: 1.5px solid {_color if _active else "var(--dashboard-border)"} !important;
        border-left: 7px solid {_color} !important;
        background: {_bg} !important;
        box-shadow: {"0 6px 16px " + _color + "55" if _active else "none"} !important;
    }}
    section[data-testid="stSidebar"] .st-key-nav_{_i} button p {{
        color: {_fg} !important; font-weight: {900 if _active else 700} !important;
        font-size: 15px !important; text-align: left !important;
    }}
    """

tab_css = ""
for i, color in TAB_ACTIVE_COLORS.items():
    tab_css += f"""
    div[data-baseweb="tab-list"] button:nth-of-type({i}) {{
        border-top: 5px solid {color} !important;
    }}
    div[data-baseweb="tab-list"] button[aria-selected="true"]:nth-of-type({i}) {{
        background: {color} !important;
        border-color: {color} !important;
        box-shadow: 0 6px 18px {color}55 !important;
    }}
    """

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Source+Serif+4:opsz,wght@8..60,500;8..60,700;8..60,800&family=JetBrains+Mono:wght@500;700&display=swap');

    :root {{
        --dashboard-background: {bg_app};
        --dashboard-surface: {bg_card};
        --dashboard-sidebar: {bg_sidebar};
        --dashboard-input: {bg_input};
        --dashboard-text: {text_main};
        --dashboard-muted: {text_sub};
        --dashboard-border: {border_color};
        --dashboard-grid: {grid_color};
        --dashboard-table-head: {table_head_bg};
        --dashboard-tab: {tab_bg_normal};
        --dashboard-tab-text: {tab_text_normal};
        --dashboard-tab-border: {tab_border_normal};
        --dashboard-shadow: {tab_shadow};
    }}

    html, body, .stApp {{
        font-family: 'Inter', sans-serif !important;
        background-color: var(--dashboard-background, var(--background-color, {bg_app})) !important;
        color: var(--dashboard-text, var(--text-color, {text_main})) !important;
    }}

    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"] {{
        color: var(--dashboard-text, var(--text-color, {text_main})) !important;
    }}

    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stCaptionContainer"],
    [data-testid="stWidgetLabel"] p,
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"] {{
        color: var(--dashboard-text, var(--text-color, {text_main}));
    }}

    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3,
    [data-testid="stMarkdownContainer"] h4,
    [data-testid="stMarkdownContainer"] h5,
    [data-testid="stMarkdownContainer"] h6 {{
        color: var(--dashboard-text, var(--text-color, {text_main})) !important;
    }}

    header[data-testid="stHeader"] {{
        background-color: transparent !important;
        height: 0px !important;
        min-height: 0px !important;
    }}

    .block-container {{
        padding-top: 1rem !important;
        padding-bottom: 2rem !important;
        max-width: 1400px !important;
    }}

    section[data-testid="stSidebar"] {{
        background-color: var(--dashboard-sidebar, var(--secondary-background-color, {bg_sidebar})) !important;
        border-right: 1px solid var(--dashboard-border, {border_color}) !important;
    }}

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {{
        color: {sidebar_header_color} !important;
        font-weight: 800 !important;
        font-size: 20px !important;
    }}

    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    section[data-testid="stSidebar"] label p {{
        font-family: 'Inter', sans-serif !important;
        font-size: 12px !important;
        font-weight: 800 !important;
        color: var(--dashboard-text, var(--text-color, {text_main})) !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}

    section[data-testid="stSidebar"] div[data-baseweb="select"] > div,
    section[data-testid="stSidebar"] div[data-baseweb="input"],
    section[data-testid="stSidebar"] div[data-baseweb="base-input"],
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    [data-testid="stNumberInput"] div[data-baseweb="input"],
    [data-testid="stDateInput"] div[data-baseweb="input"] {{
        background-color: var(--dashboard-input, var(--secondary-background-color, {bg_input})) !important;
        border: 1.5px solid var(--dashboard-border, {border_color}) !important;
        border-radius: 10px !important;
        min-height: 42px !important;
    }}

    section[data-testid="stSidebar"] input,
    section[data-testid="stSidebar"] div[data-baseweb="select"] *,
    [data-testid="stSelectbox"] div[data-baseweb="select"] *,
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input {{
        background-color: transparent !important;
        color: var(--dashboard-text, var(--text-color, {text_main})) !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 14px !important;
        font-weight: 800 !important;
    }}

    [data-testid="stSelectbox"] svg,
    [data-testid="stNumberInput"] button,
    [data-testid="stDateInput"] button {{
        color: var(--dashboard-text, var(--text-color, {text_main})) !important;
        fill: var(--dashboard-text, var(--text-color, {text_main})) !important;
    }}

    [data-testid="stButton"] button,
    [data-testid="stDownloadButton"] button {{
        color: var(--dashboard-text, var(--text-color, {text_main})) !important;
        background-color: var(--dashboard-surface, var(--secondary-background-color, {bg_card})) !important;
        border: 1.5px solid var(--dashboard-border, {border_color}) !important;
        font-weight: 700 !important;
        transition: background-color 120ms ease, border-color 120ms ease, transform 120ms ease;
    }}

    [data-testid="stButton"] button:hover,
    [data-testid="stDownloadButton"] button:hover {{
        border-color: #2563eb !important;
        background-color: var(--dashboard-input, var(--secondary-background-color, {bg_input})) !important;
    }}

    [data-testid="stButton"] button:focus-visible,
    [data-testid="stDownloadButton"] button:focus-visible {{
        outline: 3px solid #2563eb !important;
        outline-offset: 2px !important;
    }}

    div.st-key-theme_toggle {{
        position: fixed !important;
        top: 12px !important;
        right: 24px !important;
        z-index: 999 !important;
        width: 44px !important;
        height: 44px !important;
    }}

    div.st-key-theme_toggle button {{
        width: 44px !important;
        height: 44px !important;
        min-height: 44px !important;
        padding: 0 !important;
        border-radius: 50% !important;
        background-color: var(--dashboard-surface, var(--secondary-background-color, {bg_card})) !important;
        border: 2px solid var(--dashboard-border, {border_color}) !important;
        box-shadow: var(--dashboard-shadow, {tab_shadow}) !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }}

    div.st-key-theme_toggle button p {{
        font-size: 20px !important;
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1 !important;
    }}

    div[data-baseweb="tab-highlight"],
    div[data-baseweb="tab-border"] {{ display: none !important; }}

    div[data-baseweb="tab-list"], div[role="tablist"] {{
        display: flex !important;
        width: 100% !important;
        gap: 12px !important;
        background-color: transparent !important;
        padding: 6px 0px 18px 0px !important;
        border: none !important;
    }}

    div[data-baseweb="tab-list"] button,
    button[role="tab"],
    [data-testid="stTabs"] [role="tab"] {{
        flex: 1 1 0 !important;
        min-height: 56px !important;
        padding: 10px 16px !important;
        background-color: var(--dashboard-tab, var(--secondary-background-color, {tab_bg_normal})) !important;
        border: 2px solid var(--dashboard-tab-border, {tab_border_normal}) !important;
        border-radius: 12px !important;
        box-shadow: var(--dashboard-shadow, {tab_shadow}) !important;
        opacity: 1 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }}

    div[data-baseweb="tab-list"] button p,
    button[role="tab"] p,
    [data-testid="stTabs"] [role="tab"] p,
    div[data-baseweb="tab-list"] button span,
    button[role="tab"] span {{
        color: var(--dashboard-tab-text, var(--text-color, {tab_text_normal})) !important;
        font-weight: 800 !important;
        font-size: 18px !important;
        opacity: 1 !important;
        white-space: nowrap !important;
    }}

    div[data-baseweb="tab-list"] button[aria-selected="true"] p,
    button[role="tab"][aria-selected="true"] p,
    div[data-baseweb="tab-list"] button[aria-selected="true"] span,
    button[role="tab"][aria-selected="true"] span {{
        color: #ffffff !important;
        font-weight: 900 !important;
        font-size: 19px !important;
    }}
    {tab_css}
    {nav_css}

    .hero-banner-container {{
        background: linear-gradient(135deg, #2e1065 0%, #4c0519 50%, #0f172a 100%),
                    url('https://images.unsplash.com/photo-1639762681485-074b7f938ba0?q=80&w=1200&auto=format&fit=crop');
        background-size: cover; background-position: center; background-blend-mode: overlay;
        border-radius: 20px; padding: 32px 40px; color: #ffffff !important; margin-bottom: 20px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); border: 1px solid rgba(255, 255, 255, 0.15);
        display: flex; justify-content: space-between; align-items: center;
    }}

    .hero-tag-box {{
        background: rgba(236, 72, 153, 0.3); color: #f472b6 !important; border: 1px solid rgba(236, 72, 153, 0.5);
        padding: 4px 14px; border-radius: 20px; font-size: 13px; font-weight: 800; display: inline-block; margin-bottom: 12px;
    }}

    .hero-title-text {{ font-family: 'Source Serif 4', Georgia, serif; font-size: 30px; font-weight: 800; margin: 0 0 8px 0; line-height: 1.25; color: #ffffff !important; }}
    .hero-subtitle-text {{ font-size: 15px; color: #e2e8f0 !important; margin: 0; max-width: 680px; line-height: 1.5; font-weight: 500; }}

    .kpi-card-saas {{
        background-color: var(--dashboard-surface, var(--secondary-background-color, {bg_card})) !important;
        border: 1px solid var(--dashboard-border, {border_color}) !important;
        border-top: 5px solid var(--pool) !important; border-radius: 14px; padding: 18px 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }}
    .kpi-title {{ font-size: 12px; color: {text_sub} !important; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; }}
    .kpi-value {{ font-family: 'JetBrains Mono', monospace; font-size: 28px; font-weight: 700; margin: 6px 0; }}
    .kpi-badge {{ font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 6px; display: inline-block; }}
    .badge-pos {{ background: #dcfce7; color: #15803d !important; }}

    .pool-chip {{
        background: var(--dashboard-surface, var(--secondary-background-color, {bg_card}));
        border: 1px solid var(--dashboard-border, {border_color});
        border-left: 4px solid var(--c);
        border-radius: 10px;
        padding: 12px 14px;
    }}

    .section-header {{
        background: var(--dashboard-surface, var(--secondary-background-color, {bg_card}));
        border: 1px solid var(--dashboard-border, {border_color}); border-left: 8px solid var(--accent);
        border-radius: 14px; padding: 22px 28px; margin: 4px 0 22px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }}
    .section-meta {{ display: flex; gap: 10px; align-items: center; margin-bottom: 8px; }}
    .section-code {{
        font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700;
        color: #ffffff; background: var(--accent); padding: 3px 10px; border-radius: 6px; letter-spacing: 0.5px;
    }}
    .section-rq {{
        font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700;
        color: var(--accent); border: 1.5px solid var(--accent); padding: 2px 10px; border-radius: 6px;
    }}
    .section-title {{
        font-family: 'Source Serif 4', Georgia, serif; font-size: 28px; font-weight: 800;
        color: var(--dashboard-text, var(--text-color, {text_main})); line-height: 1.2; margin-bottom: 6px;
    }}
    .section-sub {{ font-size: 14.5px; color: var(--dashboard-muted, var(--text-color, {text_sub})); line-height: 1.6; max-width: 900px; }}

    .table-wrap {{
        background: var(--dashboard-surface, var(--secondary-background-color, {bg_card}));
        border: 1px solid var(--dashboard-border, {border_color}); border-top: 5px solid var(--accent);
        border-radius: 14px; overflow-x: auto; box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }}
    .research-table {{ width: 100%; border-collapse: collapse; font-size: 14px; color: var(--dashboard-text, var(--text-color, {text_main})); }}
    .research-table thead th {{
        background: var(--dashboard-table-head, var(--secondary-background-color, {table_head_bg}));
        color: var(--dashboard-muted, var(--text-color, {text_sub})); text-align: right;
        font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px;
        padding: 14px 18px; border-bottom: 2px solid var(--dashboard-border, {border_color}); white-space: nowrap;
    }}
    .research-table thead th:first-child {{ text-align: left; }}
    .research-table tbody td {{ padding: 13px 18px; border-bottom: 1px solid var(--dashboard-border, {border_color}); color: var(--dashboard-text, var(--text-color, {text_main})); }}
    .research-table tbody tr:last-child td {{ border-bottom: none; }}
    .research-table tbody tr:nth-child(even) {{ background: {table_row_alt}; }}
    .research-table tbody tr:hover {{ background: {table_row_hover}; }}
    .research-table td.c-first {{ font-weight: 700; text-align: left; }}
    .research-table td.c-num {{ font-family: 'JetBrains Mono', monospace; font-weight: 500; text-align: right; }}
    .research-table tr.row-active td {{
        background: color-mix(in srgb, var(--accent) 14%, transparent) !important; font-weight: 700;
    }}
    .research-table tr.row-active td.c-first {{ box-shadow: inset 5px 0 0 var(--accent); }}

    div[data-testid="stPlotlyChart"] {{
        background: var(--dashboard-surface, var(--secondary-background-color, {bg_card}));
        border: 1px solid var(--dashboard-border, {border_color}); border-radius: 14px;
        padding: 6px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }}
    .section-question {{
        margin-top: 12px; padding: 10px 14px; border-radius: 10px; font-size: 14px; line-height: 1.5;
        color: var(--dashboard-text, {text_main});
        background: color-mix(in srgb, var(--accent) 10%, transparent);
        border: 1px dashed var(--accent);
    }}

    .step-heading {{
        display: flex; align-items: center; gap: 12px; margin: 18px 0 6px 0;
        padding-bottom: 8px; border-bottom: 2px solid var(--dashboard-border, {border_color});
    }}
    .step-badge {{
        font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700; white-space: nowrap;
        color: #ffffff; background: var(--accent); padding: 4px 10px; border-radius: 6px; letter-spacing: 0.5px;
    }}
    .step-title {{
        font-family: 'Source Serif 4', Georgia, serif; font-size: 21px; font-weight: 800;
        color: var(--dashboard-text, {text_main});
    }}
    .step-desc {{ font-size: 13.5px; color: var(--dashboard-muted, {text_sub}); margin: 0 0 14px 2px; line-height: 1.55; }}

    .bridge-box {{
        display: flex; align-items: center; gap: 16px; margin: 26px 0 8px 0; padding: 16px 20px;
        background: var(--dashboard-surface, {bg_card});
        border: 1px solid var(--dashboard-border, {border_color}); border-left: 8px solid var(--accent);
        border-radius: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }}
    .bridge-arrow {{ font-size: 28px; font-weight: 900; color: var(--accent); }}
    .bridge-label {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700; color: var(--accent); letter-spacing: 0.6px; }}
    .bridge-text {{ font-size: 14.5px; color: var(--dashboard-text, {text_main}); line-height: 1.55; margin-top: 2px; }}

    </style>
    """,
    unsafe_allow_html=True,
)

# NÚT THEME
st.button(toggle_label, key="theme_toggle", on_click=toggle_theme)

# ---------------------------------------------------------
# 4. CẤU HÌNH SIDEBAR (THANH BÊN)
# ---------------------------------------------------------
st.sidebar.markdown(
    """
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 20px;">
        <img src="https://raw.githubusercontent.com/uniswap/assets/master/blockchains/ethereum/assets/0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984/logo.png" width="38"/>
        <div>
            <div style="font-size: 20px; font-weight: 800; color: #ec4899; line-height: 1.1;">UniLens v3</div>
            <div style="font-size: 11px; color: #64748b; font-weight: 600;">LIQUIDITY ANALYTICS</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown(
    '<div style="font-size:11px; font-weight:800; letter-spacing:0.8px; color:#64748b; margin:4px 0 8px 2px;">ĐIỀU HƯỚNG NGHIÊN CỨU</div>',
    unsafe_allow_html=True,
)


def set_page(page_id):
    st.session_state.page = page_id


for _i, _label in NAV_ITEMS.items():
    if _i == 5:
        st.sidebar.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    st.sidebar.button(
        _label,
        key=f"nav_{_i}",
        on_click=set_page,
        args=(_i,),
        use_container_width=True,
    )


# ---------------------------------------------------------
# 5. HÀM HELPER VẼ BẢNG VÀ BIỂU ĐỒ
# ---------------------------------------------------------
def research_table(df, accent, target_pool_name=None):
    head = "".join(f"<th>{escape(str(c))}</th>" for c in df.columns)
    body = ""
    for _, row in df.iterrows():
        is_active = (target_pool_name is not None) and (
            str(row.iloc[0]) == target_pool_name
        )
        cls = "row-active" if is_active else ""
        cells = "".join(
            f'<td class="{"c-first" if i == 0 else "c-num"}">{escape(str(v))}</td>'
            for i, v in enumerate(row)
        )
        body += f'<tr class="{cls}">{cells}</tr>'
    st.markdown(
        f"""<div class="table-wrap" style="--accent:{accent};">
            <table class="research-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
        </div>""",
        unsafe_allow_html=True,
    )


def style_fig(fig, title, line_color=None):
    fig.update_layout(
        template=plotly_template,
        paper_bgcolor=bg_card,
        plot_bgcolor=bg_card,
        font=dict(family="Inter, sans-serif", color=text_main, size=12),
        title=dict(
            text=title,
            x=0.02,
            xanchor="left",
            font=dict(
                family="Source Serif 4, Georgia, serif",
                size=14,
                color=text_main,
            ),
        ),
        margin=dict(l=20, r=20, t=48, b=20),
        legend=dict(font=dict(color=text_main)),
        hoverlabel=dict(font=dict(color=text_main), bgcolor=bg_card, bordercolor=border_color),
    )
    # Đặt màu chữ/tick/tiêu đề trục tường minh để luôn đọc được ở cả giao diện sáng và tối
    axis_style = dict(
        gridcolor=grid_color,
        linecolor=border_color,
        zerolinecolor=border_color,
        showline=True,
        tickfont=dict(color=text_main, size=12),
        title_font=dict(color=text_main, size=13),
    )
    fig.update_xaxes(**axis_style)
    fig.update_yaxes(**axis_style)
    if line_color:
        fig.for_each_trace(
            lambda trace: trace.update(line=dict(color=line_color, width=2.4))
            if hasattr(trace, "line") and trace.type == "scatter"
            else None
        )
    return fig


def render_output_figure(filename, caption):
    image_path = OUTPUT_FIGURES_DIR / filename
    if image_path.is_file():
        with st.expander(caption):
            st.image(str(image_path), use_container_width=True)


PLOT_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}

# BANNER HEAD
st.markdown(
    """
    <div class="hero-banner-container">
        <div>
            <div class="hero-tag-box">✨ Uniswap v3 Quantitative Research Framework</div>
            <div class="hero-title-text">Đánh giá Hiệu quả Cung cấp Thanh khoản Tập trung & Tối ưu Vùng giá trên Uniswap v3</div>
        </div>
        <div style="padding-right: 15px;">
            <img src="https://raw.githubusercontent.com/uniswap/assets/master/blockchains/ethereum/assets/0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984/logo.png" width="110" style="filter: drop-shadow(0 0 20px rgba(236, 72, 153, 0.9));"/>
        </div>
    </div>
""",
    unsafe_allow_html=True,
)

def render_appendix():
    accent = NAV_COLORS[5]
    section_header(
        "PHỤ LỤC",
        "APPENDIX",
        "Hình xuất từ Notebook & Công cụ Tính lại",
        "Tài liệu bổ trợ cho các tab phân tích: hình gốc xuất từ notebook và công cụ chạy lại backtest, hồi quy từ dữ liệu đã xử lý.",
        accent,
    )

    step_heading("PHỤ LỤC A", "Hình xuất từ notebook", accent, "Ảnh gốc phục vụ đối chiếu với kết quả ở Tab 02 và Tab 03.")
    render_output_figure(
        "figure_4_3_decomposition.png",
        "Phân rã lợi nhuận (Figure 4.3) · liên quan Tab 02",
    )
    render_output_figure(
        "figure_4_5_equity_curves.png",
        "Đường cong hiệu suất (Figure 4.5) · liên quan Tab 03",
    )

    st.markdown("---")
    step_heading("PHỤ LỤC B", "Tính lại backtest và mô hình", accent, "Chỉ chạy khi bấm nút; kết quả CSV được lưu vào outputs/tables/.")
    if st.button(
        "Chạy backtest và hồi quy",
        disabled=df_daily.empty,
        key="recompute_analysis",
    ):
        with st.spinner("Đang chạy backtest và các mô hình hồi quy..."):
            ledger, decompositions, metrics = run_backtest(df_daily)
            export_backtest_results(ledger, decompositions, metrics)
            _, panel_results, quantile_results, ols_model = run_regressions(
                df_daily, ledger
            )
        st.success(f"Đã lưu kết quả. Panel OLS R² = {ols_model.rsquared:.4f}")
        st.write("Chỉ số backtest")
        st.dataframe(metrics, use_container_width=True)
        st.write("Panel fixed-effects")
        st.dataframe(panel_results, use_container_width=True)
        st.write("Quantile regression")
        st.dataframe(quantile_results, use_container_width=True)


# ---------------------------------------------------------
# 6. ĐỊNH TUYẾN TRANG THEO NÚT Ở SIDEBAR
# ---------------------------------------------------------
page = st.session_state.page

if page == 1:
    render_tab1(
        df_daily,
        POOL_MAPPING,
        POOL_COLORS,
        research_table,
        style_fig,
        PLOT_CONFIG,
        TAB_ACCENTS[1],
    )
elif page == 2:
    render_tab2(data_tab2, research_table, style_fig, PLOT_CONFIG, TAB_ACCENTS[2])
elif page == 3:
    render_tab3(data_tab3, research_table, style_fig, PLOT_CONFIG, TAB_ACCENTS[3])
elif page == 4:
    render_tab4(
        data_tab4, research_table, style_fig, PLOT_CONFIG, TAB_ACCENTS[4], text_main
    )
else:
    render_appendix()