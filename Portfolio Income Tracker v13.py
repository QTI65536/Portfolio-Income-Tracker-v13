import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import time

# --- 1. CONFIG & STYLING ---
st.set_page_config(layout="wide", page_title="Income Portfolio Tracker by QTI")

st.markdown("""
    <style>
    [data-testid="stMetricLabel"] > div { font-size: 26px !important; font-weight: 800 !important; color: #333 !important; }
    [data-testid="stMetricValue"] > div { font-size: 44px !important; font-weight: 900 !important; color: #2c3e50 !important; }
    .stTabs [data-baseweb="tab"] p { font-size: 28px !important; font-weight: 700 !important; }
    .master-title { font-size: 52px !important; color: #2c3e50; font-weight: 900; border-bottom: 3px solid #2ecc71; padding-bottom: 10px; }
    .app-branding { font-size: 22px !important; color: #7f8c8d; font-weight: 400; margin-bottom: -10px; }
    
    .stButton > button { 
        background-color: #2ecc71 !important; color: white !important;
        font-weight: 900 !important; font-size: 22px !important; border-radius: 8px !important;
        height: 3.8rem !important; width: 100% !important; text-transform: uppercase !important;
        border: 2px solid white !important; transition: all 0.2s ease !important;
    }
    .stDownloadButton > button { 
        background-color: #007bff !important; color: white !important;
        font-weight: 900 !important; font-size: 22px !important; border-radius: 8px !important;
        height: 3.8rem !important; width: 100% !important; text-transform: uppercase !important;
        border: 2px solid white !important; transition: all 0.2s ease !important;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        transform: scale(1.02); box-shadow: 0 4px #999;
    }

    .html-table-container { width: 100%; overflow-x: auto; margin-top: 10px; }
    .gold-table { width: 100%; border-collapse: collapse; font-size: 22px !important; font-family: sans-serif; }
    .gold-table th { background-color: #f8f9fa; color: #2c3e50; font-size: 24px !important; text-align: left; padding: 16px; border-bottom: 3px solid #2ecc71; }
    .gold-table td { padding: 16px; border-bottom: 1px solid #dee2e6; color: #333; }
    .gold-table tr:hover { background-color: #f1f1f1; }
    .tk-bold { font-weight: 900; color: #2c3e50; }
    label { font-size: 18px !important; font-weight: bold !important; }
    </style>
    """, unsafe_allow_html=True)

HOVER_STYLE = dict(bgcolor="white", font_size=16, font_family="Arial", bordercolor="#2ecc71")
HARDCODED_CEFS = {'ADX', 'AIO', 'ASGI', 'BME', 'BST', 'BUI', 'CSQ', 'DNP', 'EOS', 'ERH', 'GDV', 'GLU', 'GOF', 'NBXG', 'NIE', 'PCN', 'PDI', 'PDO', 'PDX', 'RFI', 'RLTY', 'RNP', 'RQI', 'STK', 'UTF', 'UTG'}
MREIT_SYMBOLS = {'NLY', 'AGNC', 'ORC', 'DX', 'ARR', 'TWO', 'IVR', 'MITT', 'NYMT', 'CIM', 'EARN', 'ABR', 'RITM'}
CASH_SYMBOLS = {'FDRXX', 'SPAXX', 'VMFXX', 'VUSTX', 'SPRXX'}

def get_color_style(val):
    if val > 0.001: return 'style="color: #27ae60; font-weight: bold;"'
    if val < -0.001: return 'style="color: #e74c3c; font-weight: bold;"'
    return 'style="color: #333;"'

def clean_numeric(value):
    try:
        if pd.isna(value) or value == "": return 0.0
        return float(str(value).replace('$', '').replace(',', '').strip())
    except: return 0.0

def strip_ext(filename):
    return filename.rsplit('.', 1)[0] if '.' in filename else filename

# --- 3. UPDATED DATA ENGINE (CLOUD-RESILIENT) ---
@st.cache_data(ttl=3600)
def get_unified_data(tickers):
    if not tickers: return {}
    try:
        # Reduced period to 1mo to minimize Cloud IP blocking
        raw_data = yf.download(tickers, period="1mo", actions=True, auto_adjust=True, progress=False)
        if raw_data.empty:
            st.toast("⚠️ Connection to Yahoo Finance blocked. Try refreshing.", icon="🚨")
            return {}
    except Exception as e:
        return {}

    meta = {}
    for t in tickers:
        try:
            t_prices = raw_data.xs(t, level=1, axis=1) if len(tickers) > 1 else raw_data
            valid_c = t_prices['Close'].dropna()
            
            if valid_c.empty:
                lat, prev = 0.0, 0.0
            else:
                lat = float(valid_c.iloc[-1])
                prev = float(valid_c.iloc[-2]) if len(valid_c) > 1 else lat
            
            div_h = t_prices['Dividends'].dropna()
            div_h = div_h[div_h > 0]
            
            tk = yf.Ticker(t)
            # Use fast_info (metadata) instead of full .info scrape to bypass blocks
            f_info = tk.fast_info
            
            div_r = f_info.get('last_dividend', 0)
            if (div_r is None or div_r == 0) and not div_h.empty:
                div_r = float(div_h[div_h.index > (datetime.now() - timedelta(days=365))].sum())
            
            # Use a limited info block for sector/payout
            try:
                full_info = tk.info
            except:
                full_info = {}

            sumry = full_info.get('longBusinessSummary', '').lower()
            is_cef = t in HARDCODED_CEFS or "closed-end" in sumry
            sector = "Cash / Reserves" if t in CASH_SYMBOLS else (full_info.get('sector', 'CEF' if is_cef else 'Other'))

            reasons = []
            if t in CASH_SYMBOLS: pass
            elif t in MREIT_SYMBOLS:
                reasons.append("Structural mREIT Risk")
                if lat > 0 and (div_r / lat) > 0.10: reasons.append("Yield >10%")
            else:
                payout = full_info.get('payoutRatio', 0) or 0
                if payout > 0.75: reasons.append("EPS Payout")

            tier = "Tier 1: ✅ SAFE"
            if len(reasons) >= 2: tier = "Tier 3: 🚨 RISK"
            elif len(reasons) == 1: tier = "Tier 2: ⚠️ STABLE"

            meta[t] = {
                'price': lat, 'change_val': lat - prev, 
                'change_pct': (((lat - prev) / prev) * 100) if prev > 0 else 0,
                'div': div_r, 'freq': 12 if len(div_h) > 6 else 4, 
                'ex_date': full_info.get('exDividendDate'),
                'sector': sector, 'safety': tier, 'reasons': ", ".join(reasons)
            }
        except Exception as e:
            meta[t] = {'price': 0.0, 'change_val': 0.0, 'change_pct': 0.0, 'div': 0.0, 'freq': 4, 'ex_date': None, 'sector': 'Unknown', 'safety': 'Tier 3', 'reasons': 'Data Error'}
    return meta

# --- REST OF THE APP LOGIC ---
if 'portfolios' not in st.session_state: st.session_state.portfolios = {}

with st.sidebar:
    st.header("📂 Portfolio Vault")
    up = st.file_uploader("Upload CSV Files", type="csv", accept_multiple_files=True)
    curr_u = [f.name for f in up] if up else []
    for s in list(st.session_state.portfolios.keys()):
        if s != "Sample Portfolio.csv" and s not in curr_u:
            del st.session_state.portfolios[s]
            if st.session_state.get('active_portfolio_name') == s: 
                st.session_state.active_portfolio_name = None
                st.rerun()
    if up:
        for f in up:
            if f.name not in st.session_state.portfolios:
                d = pd.read_csv(f)
                d.columns = d.columns.str.strip()
                for col in ['Shares', 'Avg Cost']: d[col] = d[col].apply(clean_numeric)
                st.session_state.portfolios[f.name] = d[["Ticker", "Shares", "Avg Cost"]].dropna()
                st.session_state.active_portfolio_name = f.name
    if st.session_state.portfolios:
        st.write("---")
        for n in list(st.session_state.portfolios.keys()):
            label = f"📍 {strip_ext(n)}" if n == st.session_state.get('active_portfolio_name') else strip_ext(n)
            if st.sidebar.button(label, key=f"sb_{n}", use_container_width=True):
                st.session_state.active_portfolio_name = n
                st.rerun()

active = st.session_state.get('active_portfolio_name')

if not active:
    st.markdown('<div class="master-title">Welcome to Income Tracker</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1.2, 1])
    with c1: st.markdown("### 🚀 Getting Started\nUpload a CSV with **Ticker**, **Shares**, **Avg Cost** to begin.")
    with c2:
        tmp = pd.DataFrame(columns=["Ticker", "Shares", "Avg Cost"], data=[["SCHD", 100.0, 75.0]])
        st.download_button("💾 Download Template.csv", tmp.to_csv(index=False).encode('utf-8'), "Template.csv", "text/csv")
    st.stop()

st.markdown(f'<div class="master-title">Portfolio: {strip_ext(active)}</div>', unsafe_allow_html=True)
t_dash, t_edit = st.tabs(["📊 Dashboard", "✏️ Edit Positions"])

with t_edit:
    df_e = st.session_state.portfolios[active]
    st.subheader("🛠️ Add or Edit Tickers")
    ext_tks = sorted(df_e['Ticker'].unique().tolist())
    sel_tk = st.selectbox("Select ticker:", [""] + ext_tks)
    final_tk = sel_tk if sel_tk != "" else st.text_input("New Symbol:").upper().strip()
    
    with st.form("ed_f"):
        c1, c2 = st.columns(2)
        ns = c1.number_input("Shares", min_value=0.0)
        nc = c2.number_input("Avg Cost", min_value=0.0)
        if st.form_submit_button("COMMIT CHANGES"):
            if final_tk:
                df_e = df_e[df_e['Ticker'] != final_tk]
                if ns > 0:
                    df_e = pd.concat([df_e, pd.DataFrame([{"Ticker": final_tk, "Shares": ns, "Avg Cost": nc}])], ignore_index=True)
                st.session_state.portfolios[active] = df_e
                st.rerun()

with t_dash:
    df = st.session_state.portfolios[active].copy()
    if not df.empty:
        with st.spinner("Market Sync..."):
            meta = get_unified_data(df['Ticker'].unique().tolist())
        
        df['Price'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('price', 0))
        df['D%'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('change_pct', 0))
        df['Val'] = df['Shares'] * df['Price']
        df['Inc'] = df['Shares'] * df['Ticker'].map(lambda x: meta.get(x, {}).get('div', 0))
        df['Day_PL'] = df['Shares'] * df['Ticker'].map(lambda x: meta.get(x, {}).get('change_val', 0))
        df['Total_PL'] = df['Shares'] * (df['Price'] - df['Avg Cost'])
        df['Yield'] = (df['Inc'] / df['Val'].replace(0, 1)) * 100
        df['Saf'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('safety', 'Tier 1'))
        df['Sec'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('sector', 'Other'))

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Portfolio Value", f"${df['Val'].sum():,.0f}")
        m2.metric("Today's P/L", f"${df['Day_PL'].sum():,.2f}")
        m3.metric("Annual Income", f"${df['Inc'].sum():,.2f}")
        m4.metric("Portfolio Yield", f"{(df['Inc'].sum()/df['Val'].sum()*100) if df['Val'].sum()>0 else 0:.2f}%")
        m5.metric("Total P/L", f"${df['Total_PL'].sum():,.2f}")

        st.divider()
        
        # Detailed Analytics Table
        st.subheader("📋 Detailed Analytics")
        html_d = "<div class='html-table-container'><table class='gold-table'><thead><tr>"
        html_d += "<th>Ticker</th><th>Sector</th><th>Safety</th><th>Price</th><th>Day %</th><th>Day P/L</th><th>Total P/L</th><th>Yield</th><th>Value</th><th>Income</th></tr></thead><tbody>"
        for _, r in df.iterrows():
            sv = get_color_style(r['D%'])
            spl = get_color_style(r['Day_PL'])
            tpl = get_color_style(r['Total_PL'])
            html_d += f"<tr><td class='tk-bold'>{r['Ticker']}</td><td>{r['Sec']}</td><td>{r['Saf']}</td><td>${r['Price']:,.2f}</td><td {sv}>{r['D%']:,.2f}%</td><td {spl}>${r['Day_PL']:,.2f}</td><td {tpl}>${r['Total_PL']:,.2f}</td><td>{r['Yield']:.2f}%</td><td>${r['Val']:,.0f}</td><td>${r['Inc']:,.2f}</td></tr>"
        st.markdown(html_d + "</tbody></table></div>", unsafe_allow_html=True)
