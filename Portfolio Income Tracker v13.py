import streamlit as st
import asyncio
from google import genai
from google.genai import types
from fpdf import FPDF
import tempfile
import os
import io

# --- PAGE CONFIG ---
st.set_page_config(page_title="DSM v10.6 | Full Persistence", page_icon="📈", layout="wide")
st.title("📈 DSM Engine v10.6 | Full Persistence")
st.caption("Fix: Session State includes Raw Vision Output + PDF Download Persistence")

# --- INITIALIZE SESSION STATE ---
if 'audit_results' not in st.session_state:
    st.session_state.audit_results = None

# --- SIDEBAR ---
with st.sidebar:
    st.header("🔑 API Gateway")
    gemini_key = st.text_input("Google Gemini Key", type="password")
    st.divider()
    uploaded_chart = st.file_uploader("Upload FastGraph Screenshot", type=["png", "jpg", "jpeg"])


# --- PDF GENERATOR HELPER ---
def create_pdf(ticker, snap, report, image_bytes):
    pdf = FPDF()
    pdf.add_page()

    def clean_text(text):
        if not text: return ""
        cleaned = (text.replace('\u2019', "'").replace('\u2018', "'")
                   .replace('\u201c', '"').replace('\u201d', '"')
                   .replace('\u2013', '-').replace('\u2014', '-'))
        return cleaned.encode('ascii', 'ignore').decode('ascii')

    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"DSM FastGraphs Audit Report: {ticker}", ln=True, align='C')

    if image_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        pdf.image(tmp_path, x=15, y=25, w=180)
        os.remove(tmp_path)
        pdf.ln(115)

    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="Section 7: Governance Snapshot", ln=True)
    pdf.set_font("Courier", size=9)
    pdf.multi_cell(0, 5, clean_text(snap))

    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="Lead Auditor Final Report", ln=True)
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 5, clean_text(report))

    return pdf.output(dest='S').encode('latin-1')


# --- WORKER: GEMINI (VISION ANALYST) ---
async def get_gemini_vision(prompt, api_key, image_bytes=None):
    client = genai.Client(api_key=api_key)
    parts = [prompt]
    if image_bytes:
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
    try:
        res = await client.aio.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=parts
        )
        return res.text
    except Exception as e:
        return f"GEMINI_ERROR: {str(e)}"


# --- AUDIT PIPELINE ---
async def run_audit_pipeline(ticker, image_bytes, g_key):
    # Step 1: Raw extraction
    gem_res = await get_gemini_vision(f"Perform a DSM v3.2 Tri-Line Audit for {ticker}.", g_key, image_bytes)
    # Step 2: Formatted report
    audit_prompt = f"Lead Auditor: Finalize DSM v3.2 Audit for {ticker} using vision data.\n\nVISION: {gem_res}"
    final_report = await get_gemini_vision(audit_prompt, g_key)
    # Step 3: Snapshot table
    snap_prompt = f"Reformat this into a DSM Section 7 Snapshot table:\n{final_report}"
    snapshot = await get_gemini_vision(snap_prompt, g_key)
    return gem_res, final_report, snapshot


# --- UI LOGIC ---
ticker_input = st.text_input("Ticker Symbol:").upper()

if st.button("🚀 Run Full DSM Audit"):
    if not (gemini_key and ticker_input and uploaded_chart):
        st.error("Setup incomplete: API Key, Ticker, and Chart required.")
    else:
        img_bytes = uploaded_chart.getvalue()
        with st.status("📡 Processing...") as status:
            try:
                raw_out, report, snap = asyncio.run(run_audit_pipeline(ticker_input, img_bytes, gemini_key))
                pdf_data = create_pdf(ticker_input, snap, report, img_bytes)

                # STORE ALL DATA IN SESSION STATE
                st.session_state.audit_results = {
                    "ticker": ticker_input,
                    "raw": raw_out,
                    "report": report,
                    "snap": snap,
                    "pdf": pdf_data
                }
                status.update(label="Complete!", state="complete")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# --- PERSISTENT DISPLAY LOGIC ---
if st.session_state.audit_results:
    res = st.session_state.audit_results

    # PDF Download
    st.download_button(
        label=f"📥 Download {res['ticker']} Report",
        data=res['pdf'],
        file_name=f"DSM_Audit_{res['ticker']}.pdf",
        mime="application/pdf"
    )

    # Section 7 Table
    st.subheader(f"📝 Section 7: Governance Snapshot ({res['ticker']})")
    st.code(res['snap'], language="text")

    st.divider()

    # Final Report
    st.markdown("### 📋 Lead Auditor Final Report")
    st.write(res['report'])

    st.divider()

    # RESTORED: Raw Vision Output
    with st.expander("🔍 View Raw Vision Data"):
        st.info(res['raw'])
