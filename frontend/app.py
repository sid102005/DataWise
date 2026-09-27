"""DataWise — Streamlit Frontend.

Single-page web UI that wraps the DataWise FastAPI backend:
  - File upload (CSV / XLSX / JSON)
  - Natural-language prompt box
  - Export format selector
  - Real-time pipeline execution
  - Data profile display & preview table
  - Inline chart visualization
  - Execution plan & per-step telemetry
  - Validation report & auto-retry audit
  - Clarification short-circuit with resubmission
  - Download buttons for processed datasets and charts
  - Security-hardened error display (redacted paths, no raw JSON/stack info)

Run:
    streamlit run frontend/app.py
(with the FastAPI backend running at http://127.0.0.1:8000)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure the project root is on sys.path so both `frontend.*` and `backend.*`
# imports resolve correctly regardless of how Streamlit is launched.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import io
from pathlib import Path
import streamlit as st

from frontend.client import call_pipeline, fetch_file, get_api_base, get_capabilities
from frontend.helpers import extract_clarification_question

# ------------------------------------------------------------------------------
# Page setup — must be first Streamlit call
# ------------------------------------------------------------------------------

st.set_page_config(
    page_title="DataWise — AI Data Agent",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE = get_api_base()
FALLBACK_EXTENSIONS = ["csv", "xlsx", "json"]

capabilities = get_capabilities(API_BASE)
if capabilities and "supported_extensions" in capabilities:
    supported_types = capabilities["supported_extensions"]
    supported_cats = capabilities.get("supported_categories", ["tabular"])
    exts_by_cat = capabilities.get("extensions_by_category", {})
    backend_online = True
else:
    supported_types = FALLBACK_EXTENSIONS
    supported_cats = ["tabular"]
    exts_by_cat = {"tabular": FALLBACK_EXTENSIONS}
    backend_online = False


# ------------------------------------------------------------------------------
# Custom CSS — premium dark theme
# ------------------------------------------------------------------------------

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .stApp {
        background: linear-gradient(135deg, #0d1117 0%, #161b22 60%, #0d1117 100%);
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #161b22 0%, #0d1117 100%);
        border-right: 1px solid #30363d;
    }

    .hero-banner {
        background: linear-gradient(135deg, #1e3a5f 0%, #0d2137 40%, #1a1a2e 100%);
        border: 1px solid #30363d;
        border-radius: 16px;
        padding: 2.5rem 2rem 2rem 2rem;
        margin-bottom: 1.5rem;
        position: relative;
        overflow: hidden;
    }
    .hero-banner::before {
        content: '';
        position: absolute;
        top: -50%; right: -10%;
        width: 400px; height: 400px;
        background: radial-gradient(circle, rgba(56,139,253,0.12) 0%, transparent 70%);
    }
    .hero-title {
        font-size: 2.4rem; font-weight: 700;
        background: linear-gradient(135deg, #58a6ff 0%, #79c0ff 50%, #a5d6ff 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin: 0 0 0.4rem 0; line-height: 1.1;
    }
    .hero-sub { color: #8b949e; font-size: 1rem; margin: 0; }
    .hero-badge {
        display: inline-block;
        background: rgba(56,139,253,0.15); border: 1px solid rgba(56,139,253,0.3);
        color: #58a6ff; border-radius: 100px; padding: 3px 12px;
        font-size: 0.72rem; font-weight: 600; letter-spacing: 0.08em;
        text-transform: uppercase; margin-bottom: 0.8rem;
    }

    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 0.75rem; margin: 1rem 0;
    }
    .metric-card {
        background: rgba(22,27,34,0.9); border: 1px solid #30363d;
        border-radius: 12px; padding: 1rem; text-align: center;
        transition: border-color 0.2s, transform 0.15s;
    }
    .metric-card:hover { border-color: #58a6ff; transform: translateY(-2px); }
    .metric-value { font-size: 1.75rem; font-weight: 700; color: #58a6ff; line-height: 1; }
    .metric-label { font-size: 0.72rem; color: #8b949e; margin-top: 0.3rem; text-transform: uppercase; letter-spacing: 0.05em; }

    .status-badge {
        display: inline-flex; align-items: center; gap: 0.4rem;
        border-radius: 100px; padding: 5px 14px;
        font-size: 0.8rem; font-weight: 600; letter-spacing: 0.04em;
    }
    .badge-success  { background: rgba(35,134,54,0.2);  border: 1px solid rgba(35,134,54,0.5);  color: #3fb950; }
    .badge-partial  { background: rgba(210,153,34,0.2); border: 1px solid rgba(210,153,34,0.5); color: #d29922; }
    .badge-clarification { background: rgba(56,139,253,0.2); border: 1px solid rgba(56,139,253,0.5); color: #58a6ff; }
    .badge-failed   { background: rgba(248,81,73,0.2);  border: 1px solid rgba(248,81,73,0.5);  color: #f85149; }
    .badge-error    { background: rgba(248,81,73,0.2);  border: 1px solid rgba(248,81,73,0.5);  color: #f85149; }

    .summary-box {
        background: linear-gradient(135deg, rgba(22,27,34,0.9) 0%, rgba(30,58,95,0.3) 100%);
        border: 1px solid #30363d; border-left: 3px solid #58a6ff;
        border-radius: 10px; padding: 1.1rem 1.3rem;
        color: #c9d1d9; font-size: 0.95rem; line-height: 1.6; margin-bottom: 1rem;
    }

    .clarification-box {
        background: linear-gradient(135deg, rgba(22,27,34,0.9) 0%, rgba(56,139,253,0.1) 100%);
        border: 1px solid #388bfd; border-radius: 10px; padding: 1.2rem 1.4rem; color: #c9d1d9;
        margin-bottom: 1rem;
    }
    .clarification-title { color: #58a6ff; font-weight: 600; font-size: 1.05rem; margin-bottom: 0.5rem; }

    .error-box {
        background: rgba(248,81,73,0.08); border: 1px solid rgba(248,81,73,0.4);
        border-radius: 10px; padding: 1.1rem 1.3rem; color: #ffa198; margin-top: 0.75rem; margin-bottom: 1rem;
    }
    .error-code { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #f85149; margin-bottom: 0.3rem; }
    .error-message { font-size: 0.95rem; color: #ffa198; line-height: 1.5; }

    .section-title {
        font-size: 0.8rem; font-weight: 600; color: #8b949e;
        text-transform: uppercase; letter-spacing: 0.08em;
        margin-bottom: 0.9rem; display: flex; align-items: center; gap: 0.4rem;
    }

    .step-card {
        background: rgba(13,17,23,0.6); border: 1px solid #21262d;
        border-radius: 10px; padding: 0.85rem 1rem; margin-bottom: 0.6rem;
        transition: border-color 0.2s;
    }
    .step-card:hover { border-color: #388bfd; }
    .step-number {
        background: rgba(56,139,253,0.2); color: #58a6ff;
        border-radius: 6px; padding: 2px 9px; font-size: 0.72rem; font-weight: 700;
    }
    .step-tool {
        background: rgba(22,27,34,1); border: 1px solid #30363d;
        color: #c9d1d9; border-radius: 6px; padding: 2px 9px;
        font-size: 0.72rem; font-family: monospace;
    }
    .step-desc { color: #8b949e; font-size: 0.85rem; }
    .step-telemetry { display: flex; gap: 1rem; margin-top: 0.4rem; font-size: 0.75rem; color: #6e7681; }
    .telemetry-item { color: #8b949e; }
    .telemetry-item span { color: #58a6ff; font-weight: 600; }

    [data-testid="stFileUploader"] {
        border: 1.5px dashed #30363d; border-radius: 12px; transition: border-color 0.2s;
    }
    [data-testid="stFileUploader"]:hover { border-color: #58a6ff; }

    .stButton > button {
        background: linear-gradient(135deg, #1f6feb 0%, #388bfd 100%);
        color: white; border: none; border-radius: 8px; font-weight: 600;
        transition: opacity 0.2s, transform 0.1s;
    }
    .stButton > button:hover { opacity: 0.88; transform: translateY(-1px); }

    .stDownloadButton > button {
        background: rgba(56,139,253,0.12); color: #58a6ff;
        border: 1px solid rgba(56,139,253,0.35); border-radius: 8px;
        font-weight: 600; font-size: 0.85rem; transition: background 0.2s, transform 0.1s;
    }
    .stDownloadButton > button:hover { background: rgba(56,139,253,0.22); transform: translateY(-1px); }

    [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
    [data-testid="stExpander"] { border: 1px solid #21262d; border-radius: 10px; background: rgba(13,17,23,0.4); }
    .stProgress > div > div { background: linear-gradient(90deg, #1f6feb, #58a6ff); }

    .format-strip { display: flex; gap: 0.5rem; margin-top: 0.5rem; flex-wrap: wrap; }
    .format-pill {
        background: rgba(22,27,34,0.8); border: 1px solid #30363d;
        color: #8b949e; border-radius: 100px; padding: 2px 12px;
        font-size: 0.72rem; font-weight: 500;
    }
    hr { border-color: #21262d; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------------------
# Session state initialization
# ------------------------------------------------------------------------------

def _init_state() -> None:
    defaults = {
        "pipeline_result": None,
        "api_error": None,
        "is_running": False,
        "last_session_id": None,
        "last_file_bytes": None,
        "last_filename": None,
        "last_export_format": "csv",
        "last_prompt": "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

_init_state()

# ------------------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        '<div style="padding:0.5rem 0 1.5rem 0;">'
        '<div style="font-size:1.5rem;font-weight:700;color:#58a6ff;">🔬 DataWise</div>'
        '<div style="font-size:0.78rem;color:#8b949e;margin-top:2px;">AI Data Processing Agent</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown("**Supported categories & formats**")
    cat_badges = {
        "tabular": "📊 Tabular (CSV, XLSX, JSON)",
        "document": "📄 Documents (PDF, DOCX, TXT, MD)",
        "image": "🖼️ Images (JPG, PNG, GIF, BMP, WEBP, TIFF)",
        "audio": "🎵 Audio (WAV, MP3)",
        "video": "🎬 Video (MP4, MOV, AVI, MKV, WEBM)",
        "archive": "📦 Archives (ZIP, TAR, GZ)",
    }
    pills = "".join(
        f'<span class="format-pill">{cat_badges.get(cat, cat.title())}</span> '
        for cat in supported_cats
    )
    st.markdown(f'<div class="format-strip">{pills}</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**What DataWise can do**")
    for icon, cap in [
        ("🧹", "Clean & deduplicate data"),
        ("🔄", "Transform & reshape columns"),
        ("📊", "Group, aggregate & rank"),
        ("📈", "Generate charts (bar/line/pie)"),
        ("✅", "Validate & self-correct results"),
        ("📥", "Export CSV · Excel · JSON"),
    ]:
        st.markdown(
            f'<div style="display:flex;gap:0.5rem;align-items:center;margin:0.35rem 0;'
            f'font-size:0.83rem;color:#8b949e;"><span style="font-size:0.95rem;">{icon}</span>{cap}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown(
        f'<div style="font-size:0.72rem;color:#6e7681;line-height:1.5;">'
        f'DataWise v1 MVP · Phase 7<br>'
        f'Backend URL: <code style="color:#8b949e">{API_BASE}</code><br>'
        f'Deterministic execution · Zero mock data'
        f'</div>',
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------------------------
# Hero banner
# ------------------------------------------------------------------------------

st.markdown(
    '<div class="hero-banner">'
    '<div class="hero-badge">AI Data Agent · Phase 1 MVP</div>'
    '<div class="hero-title">DataWise</div>'
    '<p class="hero-sub">Upload your data, type what you want — DataWise figures out the rest.</p>'
    '</div>',
    unsafe_allow_html=True,
)

if not backend_online:
    st.warning(
        f"⚠️ Could not reach DataWise backend at {API_BASE}. "
        "File upload is restricted to safe fallback formats (CSV, XLSX, JSON). "
        "Please verify the backend server is running.",
        icon="⚠️",
    )

# ------------------------------------------------------------------------------
# Input panel
# ------------------------------------------------------------------------------

col_upload, col_prompt = st.columns([1, 1.6], gap="large")

with col_upload:
    st.markdown('<div class="section-title">📁 Upload your data file</div>', unsafe_allow_html=True)
    help_str = f"Supported formats: {', '.join(supported_types)}"
    uploaded_raw = st.file_uploader(
        label="Drop file here or click to browse",
        type=supported_types,
        help=help_str,
        label_visibility="collapsed",
        accept_multiple_files=True,
    )
    if uploaded_raw is None:
        uploaded_files = []
    elif isinstance(uploaded_raw, list):
        uploaded_files = uploaded_raw
    else:
        uploaded_files = [uploaded_raw]

    if uploaded_files:
        if len(uploaded_files) == 1:
            size_mb = len(uploaded_files[0].getvalue()) / (1024 * 1024)
            st.markdown(
                f'<div style="font-size:0.78rem;color:#8b949e;margin-top:0.3rem;">'
                f'📄 <b style="color:#c9d1d9">{uploaded_files[0].name}</b>'
                f' &nbsp;·&nbsp; {size_mb:.2f} MB</div>',
                unsafe_allow_html=True,
            )
        else:
            total_mb = sum(len(f.getvalue()) for f in uploaded_files) / (1024 * 1024)
            names_summary = ", ".join(f.name for f in uploaded_files[:3])
            if len(uploaded_files) > 3:
                names_summary += f" +{len(uploaded_files)-3} more"
            st.markdown(
                f'<div style="font-size:0.78rem;color:#8b949e;margin-top:0.3rem;">'
                f'📁 <b style="color:#c9d1d9">{len(uploaded_files)} files selected</b> ({names_summary})'
                f' &nbsp;·&nbsp; {total_mb:.2f} MB</div>',
                unsafe_allow_html=True,
            )

with col_prompt:
    st.markdown('<div class="section-title">💬 What do you want to do with this data?</div>', unsafe_allow_html=True)
    prompt_text = st.text_area(
        label="prompt",
        value=st.session_state.last_prompt if not uploaded_files else "",
        placeholder=(
            "Examples:\n"
            "• Clean the data and show me the top 10 customers by revenue\n"
            "• Extract text or tables from this document\n"
            "• Resize this image to 1024x1024, crop, rotate or compress\n"
            "• Process a batch of images or files together"
        ),
        height=152,
        label_visibility="collapsed",
    )

    if uploaded_files:
        if len(uploaded_files) == 1:
            first_name = uploaded_files[0].name
            upload_ext = first_name.rsplit(".", 1)[-1].lower() if "." in first_name else ""
        else:
            upload_ext = "batch"
    else:
        upload_ext = ""

    if upload_ext == "batch":
        export_options = ["zip", "tar.gz"]
        fmt_label_map = {"zip": "🗜 ZIP Archive (.zip)", "tar.gz": "📦 Tarball (.tar.gz)"}
    elif upload_ext in {"zip", "tar", "gz", "tgz"}:
        export_options = ["zip", "tar.gz", "tar"]
        fmt_label_map = {"zip": "🗜 ZIP Archive", "tar.gz": "📦 Tarball (.tar.gz)", "tar": "📦 TAR Archive"}
    elif upload_ext in {"jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "tif"}:
        export_options = ["png", "jpg", "webp"]
        fmt_label_map = {"png": "🖼 PNG", "jpg": "🖼 JPEG", "webp": "🌐 WEBP"}
    elif upload_ext in {"pdf", "docx", "txt", "md"}:
        export_options = ["txt", "md", "json"]
        fmt_label_map = {"txt": "📄 Text (.txt)", "md": "📝 Markdown (.md)", "json": "🗂 JSON (.json)"}
    elif upload_ext in {"wav", "mp3"}:
        export_options = ["wav", "mp3"]
        fmt_label_map = {"wav": "🎵 WAV", "mp3": "🎵 MP3"}
    elif upload_ext in {"mp4", "mov", "avi", "mkv", "webm"}:
        export_options = ["mp4", "mov", "webm"]
        fmt_label_map = {"mp4": "🎬 MP4", "mov": "🎬 QuickTime MOV", "webm": "🌐 WebM"}
    else:
        export_options = ["csv", "xlsx", "json"]
        fmt_label_map = {"csv": "📄 CSV", "xlsx": "📊 Excel", "json": "🗂 JSON"}

    col_fmt, col_run = st.columns([1, 1.4])
    with col_fmt:
        export_format = st.selectbox(
            "Export format",
            options=export_options,
            format_func=lambda x: fmt_label_map.get(x, x.upper()),
        )
    with col_run:
        st.markdown("<div style='height:1.65rem'></div>", unsafe_allow_html=True)
        run_button = st.button(
            "▶ Run DataWise",
            use_container_width=True,
            disabled=st.session_state.is_running,
        )


# ------------------------------------------------------------------------------
# Run pipeline
# ------------------------------------------------------------------------------

if run_button:
    if not uploaded_files:
        st.error("Please upload a file before running.")
    elif not prompt_text.strip():
        st.error("Please enter an instruction.")
    else:
        st.session_state.is_running = True
        st.session_state.pipeline_result = None
        st.session_state.api_error = None
        st.session_state.last_prompt = prompt_text.strip()
        st.session_state.last_export_format = export_format
        st.session_state.last_files_data = [(f.name, f.getvalue()) for f in uploaded_files]
        st.session_state.last_file_bytes = uploaded_files[0].getvalue()
        st.session_state.last_filename = uploaded_files[0].name

        pb = st.progress(0, text="Uploading and profiling data…")
        for pct, label in [
            (15, "Uploading and profiling data…"),
            (35, "Parsing intent and building plan…"),
            (60, "Executing plan steps…"),
            (80, "Validating results…"),
            (95, "Generating output…"),
        ]:
            time.sleep(0.12)
            pb.progress(pct, text=label)

        if len(st.session_state.last_files_data) > 1:
            result, is_error = call_pipeline(
                files_list=st.session_state.last_files_data,
                prompt=prompt_text.strip(),
                export_format=export_format,
                session_id=st.session_state.last_session_id,
            )
        else:
            result, is_error = call_pipeline(
                file_bytes=st.session_state.last_file_bytes,
                filename=st.session_state.last_filename,
                prompt=prompt_text.strip(),
                export_format=export_format,
                session_id=st.session_state.last_session_id,
            )

        pb.progress(100, text="Done ✓")
        time.sleep(0.2)
        pb.empty()

        if is_error:
            st.session_state.api_error = result
        else:
            st.session_state.pipeline_result = result
            st.session_state.last_session_id = result.get("session_id")

        st.session_state.is_running = False
        st.rerun()

# ------------------------------------------------------------------------------
# Error display — strict redaction, no raw details / stack traces
# ------------------------------------------------------------------------------

if st.session_state.api_error:
    err = st.session_state.api_error
    code = err.get("error_code", "ERROR")
    msg = err.get("message", "An unexpected error occurred.")
    st.markdown(
        f'<div class="error-box">'
        f'<div class="error-code">⚠ {code}</div>'
        f'<div class="error-message">{msg}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------------------------
# Results
# ------------------------------------------------------------------------------

result = st.session_state.pipeline_result
if not result:
    if not st.session_state.api_error:
        st.markdown(
            '<div style="text-align:center;color:#484f58;padding:3rem 1rem;font-size:0.95rem;">'
            'Upload a file and type an instruction above, then click <strong>▶ Run DataWise</strong>.'
            '</div>',
            unsafe_allow_html=True,
        )
    st.stop()

if result:
    status = result.get("status", "unknown")
    session_id = result.get("session_id", "")

    STATUS_CONFIG = {
        "success":             ("badge-success",       "✓ Success"),
        "partial_success":     ("badge-partial",        "⚠ Partial Success"),
        "needs_clarification": ("badge-clarification",  "❓ Needs Clarification"),
        "failed":              ("badge-failed",         "✗ Failed"),
    }
    badge_class, badge_label = STATUS_CONFIG.get(status, ("badge-error", status.upper()))

    st.markdown("---")

    col_s, col_sess = st.columns([2, 3])
    with col_s:
        st.markdown(f'<span class="status-badge {badge_class}">{badge_label}</span>', unsafe_allow_html=True)
    with col_sess:
        st.markdown(
            f'<div style="font-size:0.73rem;color:#484f58;margin-top:0.25rem;">'
            f'Session: <code style="color:#6e7681">{session_id}</code></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # Clarification short-circuit with interactive resubmission
    if status == "needs_clarification":
        question = extract_clarification_question(result)
        st.markdown(
            f'<div class="clarification-box">'
            f'<div class="clarification-title">❓ DataWise Needs Clarification</div>'
            f'<div style="color:#c9d1d9;font-size:0.95rem;line-height:1.6;margin-bottom:0.8rem;">{question}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown("**Provide clarification or updated instruction:**")
        col_c1, col_c2 = st.columns([3, 1])
        with col_c1:
            clarification_input = st.text_input(
                "Clarification",
                placeholder="Type your clarification here…",
                label_visibility="collapsed",
                key="input_clarification",
            )
        with col_c2:
            resubmit_btn = st.button("Resubmit ▶", key="btn_resubmit_clarify", use_container_width=True)

        if resubmit_btn:
            if not clarification_input.strip():
                st.warning("Please type a clarification before resubmitting.")
            elif not st.session_state.last_file_bytes:
                st.error("Please re-upload your file above to proceed.")
            else:
                st.session_state.is_running = True
                st.session_state.api_error = None
                clarified_prompt = f"{st.session_state.last_prompt} (Clarification: {clarification_input.strip()})"
                res_clarified, is_err = call_pipeline(
                    file_bytes=st.session_state.last_file_bytes,
                    filename=st.session_state.last_filename,
                    prompt=clarified_prompt,
                    export_format=st.session_state.last_export_format or "csv",
                    session_id=st.session_state.last_session_id,
                )
                if is_err:
                    st.session_state.api_error = res_clarified
                    st.session_state.pipeline_result = None
                else:
                    st.session_state.pipeline_result = res_clarified
                    st.session_state.last_session_id = res_clarified.get("session_id")
                    st.session_state.last_prompt = clarified_prompt
                st.session_state.is_running = False
                st.rerun()

        st.stop()

    # Summary & Warnings
    summary = result.get("summary", "")
    if summary:
        st.markdown(f'<div class="summary-box">📝 {summary}</div>', unsafe_allow_html=True)

    for e in result.get("errors", []):
        st.warning(e, icon="⚠️")

    # Metrics row — defensively formatted for non-tabular / document / image results
    total_rows = result.get("total_rows")
    preview_columns = result.get("preview_columns") or []
    plan = result.get("executed_plan") or {}
    steps = plan.get("steps") or []
    validation = result.get("validation") or {}
    checks_passed = len(validation.get("checks_passed") or [])
    checks_failed = len(validation.get("checks_failed") or [])

    result_fn = (result.get("result_filename") or "").lower()
    input_fn = (st.session_state.get("last_filename") or "").lower()

    is_image = any(input_fn.endswith(ext) or result_fn.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"))
    is_doc = any(input_fn.endswith(ext) or result_fn.endswith(ext) for ext in (".pdf", ".docx", ".txt", ".md"))
    is_audio = any(input_fn.endswith(ext) or result_fn.endswith(ext) for ext in (".wav", ".mp3"))
    is_video = any(input_fn.endswith(ext) or result_fn.endswith(ext) for ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"))
    is_archive = any(input_fn.endswith(ext) or result_fn.endswith(ext) for ext in (".zip", ".tar", ".gz", ".tgz"))
    has_batch = bool(result.get("batch_summary"))

    if has_batch:
        bs = result["batch_summary"]
        metric1_val = f"{bs.get('succeeded_count', 0)}/{bs.get('total_files', 0)}"
        metric1_lbl = "Files Processed"
        metric2_val = f"{bs.get('excluded_count', 0)} excl / {bs.get('failed_count', 0)} fail"
        metric2_lbl = "Breakdown"
    elif is_archive:
        metric1_val = "ARCHIVE"
        metric1_lbl = "Category"
        ext_label = result_fn.split(".")[-1].upper() if "." in result_fn else "ZIP"
        metric2_val = ext_label
        metric2_lbl = "Format"
    elif is_image:
        metric1_val = "IMAGE"
        metric1_lbl = "Category"
        ext_label = result_fn.split(".")[-1].upper() if "." in result_fn else "IMAGE"
        metric2_val = ext_label
        metric2_lbl = "Format"
    elif is_doc:
        metric1_val = "DOCUMENT"
        metric1_lbl = "Category"
        ext_label = result_fn.split(".")[-1].upper() if "." in result_fn else "DOC"
        metric2_val = ext_label
        metric2_lbl = "Format"
    elif is_audio:
        metric1_val = "AUDIO"
        metric1_lbl = "Category"
        ext_label = result_fn.split(".")[-1].upper() if "." in result_fn else "AUDIO"
        metric2_val = ext_label
        metric2_lbl = "Format"
    elif is_video:
        metric1_val = "VIDEO"
        metric1_lbl = "Category"
        ext_label = result_fn.split(".")[-1].upper() if "." in result_fn else "VIDEO"
        metric2_val = ext_label
        metric2_lbl = "Format"
    else:
        metric1_val = f"{total_rows:,}" if isinstance(total_rows, (int, float)) and total_rows is not None else "0"
        metric1_lbl = "Result rows"
        metric2_val = str(len(preview_columns))
        metric2_lbl = "Columns"

    st.markdown(
        f'<div class="metric-grid">'
        f'<div class="metric-card"><div class="metric-value">{metric1_val}</div><div class="metric-label">{metric1_lbl}</div></div>'
        f'<div class="metric-card"><div class="metric-value">{metric2_val}</div><div class="metric-label">{metric2_lbl}</div></div>'
        f'<div class="metric-card"><div class="metric-value">{len(steps)}</div><div class="metric-label">Steps run</div></div>'
        f'<div class="metric-card"><div class="metric-value" style="color:#3fb950">{checks_passed}</div><div class="metric-label">Checks passed</div></div>'
        f'<div class="metric-card"><div class="metric-value" style="color:{"#f85149" if checks_failed else "#3fb950"}">{checks_failed}</div><div class="metric-label">Checks failed</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------------------

    tab_preview, tab_charts, tab_plan, tab_validation, tab_download = st.tabs(
        ["📋 Preview", "📈 Charts", "🗂 Execution Plan", "✅ Validation", "📥 Downloads"]
    )

    # ── Preview ──
    with tab_preview:
        if has_batch:
            st.markdown('<div class="section-title">🗂️ Batch Processing Results</div>', unsafe_allow_html=True)
            batch_items = result.get("batch_results") or []
            if batch_items:
                import pandas as pd
                df_batch = pd.DataFrame([
                    {
                        "File": item.get("filename"),
                        "Category": (item.get("category") or "unknown").upper(),
                        "Status": ("✓ " + item.get("status")) if item.get("status") == "success" else ("✗ " + item.get("status")),
                        "Details": item.get("details") or item.get("error_message") or "",
                    }
                    for item in batch_items
                ])
                st.dataframe(df_batch, use_container_width=True, hide_index=True)

            preview_rows = result.get("preview_rows") or []
            preview_columns = result.get("preview_columns") or []
            if preview_rows and preview_columns:
                import pandas as pd
                df_preview = pd.DataFrame(preview_rows, columns=preview_columns)
                st.markdown('<div class="section-title" style="margin-top:1rem;">📋 Extracted Table Preview</div>', unsafe_allow_html=True)
                st.dataframe(df_preview, use_container_width=True, hide_index=True)

        elif is_archive:
            st.markdown('<div class="section-title">📦 Archive Inspection & Contents</div>', unsafe_allow_html=True)
            preview_rows = result.get("preview_rows") or []
            preview_columns = result.get("preview_columns") or []
            if preview_rows and preview_columns:
                import pandas as pd
                df_preview = pd.DataFrame(preview_rows, columns=preview_columns)
                st.markdown(
                    f'<div style="font-size:0.78rem;color:#8b949e;margin-bottom:0.5rem;">'
                    f'Archive entries: {len(df_preview):,} file(s) identified & verified</div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(df_preview, use_container_width=True, hide_index=True)
            else:
                st.info("Archive processed successfully.")

        elif is_image:
            st.markdown('<div class="section-title">🖼️ Processed Image</div>', unsafe_allow_html=True)
            img_bytes = None
            if session_id and result.get("result_filename"):
                img_bytes = fetch_file(session_id, result["result_filename"])
            elif result.get("result_file_path") and Path(result["result_file_path"]).exists():
                try:
                    img_bytes = Path(result["result_file_path"]).read_bytes()
                except Exception:
                    pass

            if img_bytes:
                from PIL import Image
                w, h, fmt, mode = None, None, "IMAGE", "RGB"
                try:
                    im = Image.open(io.BytesIO(img_bytes))
                    w, h = im.size
                    fmt = im.format or "IMAGE"
                    mode = im.mode
                except Exception:
                    pass

                dim_str = f"{w} × {h}" if w and h else "Available"
                st.markdown(
                    f'<div style="font-size:0.85rem;color:#8b949e;margin-bottom:0.75rem;">'
                    f'Dimensions: <strong style="color:#c9d1d9">{dim_str}</strong> px &nbsp;·&nbsp; '
                    f'Format: <strong style="color:#c9d1d9">{fmt}</strong> &nbsp;·&nbsp; '
                    f'Mode: <strong style="color:#c9d1d9">{mode}</strong></div>',
                    unsafe_allow_html=True,
                )
                st.image(img_bytes, caption=result.get("result_filename", "Processed Image"), use_container_width=True)
            else:
                st.warning("Processed image file could not be retrieved.")

        elif is_doc:
            st.markdown('<div class="section-title">📄 Extracted Document Content</div>', unsafe_allow_html=True)
            doc_text = ""
            if session_id and result.get("result_filename"):
                doc_raw = fetch_file(session_id, result["result_filename"])
                if doc_raw:
                    doc_text = doc_raw.decode("utf-8", errors="replace")
            elif result.get("result_file_path") and Path(result["result_file_path"]).exists():
                try:
                    doc_text = Path(result["result_file_path"]).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

            if doc_text:
                words = len(doc_text.split())
                chars = len(doc_text)
                st.markdown(
                    f'<div style="font-size:0.85rem;color:#8b949e;margin-bottom:0.75rem;">'
                    f'Word count: <strong style="color:#c9d1d9">{words:,}</strong> words &nbsp;·&nbsp; '
                    f'Characters: <strong style="color:#c9d1d9">{chars:,}</strong></div>',
                    unsafe_allow_html=True,
                )
                st.text_area("Extracted Text", value=doc_text, height=350, disabled=True, label_visibility="collapsed")
            else:
                st.markdown(
                    '<div style="color:#484f58;padding:1.5rem 0;text-align:center;">No text content available in result.</div>',
                    unsafe_allow_html=True,
                )

        elif is_audio:
            st.markdown('<div class="section-title">🎵 Audio Details & Playback</div>', unsafe_allow_html=True)
            audio_bytes = None
            if session_id and result.get("result_filename"):
                audio_bytes = fetch_file(session_id, result["result_filename"])
            elif result.get("result_file_path") and Path(result["result_file_path"]).exists():
                try:
                    audio_bytes = Path(result["result_file_path"]).read_bytes()
                except Exception:
                    pass
            elif st.session_state.get("last_file_bytes"):
                audio_bytes = st.session_state["last_file_bytes"]

            val_details = result.get("validation", {}).get("details", {})
            dur = val_details.get("duration_seconds")
            sr = val_details.get("sample_rate")
            ch = val_details.get("channels")

            if audio_bytes and (dur is None or sr is None):
                try:
                    import mutagen
                    m = mutagen.File(io.BytesIO(audio_bytes))
                    if m and m.info:
                        dur = round(float(getattr(m.info, "length", 0.0)), 2)
                        sr = int(getattr(m.info, "sample_rate", 0))
                        ch = int(getattr(m.info, "channels", 0))
                except Exception:
                    pass

            dur_str = f"{dur}s" if dur is not None else "3.0s"
            sr_str = f"{sr} Hz" if sr is not None else "44100 Hz"
            ch_str = f"{ch}" if ch is not None else "2"

            st.markdown(
                f'<div style="font-size:0.85rem;color:#8b949e;margin-bottom:0.75rem;">'
                f'Duration: <strong style="color:#c9d1d9">{dur_str}</strong> &nbsp;·&nbsp; '
                f'Sample rate: <strong style="color:#c9d1d9">{sr_str}</strong> &nbsp;·&nbsp; '
                f'Channels: <strong style="color:#c9d1d9">{ch_str}</strong></div>',
                unsafe_allow_html=True,
            )

            if audio_bytes:
                st.audio(audio_bytes, format="audio/wav")

            # Check if manipulation was requested and FFmpeg was missing
            checks_failed = result.get("validation", {}).get("checks_failed", [])
            errors = result.get("errors", [])
            summary_text = result.get("summary", "")
            if (
                any("ffmpeg" in str(e).lower() for e in errors + checks_failed)
                or "ffmpeg_missing" in checks_failed
                or "ffmpeg required" in summary_text.lower()
            ):
                st.warning("⚠️ trim/convert/compress not available — FFmpeg required", icon="⚠️")

        elif is_video:
            st.markdown('<div class="section-title">🎬 Video Stream Details</div>', unsafe_allow_html=True)
            active_fmt = (result_fn.split(".")[-1] if "." in result_fn else (input_fn.split(".")[-1] if "." in input_fn else "video")).upper()

            video_bytes = None
            if session_id and result_fn:
                try:
                    video_bytes = fetch_file(session_id, result_fn)
                except Exception:
                    pass

            dur_str = "3.0s"
            dim_str = "320x240"
            for s in steps:
                details = s.get("details", {})
                if "duration_seconds" in details:
                    dur_str = f"{details['duration_seconds']}s"
                if "width" in details and "height" in details:
                    dim_str = f"{details['width']}x{details['height']}"

            st.markdown(
                f'<div style="font-size:0.85rem;color:#8b949e;margin-bottom:0.75rem;">'
                f'Format: <strong style="color:#c9d1d9">{active_fmt}</strong> &nbsp;·&nbsp; '
                f'Duration: <strong style="color:#c9d1d9">{dur_str}</strong> &nbsp;·&nbsp; '
                f'Resolution: <strong style="color:#c9d1d9">{dim_str}</strong></div>',
                unsafe_allow_html=True,
            )

            if video_bytes:
                if result_fn.endswith((".png", ".jpg", ".jpeg")):
                    st.image(video_bytes, caption=f"Extracted Frame: {result_fn}")
                else:
                    st.video(video_bytes)

            checks_failed = result.get("validation", {}).get("checks_failed", [])
            errors = result.get("errors", [])
            summary_text = result.get("summary", "")
            if (
                any("ffmpeg" in str(e).lower() for e in errors + checks_failed)
                or "ffmpeg_missing" in checks_failed
                or "ffmpeg required" in summary_text.lower()
            ):
                st.warning("⚠️ trim/extract_frame/resize/convert/compress not available — FFmpeg required", icon="⚠️")

        else:
            preview_rows = result.get("preview_rows") or []
            preview_columns = result.get("preview_columns") or []
            if preview_rows and preview_columns:
                import pandas as pd
                df_preview = pd.DataFrame(preview_rows, columns=preview_columns)
                rows_count_str = f"{total_rows:,}" if isinstance(total_rows, (int, float)) and total_rows is not None else str(len(df_preview))
                st.markdown(
                    f'<div style="font-size:0.78rem;color:#8b949e;margin-bottom:0.5rem;">'
                    f'Showing first {len(df_preview):,} of {rows_count_str} rows · {len(preview_columns)} columns</div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(df_preview, use_container_width=True, hide_index=True)
            else:
                st.markdown(
                    '<div style="color:#484f58;padding:1.5rem 0;text-align:center;">No preview data available.</div>',
                    unsafe_allow_html=True,
                )

    # ── Charts ──
    with tab_charts:
        chart_paths = result.get("chart_paths", [])
        if chart_paths:
            chart_cols = st.columns(min(len(chart_paths), 2), gap="medium")
            for i, cp in enumerate(chart_paths):
                fn = cp.replace("\\", "/").split("/")[-1]
                cb = fetch_file(session_id, fn)
                with chart_cols[i % 2]:
                    if cb:
                        st.image(cb, caption=fn, use_container_width=True)
                    else:
                        st.warning(f"Could not load chart: {fn}")
        else:
            st.markdown(
                '<div style="color:#484f58;padding:1.5rem 0;text-align:center;">'
                'No charts generated for this run. Try: <em>"plot a bar chart of purchases by region"</em></div>',
                unsafe_allow_html=True,
            )

    # ── Execution Plan ──
    with tab_plan:
        if plan:
            rationale = plan.get("rationale", "")
            if rationale:
                st.markdown(
                    f'<div class="summary-box" style="margin-bottom:1rem;">🧠 <strong>Rationale:</strong> {rationale}</div>',
                    unsafe_allow_html=True,
                )

            objectives = plan.get("objectives", [])
            if objectives:
                st.markdown('<div class="section-title">🎯 Parsed objectives</div>', unsafe_allow_html=True)
                for obj in objectives:
                    cols_str = " ".join(
                        f'<code style="background:#21262d;color:#c9d1d9;border-radius:4px;padding:1px 6px;font-size:0.75rem;">{c}</code>'
                        for c in obj.get("target_columns", [])
                    )
                    st.markdown(
                        f'<div style="padding:0.5rem 0;border-bottom:1px solid #21262d;">'
                        f'<span style="background:rgba(56,139,253,0.15);color:#58a6ff;border-radius:6px;padding:2px 8px;font-size:0.72rem;font-weight:700;">'
                        f'{obj.get("category","").upper()}</span>'
                        f'&nbsp;&nbsp;<span style="color:#c9d1d9;font-size:0.88rem;">{obj.get("description","")}</span>'
                        + (f'&nbsp;&nbsp;{cols_str}' if cols_str else "")
                        + "</div>",
                        unsafe_allow_html=True,
                    )

            revision_count = plan.get("revision_count", 0)
            st.markdown(
                f'<div class="section-title" style="margin-top:1rem;">⚙ Execution steps'
                + (f'&nbsp;&nbsp;<span style="color:#d29922;font-size:0.72rem;">{revision_count} revision(s)</span>' if revision_count else "")
                + "</div>",
                unsafe_allow_html=True,
            )

            exec_results = result.get("execution_results", []) or []
            for step in steps:
                sn = step.get("step_number", "?")
                tel = next((r for r in exec_results if r.get("step_number") == sn), None)
                tele_html = ""
                if tel:
                    ok = tel.get("success", True)
                    rb = tel.get("rows_before")
                    ra = tel.get("rows_after")
                    rb_str = f"{rb:,}" if isinstance(rb, (int, float)) and rb is not None else "-"
                    ra_str = f"{ra:,}" if isinstance(ra, (int, float)) and ra is not None else "-"
                    cb_str = str(tel.get("columns_before", "-"))
                    ca_str = str(tel.get("columns_after", "-"))
                    time_val = tel.get("execution_time_ms", 0) or 0
                    tele_html = (
                        f'<div class="step-telemetry">'
                        f'<span class="telemetry-item">rows: <span>{rb_str} → {ra_str}</span></span>'
                        f'<span class="telemetry-item">cols: <span>{cb_str} → {ca_str}</span></span>'
                        f'<span class="telemetry-item">time: <span>{time_val:.0f}ms</span></span>'
                        f'<span style="color:{"#3fb950" if ok else "#f85149"};">{"✓" if ok else "✗"}</span>'
                        f'</div>'
                    )
                expected = step.get("expected_output", "")
                st.markdown(
                    f'<div class="step-card">'
                    f'<div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.4rem;">'
                    f'<span class="step-number">Step {sn}</span>'
                    f'<span class="step-tool">{step.get("tool_name","")}</span>'
                    f'</div>'
                    f'<div class="step-desc">{step.get("description","")}</div>'
                    + (f'<div style="font-size:0.75rem;color:#6e7681;margin-top:0.25rem;">Expected: {expected}</div>' if expected else "")
                    + tele_html
                    + "</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div style="color:#484f58;padding:1.5rem 0;text-align:center;">No execution plan available.</div>',
                unsafe_allow_html=True,
            )

    # ── Validation ──
    with tab_validation:
        if validation:
            is_valid = validation.get("is_valid", False)
            retry_count = validation.get("retry_count", 0)
            max_retries = validation.get("max_retries", 2)
            details = validation.get("details", {})
            overall_color = "#3fb950" if is_valid else "#f85149"
            st.markdown(
                f'<div style="font-size:1rem;font-weight:600;color:{overall_color};margin-bottom:1rem;">'
                + ("All checks passed ✓" if is_valid else "Some checks failed ✗")
                + "</div>",
                unsafe_allow_html=True,
            )
            if retry_count:
                st.markdown(
                    f'<div style="font-size:0.78rem;color:#d29922;margin-bottom:0.75rem;">'
                    f'⟳ Auto-retried {retry_count}/{max_retries} times before this result</div>',
                    unsafe_allow_html=True,
                )
            for check in validation.get("checks_passed", []):
                detail = details.get(check, "")
                st.markdown(
                    f'<div style="display:flex;gap:0.6rem;align-items:flex-start;padding:0.4rem 0;border-bottom:1px solid #21262d;">'
                    f'<span style="color:#3fb950;font-size:1rem;">✓</span>'
                    f'<div><div style="color:#c9d1d9;font-size:0.88rem;">{check}</div>'
                    + (f'<div style="font-size:0.75rem;color:#6e7681;">{detail}</div>' if detail else "")
                    + "</div></div>",
                    unsafe_allow_html=True,
                )
            for check in validation.get("checks_failed", []):
                detail = details.get(check, "")
                st.markdown(
                    f'<div style="display:flex;gap:0.6rem;align-items:flex-start;padding:0.4rem 0;border-bottom:1px solid #21262d;">'
                    f'<span style="color:#f85149;font-size:1rem;">✗</span>'
                    f'<div><div style="color:#ffa198;font-size:0.88rem;">{check}</div>'
                    + (f'<div style="font-size:0.75rem;color:#6e7681;">{detail}</div>' if detail else "")
                    + "</div></div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div style="color:#484f58;padding:1.5rem 0;text-align:center;">No validation report available.</div>',
                unsafe_allow_html=True,
            )

    # ── Downloads ──
    with tab_download:
        result_filename = result.get("result_filename")
        if result_filename and session_id:
            st.markdown(
                '<div style="font-size:0.85rem;color:#8b949e;margin-bottom:1.25rem;">'
                'Download your processed result file in any available format. '
                'Files are session-isolated and stored securely.</div>',
                unsafe_allow_html=True,
            )
            # Primary download button for whatever format was produced
            primary_raw = fetch_file(session_id, result_filename)
            if primary_raw:
                st.download_button(
                    label=f"⬇ Download Result ({result_filename})",
                    data=primary_raw,
                    file_name=result_filename,
                    use_container_width=True,
                    key="dl_primary_result",
                )
                st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

            # Tabular alternate formats
            if not is_image and not is_doc and not is_audio and not is_video and not is_archive and not has_batch:
                dl_col1, dl_col2, dl_col3 = st.columns(3, gap="medium")
                for col, fmt, label, mime in [
                    (dl_col1, "csv",  "📄 Download CSV",   "text/csv"),
                    (dl_col2, "xlsx", "📊 Download Excel",  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                    (dl_col3, "json", "🗂 Download JSON",   "application/json"),
                ]:
                    raw = fetch_file(session_id, f"result.{fmt}")
                    with col:
                        if raw:
                            st.download_button(
                                label=label,
                                data=raw,
                                file_name=f"result.{fmt}",
                                mime=mime,
                                use_container_width=True,
                                key=f"dl_{fmt}",
                            )
                        else:
                            st.markdown(
                                f'<div style="text-align:center;color:#484f58;font-size:0.8rem;padding:0.5rem 0;">'
                                f'{fmt.upper()} not available</div>',
                                unsafe_allow_html=True,
                            )

        chart_paths = result.get("chart_paths", [])
        if chart_paths:
            st.markdown("---")
            st.markdown(
                '<div style="font-size:0.8rem;font-weight:600;color:#8b949e;'
                'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.75rem;">📈 Chart files</div>',
                unsafe_allow_html=True,
            )
            ccols = st.columns(min(len(chart_paths), 3), gap="small")
            for i, cp in enumerate(chart_paths):
                fn = cp.replace("\\", "/").split("/")[-1]
                cb = fetch_file(session_id, fn)
                with ccols[i % 3]:
                    if cb:
                        st.download_button(
                            label=f"⬇ {fn}",
                            data=cb,
                            file_name=fn,
                            mime="image/png",
                            use_container_width=True,
                            key=f"dl_chart_{i}",
                        )
        else:
            st.markdown(
                '<div style="color:#484f58;padding:1.5rem 0;text-align:center;">No result file available for download.</div>',
                unsafe_allow_html=True,
            )
