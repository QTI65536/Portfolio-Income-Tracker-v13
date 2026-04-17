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

    .radar-container { background-color: #f8f9fa; border-radius: 12px; padding: 20px; border-left: 8px solid #3498db; margin-bottom: 25px; overflow-x: auto; white-space: nowrap; }
    .radar-card { display: inline-block; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-right: 15px; min-width: 200px; text-align: center; border-top: 4px solid #3498db; }
    .radar-ticker { font-size: 24px; font-weight: 900; color: #2c3e50; }
    .radar-date { font-size: 16px; color: #e67e22; font-weight: 700; }
    .radar-amt { font-size: 18px; color: #27ae60; font-weight: 800; }

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

    .html-table-container { width: 100%; overflow-x: auto; margin-top: 10px; }
    .gold-table { width: 100%; border-collapse: collapse; font-size: 22px !important; font-family: sans-serif; }
    .gold-table th { background-color: #f8f9fa; color: #2c3e50; font-size: 24px !important; text-align: left; padding: 16px; border-bottom: 3px solid #2ecc71; }
    .gold-table td { padding: 16px; border-bottom: 1px solid #dee2e6; color: #333; }
    .tk-bold { font-weight: 900; color: #2c3e50; }
    </style>
    """, unsafe_allow_html=True)

HOVER_STYLE = dict(bgcolor="white", font_size=16, font_family="Arial", bordercolor="#2ecc71")
MREIT_SYMBOLS = {'NLY', 'AGNC', 'ORC', 'DX', 'ARR', 'TWO', 'IVR', 'MITT', 'NYMT', 'CIM', 'EARN', 'ABR', 'RITM'}
CASH_SYMBOLS = {'FDRXX', 'SPAXX', 'VMFXX', 'VUSTX', 'SPRXX'}
HARDCODED_CEFS = {'ADX', 'AIO', 'ASGI', 'BME', 'BST', 'BUI', 'CSQ', 'DNP', 'EOS', 'ERH', 'GDV', 'GLU', 'GOF', 'NBXG', 'NIE', 'PCN', 'PDI', 'PDO', 'PDX', 'RFI', 'RLTY', 'RNP', 'RQI', 'STK', 'UTF', 'UTG'}

def get_color_style(val):
    if val > 0.001: return 'style="color: #27ae60; font-weight: bold;"'
    if val < -0.001: return 'style="color: #e74c3c; font-weight: bold;"'
    return 'style="color: #333;"'

def clean_numeric(value):
    try:
        if pd.isna(value) or value == "": return 0.0
        return float(str(value).replace('$', '').replace(',', '').strip())
    except: return 0.0

def strip_ext(filename): return filename.rsplit('.', 1)[0] if '.' in filename else filename

@st.cache_data(ttl=3600)
def get_unified_data(tickers):
    if not tickers: return {}
    try:
        raw_data = yf.download(tickers, period="1mo", actions=True, auto_adjust=True, progress=False)
        if raw_data.empty: return {}
    except: return {}
    
    meta = {}
    for t in tickers:
        try:
            t_prices = raw_data.xs(t, level=1, axis=1) if len(tickers) > 1 else raw_data
            valid_c = t_prices['Close'].dropna()
            lat = float(valid_c.iloc[-1]) if not valid_c.empty else 0.0
            prev = float(valid_c.iloc[-2]) if len(valid_c) > 1 else lat
            div_h = t_prices['Dividends'].dropna()[t_prices['Dividends'] > 0]
            
            tk = yf.Ticker(t); f_info = tk.fast_info
            div_r = f_info.get('last_dividend', 0)
            if (div_r is None or div_r == 0) and not div_h.empty:
                div_r = float(div_h[div_h.index > (datetime.now() - timedelta(days=365))].sum())
            
            try: info = tk.info
            except: info = {}

            sumry = info.get('longBusinessSummary', '').lower()
            is_cef = t in HARDCODED_CEFS or "closed-end" in sumry
            sector = "Cash" if t in CASH_SYMBOLS else ("CEF" if is_cef else info.get('sector', 'Other'))

            reasons = []
            if t in MREIT_SYMBOLS:
                reasons.append("mREIT risk"); reasons.append("Leverage")
            elif lat > 0 and (div_r / lat) > 0.125: reasons.append("Yield Trap")
            
            tier = "Tier 1: ✅ SAFE" if t in CASH_SYMBOLS else ("Tier 3: 🚨 RISK" if len(reasons) >= 2 else ("Tier 2: ⚠️ STABLE" if len(reasons) == 1 else "Tier 1: ✅ SAFE"))

            meta[t] = {
                'price': lat, 'change_val': lat - prev, 'change_pct': (((lat - prev)/prev)*100) if prev > 0 else 0,
                'div': div_r, 'freq': 12 if len(div_h) > 6 else (4 if len(div_h) > 2 else 2), 'ex_date': info.get('exDividendDate'),
                'sector': sector, 'safety': tier, 'reasons': ", ".join(reasons)
            }
        except: meta[t] = {'price': 0.0, 'change_val': 0.0, 'change_pct': 0.0, 'div': 0.0, 'freq': 4, 'ex_date': None, 'sector': 'Other', 'safety': 'Tier 3', 'reasons': 'Error'}
    return meta

if 'portfolios' not in st.session_state: st.session_state.portfolios = {}

with st.sidebar:
    st.header("📂 Portfolio Vault")
    up = st.file_uploader("Upload CSV Files", type="csv", accept_multiple_files=True)
    if up:
        for f in up:
            if f.name not in st.session_state.portfolios:
                d = pd.read_csv(f); d.columns = d.columns.str.strip()
                for col in ['Shares', 'Avg Cost']: d[col] = d[col].apply(clean_numeric)
                st.session_state.portfolios[f.name] = d[["Ticker", "Shares", "Avg Cost"]].dropna()
                st.session_state.active_portfolio_name = f.name
    if st.session_state.portfolios:
        st.write("---")
        for n in list(st.session_state.portfolios.keys()):
            is_active = (n == st.session_state.get('active_portfolio_name'))
            if st.sidebar.button(f"📍 {strip_ext(n)}" if is_active else strip_ext(n), key=f"sb_{n}", use_container_width=True):
                st.session_state.active_portfolio_name = n; st.rerun()

active = st.session_state.get('active_portfolio_name')
if not active:
    st.markdown('<div class="master-title">Welcome to Income Tracker</div>', unsafe_allow_html=True)
    st.info("Upload a CSV with **Ticker**, **Shares**, **Avg Cost** to begin.")
    st.stop()

st.markdown(f'<div class="master-title">Portfolio: {strip_ext(active)}</div>', unsafe_allow_html=True)
t_dash, t_edit = st.tabs(["📊 Dashboard", "✏️ Edit Positions"])

with t_edit:
    df_e = st.session_state.portfolios[active]
    ext_tks = sorted(df_e['Ticker'].unique().tolist())
    with st.form("ed_f", clear_on_submit=True):
        c1, c2, c3 = st.columns([2,1,1])
        final_tk = c1.selectbox("Ticker:", [""] + ext_tks) or c1.text_input("New Symbol:").upper().strip()
        ns, nc = c2.number_input("Shares", min_value=0.0), c3.number_input("Avg Cost", min_value=0.0)
        if st.form_submit_button("COMMIT CHANGES"):
            if final_tk:
                df_e = df_e[df_e['Ticker'] != final_tk]
                if ns > 0: df_e = pd.concat([df_e, pd.DataFrame([{"Ticker": final_tk, "Shares": ns, "Avg Cost": nc}])], ignore_index=True)
                st.session_state.portfolios[active] = df_e; st.rerun()
    st.divider(); st.subheader("📋 Current Inventory")
    st.download_button("💾 SAVE PORTFOLIO (CSV)", df_e.to_csv(index=False).encode('utf-8'), f"{strip_ext(active)}.csv", "text/csv")
    html_inv = "<div class='html-table-container'><table class='gold-table'><thead><tr><th>Ticker</th><th>Shares</th><th>Avg Cost</th><th>Basis ($)</th></tr></thead><tbody>"
    for _, r in df_e.sort_values("Ticker").iterrows():
        sh, cost = float(r['Shares']), float(r['Avg Cost'])
        html_inv += f"<tr><td class='tk-bold'>{r['Ticker']}</td><td>{sh:,.2f}</td><td>${cost:,.2f}</td><td>${(sh*cost):,.0f}</td></tr>"
    st.markdown(html_inv + "</tbody></table></div>", unsafe_allow_html=True)

with t_dash:
    df = st.session_state.portfolios[active].copy()
    if not df.empty:
        with st.spinner("Market Data Sync..."): meta = get_unified_data(df['Ticker'].unique().tolist())
        df['Price'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('price', 0))
        df['D$'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('change_val', 0)); df['D%'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('change_pct', 0))
        df['Val'] = df['Shares'] * df['Price']; df['Inc'] = df['Shares'] * df['Ticker'].map(lambda x: meta.get(x, {}).get('div', 0))
        df['Day_PL'] = df['Shares'] * df['D$']; df['Total_PL'] = df['Shares'] * (df['Price'] - df['Avg Cost'])
        df['Saf'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('safety', 'Tier 1'))
        df['Sec'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('sector', 'Other'))
        df['ExD'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('ex_date'))
        df['Frq'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('freq', 4)); df['Yield'] = (df['Inc'] / df['Val'].replace(0,1)) * 100

        # Radar
        radar_items = []
        now = datetime.now(); horizon = now + timedelta(days=14)
        for _, r in df.iterrows():
            if pd.notna(r['ExD']) and isinstance(r['ExD'], (int, float)):
                try:
                    ex_dt = (datetime.fromtimestamp(r['ExD']) + timedelta(hours=12)).replace(hour=0, minute=0, second=0, microsecond=0)
                    if now <= ex_dt <= horizon: radar_items.append({'Tk': r['Ticker'], 'Dt': ex_dt, 'Amt': r['Inc']/r['Frq']})
                except: pass
        if radar_items:
            st.subheader("📡 Dividend Radar (Next 14 Days)")
            r_html = '<div class="radar-container">'
            for i in sorted(radar_items, key=lambda x: x['Dt']):
                r_html += f'<div class="radar-card"><div class="radar-ticker">{i["Tk"]}</div><div class="radar-date">Ex-Div: {i["Dt"].strftime("%b %d")}</div><div class="radar-amt">${i["Amt"]:,.2f}</div></div>'
            st.markdown(r_html + '</div>', unsafe_allow_html=True)

        m1, m2, m3, m4, m5 = st.columns(5)
        ti, tv = df['Inc'].sum(), df['Val'].sum()
        m1.metric("Value", f"${tv:,.0f}"); m2.metric("Today", f"${df['Day_PL'].sum():,.2f}"); m3.metric("Income", f"${ti:,.2f}")
        m4.metric("Yield", f"{(ti/tv*100) if tv>0 else 0:.2f}%"); m5.metric("Total P/L", f"${df['Total_PL'].sum():,.2f}")

        st.divider(); c1, c2, c3 = st.columns(3)
        def draw_donut(pdf, v_col, l_col, tot):
            def agg(g):
                s_g = g.sort_values(v_col, ascending=False).head(10)
                b = "".join([f"• {t}: <b>${amt:,.2f}</b><br>" for t, amt in zip(s_g['Ticker'], s_g[v_col])])
                return pd.Series({'Sum': g[v_col].sum(), 'Hover': f"<b>{g.name}</b><br>Total: ${g[v_col].sum():,.2f}<br><br>{b}"})
            sum_df = pdf.groupby(l_col).apply(agg).reset_index()
            f = go.Figure(data=[go.Pie(labels=sum_df[l_col], values=sum_df['Sum'], hole=0.6, customdata=sum_df['Hover'], hovertemplate="<b>%{customdata}</b><extra></extra>")])
            f.update_layout(height=400, margin=dict(t=0, b=0), hoverlabel=HOVER_STYLE, legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(f, use_container_width=True)

        with c1: st.subheader("Safety Rating"); draw_donut(df, "Inc", "Saf", ti)
        with c2:
            st.subheader("10-Year Forecast"); g_r = st.number_input("Growth %", min_value=0.0, max_value=100.0, value=6.0, step=0.5)
            y_p = [datetime.now().year + i for i in range(11)]; v_p = [ti * ((1 + g_r/100)**i) for i in range(11)]
            fig_g = go.Figure(data=[go.Scatter(x=y_p, y=v_p, fill='tozeroy', mode='lines+markers', customdata=v_p, hovertemplate="<b>Year: %{x}</b><br>Income: $%{customdata:,.2f}<extra></extra>")])
            fig_g.update_layout(height=350, margin=dict(b=0), hoverlabel=HOVER_STYLE); st.plotly_chart(fig_g, use_container_width=True)
        with c3: st.subheader("Sector Allocation"); draw_donut(df, "Val", "Sec", tv)

        # --- RESTORED 12-MONTH CALENDAR LOGIC ---
        st.divider(); st.subheader("📅 Monthly Income Distribution")
        mnths = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        cal_list = []
        for _, r in df.iterrows():
            if r['Inc'] > 0:
                # Determine the 'Seed Month' (First month of payment)
                try:
                    seed = (datetime.fromtimestamp(r['ExD']) + timedelta(hours=12)).month if pd.notna(r['ExD']) else 1
                except: seed = 1
                
                # Project payments across 12 months based on frequency
                step = 12 // int(r['Frq'])
                for i in range(int(r['Frq'])):
                    # Calculate the month index (0-11)
                    m_idx = (seed + (i * step) - 1) % 12
                    cal_list.append({'Ticker': r['Ticker'], 'Month': mnths[m_idx], 'MonthInc': r['Inc']/int(r['Frq']), 'Sort': m_idx})
        
        if cal_list:
            c_df = pd.DataFrame(cal_list)
            # Group by month and build hover text
            def m_agg(g):
                s_g = g.sort_values('MonthInc', ascending=False).head(10)
                b = "<br>".join([f"• {t}: <b>${amt:,.2f}</b>" for t, amt in zip(s_g['Ticker'], s_g['MonthInc'])])
                return pd.Series({'Total': g['MonthInc'].sum(), 'Break': f"<b>Monthly Total: ${g['MonthInc'].sum():,.2f}</b><br><br>{b}"})
            c_s = c_df.groupby(['Month', 'Sort']).apply(m_agg).reset_index().sort_values('Sort')
            
            # Ensure all 12 months are represented even if zero
            full_year = pd.DataFrame({'Month': mnths, 'Sort': range(12)})
            c_s = full_year.merge(c_s, on=['Month', 'Sort'], how='left').fillna({'Total': 0, 'Break': 'No income this month'})
            
            fig_c = go.Figure(data=[go.Bar(x=c_s['Month'], y=c_s['Total'], customdata=c_s['Break'], hovertemplate="<b>%{x}</b><br>%{customdata}<extra></extra>")])
            fig_c.update_layout(height=400, hoverlabel=HOVER_STYLE, xaxis_title="Month", yaxis_title="Income ($)"); st.plotly_chart(fig_c, use_container_width=True)

        st.divider(); st.subheader("📋 Detailed Analytics")
        s_map = {"Ticker":"Ticker", "Sector":"Sec", "Safety":"Saf", "Price":"Price", "Day %":"D%", "Day's P/L":"Day_PL", "Total P/L":"Total_PL", "Yield":"Yield", "Value":"Val", "Income":"Inc"}
        sc1, sc2 = st.columns(2); s_by = sc1.selectbox("Sort By:", list(s_map.keys()), index=8); s_ord = sc2.radio("Order:", ["Descending", "Ascending"], horizontal=True)
        df_s = df.sort_values(by=s_map[s_by], ascending=(s_ord=="Ascending"))
        h = "<div class='html-table-container'><table class='gold-table'><thead><tr><th>Ticker</th><th>Sector</th><th>Safety</th><th>Price</th><th>Day %</th><th>Day P/L</th><th>Total P/L</th><th>Yield</th><th>Value</th><th>Income</th></tr></thead><tbody>"
        for _, r in df_s.iterrows():
            sv, spl, tpl = get_color_style(r['D%']), get_color_style(r['Day_PL']), get_color_style(r['Total_PL'])
            h += f"<tr><td class='tk-bold'>{r['Ticker']}</td><td>{r['Sec']}</td><td>{r['Saf']}</td><td>${r['Price']:,.2f}</td><td {sv}>{r['D%']:,.2f}%</td><td {spl}>${r['Day_PL']:,.2f}</td><td {tpl}>${r['Total_PL']:,.2f}</td><td>{r['Yield']:.2f}%</td><td>${r['Val']:,.0f}</td><td>${r['Inc']:,.2f}</td></tr>"
        st.markdown(h + "</tbody></table></div>", unsafe_allow_html=True)
