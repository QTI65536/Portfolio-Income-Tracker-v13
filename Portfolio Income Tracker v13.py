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

    /* HIGH VISIBILITY BUTTONS */
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
HARDCODED_CEFS = {'ADX', 'AIO', 'ASGI', 'BME', 'BST', 'BUI', 'CSQ', 'DNP', 'EOS', 'ERH', 'GDV', 'GLU', 'GOF', 'NBXG',
                  'NIE', 'PCN', 'PDI', 'PDO', 'PDX', 'RFI', 'RLTY', 'RNP', 'RQI', 'STK', 'UTF', 'UTG'}
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
    except:
        return 0.0


def strip_ext(filename):
    return filename.rsplit('.', 1)[0] if '.' in filename else filename


@st.cache_data(ttl=3600)
def get_unified_data(tickers):
    if not tickers: return {}
    try:
        raw_data = yf.download(tickers, period="1y", actions=True, auto_adjust=True, progress=False)
        if raw_data.empty: return {}
    except:
        return {}
    meta = {}
    for t in tickers:
        try:
            t_prices = raw_data.xs(t, level=1, axis=1) if len(tickers) > 1 else raw_data
            valid_c = t_prices['Close'].dropna()
            lat, prev = float(valid_c.iloc[-1]), float(valid_c.iloc[-2])
            div_h = t_prices['Dividends'].dropna()
            div_h = div_h[div_h > 0]
            tk = yf.Ticker(t);
            info = tk.info
            div_r = float(info.get('dividendRate', 0) or 0)
            if div_r == 0 and not div_h.empty:
                div_r = float(div_h[div_h.index > (datetime.now() - timedelta(days=365))].sum())
            latest_ex = info.get('exDividendDate') or (int(div_h.index[-1].timestamp()) if not div_h.empty else None)
            sumry = info.get('longBusinessSummary', '').lower()
            is_cef = t in HARDCODED_CEFS or "closed-end" in sumry
            sector = "Cash / Reserves" if t in CASH_SYMBOLS else (
                "Closed-End Fund" if is_cef else info.get('sector', 'Other'))

            reasons = []
            if t in CASH_SYMBOLS:
                pass
            elif t in MREIT_SYMBOLS:
                reasons.append("Structural mREIT Risk")
                if div_r / lat > 0.10: reasons.append("Yield >10%")
            else:
                if sector == "Utilities":
                    ocf = info.get('operatingCashflow', 0) or 0
                    total_div_cost = div_r * info.get('sharesOutstanding', 1)
                    if ocf > 0 and (total_div_cost / ocf) > 0.70: reasons.append("Utility OCF Payout")
                elif sector == "Real Estate":
                    ocf, capex = (info.get('operatingCashflow', 0) or 0), abs(info.get('capitalExpenditures', 0) or 0)
                    affo = ocf - capex
                    total_div_cost = div_r * info.get('sharesOutstanding', 1)
                    if affo > 0 and (total_div_cost / affo) > 0.90: reasons.append("AFFO Payout")
                else:
                    payout = info.get('payoutRatio', 0) or 0
                    if payout > 0.75: reasons.append("EPS Payout")

            if t in CASH_SYMBOLS:
                tier = "Tier 1: ✅ SAFE"
            elif len(reasons) >= 2:
                tier = "Tier 3: 🚨 RISK"
            elif len(reasons) == 1:
                tier = "Tier 2: ⚠️ STABLE"
            else:
                tier = "Tier 1: ✅ SAFE"

            meta[t] = {
                'price': lat, 'change_val': lat - prev, 'change_pct': ((lat - prev) / prev) * 100,
                'div': div_r, 'freq': 12 if len(div_h) > 6 else 4, 'ex_date': latest_ex,
                'sector': sector, 'safety': tier, 'reasons': ", ".join(reasons)
            }
        except:
            meta[t] = {'price': 0.0, 'change_val': 0.0, 'change_pct': 0.0, 'div': 0.0, 'freq': 4, 'ex_date': None,
                       'sector': 'Unknown', 'safety': 'Tier 3: 🚨 RISK', 'reasons': 'Data error'}
    return meta


if 'portfolios' not in st.session_state: st.session_state.portfolios = {}

with st.sidebar:
    st.header("📂 Portfolio Vault")
    up = st.file_uploader("Upload CSV Files", type="csv", accept_multiple_files=True)
    curr_u = [f.name for f in up] if up else []
    for s in list(st.session_state.portfolios.keys()):
        if s != "Sample Portfolio.csv" and s not in curr_u:
            del st.session_state.portfolios[s]
            if st.session_state.get(
                'active_portfolio_name') == s: st.session_state.active_portfolio_name = None; st.rerun()
    if up:
        for f in up:
            if f.name not in st.session_state.portfolios:
                d = pd.read_csv(f);
                d.columns = d.columns.str.strip()
                for col in ['Shares', 'Avg Cost']: d[col] = d[col].apply(clean_numeric)
                st.session_state.portfolios[f.name] = d[["Ticker", "Shares", "Avg Cost"]].dropna()
                st.session_state.active_portfolio_name = f.name
    if st.session_state.portfolios:
        st.write("---")
        for n in list(st.session_state.portfolios.keys()):
            if st.sidebar.button(
                    f"📍 {strip_ext(n)}" if n == st.session_state.get('active_portfolio_name') else strip_ext(n),
                    use_container_width=True):
                st.session_state.active_portfolio_name = n;
                st.rerun()

st.markdown(f'<div class="app-branding">Income Portfolio Tracker by QTI (v13.7)</div>', unsafe_allow_html=True)
active = st.session_state.get('active_portfolio_name')

if not active:
    st.markdown('<div class="master-title">Welcome to Income Tracker</div>', unsafe_allow_html=True)
    cg, ca = st.columns([1.2, 1])
    with cg:
        st.markdown(
            "### 🚀 Getting Started\n1. **Excel / Google Sheets:** Create 3 columns: **Ticker**, **Shares**, **Avg Cost**.\n2. **Save as CSV**: Choose **CSV (Comma Delimited)**.\n3. **Upload**: Drag the file into the sidebar.")
    with ca:
        st.markdown("### 🛠️ Onboarding")
        tmp = pd.DataFrame(columns=["Ticker", "Shares", "Avg Cost"], data=[["SCHD", 100.0, 75.0]])
        st.download_button("💾 Download Template.csv", tmp.to_csv(index=False).encode('utf-8'), "Template.csv",
                           "text/csv")
        if st.button("📈 Load Default Sample Portfolio"):
            if os.path.exists("Sample Portfolio.csv"):
                sdf = pd.read_csv("Sample Portfolio.csv")
                st.session_state.portfolios["Sample Portfolio.csv"] = sdf
                st.session_state.active_portfolio_name = "Sample Portfolio.csv";
                st.rerun()
    st.stop()

st.markdown(f'<div class="master-title">Portfolio: {strip_ext(active)}</div>', unsafe_allow_html=True)
t_dash, t_edit = st.tabs(["📊 Dashboard", "✏️ Edit Positions"])

with t_edit:
    df_e = st.session_state.portfolios[active]
    st.subheader("🛠️ Add or Edit Tickers")
    ext_tks = sorted(df_e['Ticker'].unique().tolist())
    sel_tk = st.selectbox("Select existing or type new:", [""] + ext_tks,
                          format_func=lambda x: "--- Create New ---" if x == "" else x)
    final_tk = sel_tk if sel_tk != "" else st.text_input("New Ticker Symbol:").upper().strip()
    curr_s, curr_c = 0.0, 0.0
    if final_tk in df_e['Ticker'].values:
        r_ed = df_e[df_e['Ticker'] == final_tk].iloc[0]
        curr_s, curr_c = float(r_ed['Shares']), float(r_ed['Avg Cost'])
    with st.form("ed_f", clear_on_submit=True):
        c1, c2 = st.columns(2)
        ns, nc = c1.number_input("Shares", min_value=0.0, value=curr_s), c2.number_input("Avg Cost", min_value=0.0,
                                                                                         value=curr_c)
        if st.form_submit_button("COMMIT CHANGES"):
            if final_tk:
                if ns <= 0:
                    st.session_state.portfolios[active] = df_e[df_e['Ticker'] != final_tk]
                elif final_tk in df_e['Ticker'].values:
                    df_e.loc[df_e['Ticker'] == final_tk, ['Shares', 'Avg Cost']] = [ns, nc]
                else:
                    st.session_state.portfolios[active] = pd.concat(
                        [df_e, pd.DataFrame([{"Ticker": final_tk, "Shares": ns, "Avg Cost": nc}])], ignore_index=True)
                st.toast("✅ Updated!");
                time.sleep(0.5);
                st.rerun()
    st.divider();
    st.subheader("📋 Delete Tickers")
    to_del = st.multiselect("Select Tickers to Remove:", ext_tks)
    if to_del and st.button("🗑️ DELETE SELECTED", type="primary"):
        st.session_state.portfolios[active] = df_e[~df_e['Ticker'].isin(to_del)];
        st.rerun()
    st.divider();
    st.subheader("📋 Inventory");
    st.download_button("💾 SAVE CURRENT PORTFOLIO", df_e.to_csv(index=False).encode('utf-8'),
                       f"{strip_ext(active)}.csv", "text/csv")
    html_e = "<div class='html-table-container'><table class='gold-table'><thead><tr><th>Ticker</th><th>Shares</th><th>Avg Cost</th><th>Basis</th></tr></thead><tbody>"
    for _, r in df_e.sort_values("Ticker").iterrows():
        sh, co = float(r['Shares']), float(r['Avg Cost'])
        html_e += f"<tr><td class='tk-bold'>{r['Ticker']}</td><td>{sh:,.2f}</td><td>${co:,.2f}</td><td>${(sh * co):,.0f}</td></tr>"
    st.markdown(html_e + "</tbody></table></div>", unsafe_allow_html=True)

with t_dash:
    df = st.session_state.portfolios[active].copy()
    if not df.empty:
        with st.spinner("Syncing Live Metrics..."):
            meta = get_unified_data(df['Ticker'].unique().tolist())
        df['Price'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('price', 0))
        df['D$'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('change_val', 0))
        df['D%'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('change_pct', 0))
        df['Val'] = df['Shares'] * df['Price']
        df['Day_PL'] = df['Shares'] * df['D$']
        df['Total_PL'] = df['Shares'] * (df['Price'] - df['Avg Cost'])
        df['Inc'] = df['Shares'] * df['Ticker'].map(lambda x: meta.get(x, {}).get('div', 0))
        df['Saf'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('safety', 'Tier 2'))
        df['Sec'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('sector', 'Other'))
        df['Why'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('reasons', ''))
        df['ExD'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('ex_date'))
        df['Frq'] = df['Ticker'].map(lambda x: meta.get(x, {}).get('freq', 4))
        df['Yield'] = (df['Inc'] / df['Val'].replace(0, 1)) * 100

        m1, m2, m3, m4, m5 = st.columns(5)
        tv, ti, tg = df['Val'].sum(), df['Inc'].sum(), df['Day_PL'].sum()
        m1.metric("Portfolio Value", f"${tv:,.0f}");
        m2.metric("Today's Change", f"${tg:,.2f}", f"{(tg / (tv - tg) * 100) if (tv - tg) != 0 else 0:.2f}%")
        m3.metric("Annual Income", f"${ti:,.2f}");
        m4.metric("Div. Yield", f"{(ti / tv * 100) if tv > 0 else 0:.2f}%");
        m5.metric("YOC",
                  f"{(ti / (df['Shares'] * df['Avg Cost']).sum() * 100) if (df['Shares'] * df['Avg Cost']).sum() > 0 else 0:.2f}%")

        st.divider();
        c1, c2, c3 = st.columns(3)


        def draw_donut(pdf, val_col, lab_col, total_overall):
            def agg(g):
                s_g = g.sort_values(val_col, ascending=False).head(10)
                b = ""
                for t, amt, why in zip(s_g['Ticker'], s_g[val_col], s_g['Why']):
                    reason_str = f" ({why})" if (why and "RISK" in g.name) else ""
                    b += f"• {t}: <b>${amt:,.2f}</b>{reason_str}<br>"
                if len(g) > 10: b += f"<br><i>...and {len(g) - 10} others</i>"
                perc = (g[val_col].sum() / total_overall * 100) if total_overall > 0 else 0
                return pd.Series({'Sum': g[val_col].sum(),
                                  'Hover': f"<b>{g.name}: {perc:.1f}%</b><br>Total: ${g[val_col].sum():,.2f}<br><br>{b}"})

            sum_df = pdf.groupby(lab_col).apply(agg).reset_index()
            f = go.Figure(data=[go.Pie(labels=sum_df[lab_col], values=sum_df['Sum'], hole=0.6, marker=dict(
                colors=['#2ecc71', '#f1c40f', '#e74c3c'] if 'Tier' in str(
                    sum_df[lab_col].iloc[0]) else px.colors.qualitative.Pastel), customdata=sum_df['Hover'],
                                       hovertemplate="<b>%{customdata}</b><extra></extra>")])
            f.update_layout(height=550, margin=dict(t=30, b=150), hoverlabel=HOVER_STYLE,
                            legend=dict(orientation="h", y=-0.2, x=0.5, xanchor="center"))
            st.plotly_chart(f, use_container_width=True)


        with c1:
            st.subheader("Dynamic Safety Rating"); draw_donut(df, "Inc", "Saf", ti)
        with c2:
            st.subheader("10-Year Income Forecast");
            g_r = st.number_input("Growth %", value=6.0, step=0.5)
            y_proj = [datetime.now().year + i for i in range(11)];
            v_proj = [ti * ((1 + g_r / 100) ** i) for i in range(11)]
            fig_g = px.area(x=y_proj, y=v_proj);
            fig_g.update_traces(hovertemplate="<b>Year: %{x}</b><br>Income: $%{y:,.2f}<extra></extra>")
            fig_g.update_layout(height=400, margin=dict(b=50), hoverlabel=HOVER_STYLE);
            st.plotly_chart(fig_g, use_container_width=True)
        with c3:
            st.subheader("Sector Allocation");
            v_t = st.radio("View Sector By:", ["Portfolio Value", "Annual Income"], horizontal=True, key="sec_toggle")
            draw_donut(df, "Val" if v_t == "Portfolio Value" else "Inc", "Sec", tv if v_t == "Portfolio Value" else ti)

        st.divider();
        st.subheader("📅 Monthly Income Distribution")
        mnths = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        cal_list = []
        for _, r in df.iterrows():
            if r['Inc'] > 0:
                try:
                    start = datetime.fromtimestamp(r['ExD']).month if (r['ExD'] and not pd.isna(r['ExD'])) else (
                        1 if int(r['Frq']) == 12 else 3)
                except:
                    start = 1
                for i in range(int(r['Frq'])):
                    idx = (start + (i * (12 // int(r['Frq']))) - 1) % 12
                    cal_list.append(
                        {'Ticker': r['Ticker'], 'Month': mnths[idx], 'MonthInc': r['Inc'] / int(r['Frq']), 'Sort': idx})
        if cal_list:
            c_df = pd.DataFrame(cal_list)


            def m_st(g):
                s_g = g.sort_values('MonthInc', ascending=False).head(10);
                b = "<br>".join([f"• {t}: <b>${amt:,.2f}</b>" for t, amt in zip(s_g['Ticker'], s_g['MonthInc'])])
                return pd.Series({'Total': g['MonthInc'].sum(),
                                  'Break': f"<b>Monthly Total: ${g['MonthInc'].sum():,.2f}</b><br><br>{b}"})


            c_s = c_df.groupby(['Month', 'Sort']).apply(m_st).reset_index().sort_values('Sort')
            fig_c = go.Figure(data=[
                go.Bar(x=c_s['Month'], y=c_s['Total'], text=c_s['Total'], texttemplate='$%{text:.2s}',
                       customdata=c_s['Break'], hovertemplate="<b>%{x}</b><br>%{customdata}<extra></extra>")]);
            fig_c.update_layout(height=450, hoverlabel=HOVER_STYLE);
            st.plotly_chart(fig_c, use_container_width=True)

        st.divider();
        st.subheader("📋 Detailed Analytics")
        # UPDATED SORT COLUMN MAP
        s_map = {"Ticker": "Ticker", "Sector": "Sec", "Safety": "Saf", "Price": "Price", "Day Chg %": "D%",
                 "Day's P/L $": "Day_PL", "Total P/L $": "Total_PL", "Yield": "Yield", "Value": "Val", "Income": "Inc"}
        sc1, sc2 = st.columns(2);
        s_by = sc1.selectbox("Sort Table By:", list(s_map.keys()), index=8)  # Default to Value
        s_ord = sc2.radio("Order:", ["Descending", "Ascending"], horizontal=True)
        df_s = df.sort_values(by=s_map[s_by], ascending=(s_ord == "Ascending"))

        # COLUMN HEADERS UPDATED: Day Chg % replaced Day Chg $
        html_d = "<div class='html-table-container'><table class='gold-table'><thead><tr>"
        html_d += "<th>Ticker</th><th>Sector</th><th>Safety</th><th>Price</th><th>Day Chg %</th><th>Day's P/L $</th><th>Total P/L $</th><th>Yield</th><th>Value</th><th>Income</th></tr></thead><tbody>"
        for _, r in df_s.iterrows():
            sv = get_color_style(r['D%'])
            spl = get_color_style(r['Day_PL'])
            tpl = get_color_style(r['Total_PL'])
            html_d += f"<tr><td class='tk-bold'>{r['Ticker']}</td><td>{r['Sec']}</td><td>{r['Saf']}</td><td>${r['Price']:,.2f}</td><td {sv}>{r['D%']:,.2f}%</td><td {spl}>${r['Day_PL']:,.2f}</td><td {tpl}>${r['Total_PL']:,.2f}</td><td>{r['Yield']:.2f}%</td><td>${r['Val']:,.0f}</td><td>${r['Inc']:,.2f}</td></tr>"
        st.markdown(html_d + "</tbody></table></div>", unsafe_allow_html=True)
