import math
import os
import json
from io import BytesIO

import altair as alt
import numpy as np
import pandas as pd

import streamlit as st

# Optional dependencies (chỉ cần khi bật Supabase)
try:
    from supabase import create_client  # type: ignore
except Exception:  # pragma: no cover
    create_client = None

try:
    from passlib.hash import bcrypt  # type: ignore
except Exception:  # pragma: no cover
    bcrypt = None


def supabase_is_configured() -> bool:
    """True khi secrets có đủ SUPABASE_URL + SUPABASE_SERVICE_KEY/ANON_KEY."""
    try:
        sb = st.secrets.get("supabase", {})
        url = sb.get("url")
        key = sb.get("service_key") or sb.get("anon_key")
        return bool(url and key and create_client is not None)
    except Exception:
        return False


@st.cache_resource
def _get_supabase_client():
    sb = st.secrets.get("supabase", {})
    url = sb.get("url")
    key = sb.get("service_key") or sb.get("anon_key")
    if not url or not key:
        raise RuntimeError("Missing Supabase secrets: supabase.url and supabase.service_key/anon_key")
    if create_client is None:
        raise RuntimeError("Missing dependency: supabase (pip install supabase)")
    return create_client(url, key)


def _df_to_records(df: pd.DataFrame) -> list:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []
    _df = df.copy()
    # Chuyển Timestamp -> ISO string
    for c in _df.columns:
        if np.issubdtype(_df[c].dtype, np.datetime64):
            _df[c] = _df[c].astype("datetime64[ns]").dt.strftime("%Y-%m-%d")
    return _df.to_dict(orient="records")


def _records_to_df(records) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def db_load_state(lab_id: str, analyte_key: str) -> dict | None:
    """Load toàn bộ state của 1 xét nghiệm (analyte_key) theo lab_id."""
    if not supabase_is_configured():
        return None
    try:
        client = _get_supabase_client()
        resp = (
            client.table("iqc_state")
            .select("state")
            .eq("lab_id", lab_id)
            .eq("analyte_key", analyte_key)
            .limit(1)
            .execute()
        )
        data = getattr(resp, "data", None) or []
        if not data:
            return None
        state = data[0].get("state")
        if not isinstance(state, dict):
            return None
        # Restore DataFrames
        for k in ["qc_stats", "daily_df", "summary_df", "chart_df"]:
            if k in state and isinstance(state[k], list):
                state[k] = _records_to_df(state[k])
        return state
    except Exception:
        return None


def db_save_state(lab_id: str, analyte_key: str, state: dict) -> bool:
    """Upsert state về Supabase. Chỉ lưu các thành phần cần thiết."""
    if not supabase_is_configured():
        return False
    try:
        client = _get_supabase_client()
        payload = dict(state)
        # Serialize DataFrames
        for k in ["qc_stats", "daily_df", "summary_df", "chart_df"]:
            if k in payload and isinstance(payload[k], pd.DataFrame):
                payload[k] = _df_to_records(payload[k])
        client.table("iqc_state").upsert(
            {"lab_id": lab_id, "analyte_key": analyte_key, "state": payload},
            on_conflict="lab_id,analyte_key",
        ).execute()
        return True
    except Exception:
        return False


def auth_logout():
    for k in ["auth_user", "auth_role", "auth_lab_id", "is_logged_in"]:
        st.session_state.pop(k, None)
    _rerun()


def require_login():
    import streamlit as st

    # --- đọc secrets ---
    sb = st.secrets.get("supabase", {})
    sb_url = sb.get("url", "")
    sb_key = sb.get("service_key", "") or sb.get("anon_key", "")

    if not sb_url or not sb_key:
        st.error("Chưa cấu hình Supabase. Vào Streamlit → Settings → Secrets và thêm supabase.url + supabase.service_key (hoặc supabase.anon_key).")
        st.stop()

    # --- init supabase client ---
    try:
        from supabase import create_client
        supabase = create_client(sb_url, sb_key)
    except Exception as e:
        st.error(f"Lỗi khởi tạo Supabase client: {e}")
        st.stop()

    # --- nếu đã login thì khỏi hỏi lại ---
    if st.session_state.get("auth_ok"):
        return

    st.title("🔐 Đăng nhập IQC")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    col1, col2 = st.columns([1, 3])
    with col1:
        do_login = st.button("Đăng nhập", use_container_width=True)

    if do_login:
        try:
            # gọi hàm SQL: check_login(p_password, p_username)
            res = supabase.rpc(
                "check_login",
                {"p_password": password, "p_username": username.strip()},
            ).execute()

            if res.data and len(res.data) > 0:
                user = res.data[0]
                st.session_state["auth_ok"] = True
                st.session_state["username"] = user.get("username")
                st.session_state["role"] = user.get("role")
                st.session_state["lab_id"] = user.get("lab_id")
                st.success(f"✅ Đăng nhập OK: {st.session_state['username']} | {st.session_state['lab_id']}")
                st.rerun()
            else:
                st.error("❌ Sai username hoặc password.")
        except Exception as e:
            st.error(f"❌ Lỗi đăng nhập: {e}")

    # chưa login thì chặn app
    if not st.session_state.get("auth_ok"):
        st.stop()



def _rerun():
    """Tương thích nhiều phiên bản Streamlit."""
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()

def _img_to_base64(path: str) -> str:
    """Đọc file ảnh và trả về data URI base64 để nhúng vào HTML."""
    try:
        import base64
        if not os.path.exists(path):
            return ""
        ext = os.path.splitext(path)[1].lower()
        mime = "image/png"
        if ext == ".gif":
            mime = "image/gif"
        elif ext in [".jpg", ".jpeg"]:
            mime = "image/jpeg"
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return ""


# =====================================================
# CẤU HÌNH CHUNG & GIAO DIỆN PREMIUM (Warm Gold)
# - Màu được quản lý tập trung qua file JSON: assets/theme_premium.json
# - Streamlit theme (config.toml) chỉ hỗ trợ một phần; CSS bên dưới sẽ "diệt sạch" màu lạc tông.
# =====================================================

def apply_page_config():
    st.set_page_config(
        page_title="Nội kiểm tra chất lượng xét nghiệm",
        page_icon="🧪",
        layout="wide",
    )


THEME_DEFAULT = {
    "bg": "#FFFCF7",
    "panel": "#E1C18A",
    "panelDark": "#D2AA63",
    "gold": "#B88A2B",
    "goldHover": "#A77C25",
    "goldSoft": "rgba(184, 138, 43, 0.18)",
    "text": "#2D2318",
    "text2": "#6B5A44",
    "error": "#A94442",
    "warning": "#C28F2C",
    "cardStrong": "#FFFFFF",
    "border": "rgba(184, 138, 43, 0.34)",
    "shadow": "rgba(15, 23, 42, 0.14)",
    "shadowStrong": "rgba(15, 23, 42, 0.20)",
    "chartBg": "#FFFFFF",
    "grid": "rgba(45, 35, 24, 0.18)",
}


def get_theme() -> dict:
    """Đọc theme từ JSON (nếu có), cache trong session_state."""
    if "qc_theme" in st.session_state and isinstance(st.session_state["qc_theme"], dict):
        return st.session_state["qc_theme"]

    theme_path = os.path.join("assets", "theme_premium.json")
    theme = dict(THEME_DEFAULT)
    try:
        if os.path.exists(theme_path):
            with open(theme_path, "r", encoding="utf-8") as f:
                user_theme = json.load(f)
            if isinstance(user_theme, dict):
                theme.update({k: v for k, v in user_theme.items() if v})
    except Exception:
        # giữ default nếu đọc lỗi
        theme = dict(THEME_DEFAULT)

    st.session_state["qc_theme"] = theme
    return theme


def inject_global_css():
    t = get_theme()
    css = f"""
    <style>
      :root {{
        --qc-bg: {t['bg']};
        --qc-panel: {t['panel']};
        --qc-panel-dark: {t.get('panelDark', t['panel'])};
        --qc-gold: {t['gold']};
        --qc-gold-hover: {t['goldHover']};
        --qc-gold-soft: {t.get('goldSoft','rgba(184, 138, 43, 0.18)')};
        --qc-text: {t['text']};
        --qc-text2: {t['text2']};
        --qc-border: {t.get('border','rgba(185, 150, 60, 0.35)')};
        --qc-card-strong: {t.get('cardStrong','#FFFFFF')};
        --qc-shadow: {t.get('shadow','rgba(15, 23, 42, 0.14)')};
        --qc-shadow-strong: {t.get('shadowStrong','rgba(15, 23, 42, 0.20)')};
        --qc-error: {t.get('error','#A94442')};
        --qc-warning: {t.get('warning','#C28F2C')};
      }}

      /* Hide default multipage nav (we render custom menu) */
      [data-testid="stSidebarNav"] {{ display: none; }}

      /* Nền chính */
      [data-testid="stAppViewContainer"] > .main {{
        background: linear-gradient(180deg, #FFFFFF 0%, var(--qc-bg) 55%, #FFFFFF 120%) !important;
      }}

      /* Sidebar collapse/expand control: force stable "<<" (avoid Material Symbols text fallback) */
      [data-testid="collapsedControl"] button,
      [data-testid="stSidebarCollapseButton"] button {{
        border-radius: 14px !important;
        border: 1px solid rgba(184, 138, 43, 0.35) !important;
        background: rgba(255,255,255,0.72) !important;
        box-shadow: 0 10px 18px rgba(15,23,42,0.10);
      }}
      /* Hide anything inside the control (icon or its text fallback) */
      [data-testid="collapsedControl"] button *,
      [data-testid="stSidebarCollapseButton"] button * {{
        visibility: hidden !important;
      }}
      /* Paint our own symbol; move it slightly down for better balance */
      [data-testid="collapsedControl"] button,
      [data-testid="stSidebarCollapseButton"] button {{
        position: relative !important;
      }}
      [data-testid="collapsedControl"] button::after,
      [data-testid="stSidebarCollapseButton"] button::after {{
        content: "<<";
        position: absolute;
        left: 50%;
        top: 52%;
        transform: translate(-50%, -50%) translateY(2px);
        font-weight: 900;
        font-size: 18px;
        color: var(--qc-gold);
        letter-spacing: -0.08em;
        line-height: 1;
        pointer-events: none;
      }}

      /* Luxury spacing */
      .block-container {{
        padding-top: 1.1rem !important;
        padding-bottom: 2.6rem !important;
        padding-left: 2.0rem !important;
        padding-right: 2.0rem !important;
        max-width: 1280px !important;
      }}

      /* Top header bar */
      [data-testid="stHeader"] {{ background: rgba(255,255,255,0) !important; }}
      body {{ background: var(--qc-bg) !important; color: var(--qc-text) !important; }}

      /* Typography (luxury dashboard) */
      html, body, [data-testid="stAppViewContainer"] * {{
        font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      }}
      h1, h2, h3, h4, .qc-title-block h1 {{
        font-family: Georgia, "Times New Roman", Times, serif;
      }}

      /* Sidebar (premium stronger contrast) */
      [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, var(--qc-panel-dark) 0%, var(--qc-panel) 100%) !important;
        border-right: 1px solid rgba(184, 138, 43, 0.40) !important;
      }}
      [data-testid="stSidebar"] * {{ color: var(--qc-text) !important; }}

      /* Center sidebar logo */
      [data-testid="stSidebar"] img {{
        display:block;
        margin-left:auto;
        margin-right:auto;
      }}

      /* Custom nav links (page_link) */
      .qc-nav a, .qc-nav a:visited {{ text-decoration:none !important; }}
      .qc-nav [data-testid="stPageLink"] a {{
        border-radius: 16px;
        padding: 0.60rem 0.85rem;
        display: block;
        border: 1px solid rgba(184, 138, 43, 0.26);
        background: rgba(255,255,255,0.62);
        color: var(--qc-text) !important;
        margin-bottom: 0.45rem;
        box-shadow: 0 10px 18px rgba(15,23,42,0.08);
        white-space: normal !important;
        word-break: break-word !important;
      }}
      /* Ensure long Vietnamese labels wrap instead of truncating */
      .qc-nav [data-testid="stPageLink"] a * {{
        white-space: normal !important;
        word-break: break-word !important;
        overflow: visible !important;
        text-overflow: clip !important;
      }}
      /* Streamlit sometimes applies ellipsis on specific text nodes */
      .qc-nav [data-testid="stPageLink"] a p,
      .qc-nav [data-testid="stPageLink"] a span {{
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
      }}
      .qc-nav [data-testid="stPageLink"] a:hover {{
        border: 1px solid rgba(184, 138, 43, 0.62);
        background: rgba(184, 138, 43, 0.14);
        transform: translateY(-1px);
      }}
      /* Active page (make it clearly highlighted/premium) */
      .qc-nav [data-testid="stPageLink"] a[aria-current="page"],
      .qc-nav [data-testid="stPageLink"] a[aria-current="true"] {{
        background: var(--qc-gold-soft) !important;
        border: 1px solid rgba(184, 138, 43, 0.85) !important;
        box-shadow: 0 14px 26px rgba(15,23,42,0.14);
        font-weight: 800;
      }}
      .qc-nav [data-testid="stPageLink"] a[aria-current="page"] {{
        background: var(--qc-gold) !important;
        color: #ffffff !important;
        border: 1px solid rgba(184, 138, 43, 0.78) !important;
        box-shadow: 0 16px 28px rgba(15,23,42,0.16);
      }}
      .qc-nav [data-testid="stPageLink"] a[aria-current="page"] svg {{
        fill: #ffffff !important;
      }}

      /* Header chính */
      .qc-header {{
        display:flex;
        align-items:center;
        gap: 1rem;
        margin-top: 0.5rem;
        margin-bottom: 1.2rem;
        padding: 0.72rem 0.70rem 0.72rem 0.95rem; /* giảm padding phải để GIF sát lề hơn */
        border-radius: 22px;
        border: 1px solid rgba(184, 138, 43, 0.86);
        position: relative;
        overflow: hidden;
        background:
          radial-gradient(circle at 18% 10%, rgba(184,138,43,0.22), transparent 54%),
          radial-gradient(circle at 82% 18%, rgba(210,170,99,0.28), transparent 58%),
          linear-gradient(135deg, #ffffff 0%, var(--qc-bg) 65%, #ffffff 120%);
        color: var(--qc-text);
        box-shadow: 0 26px 54px var(--qc-shadow);
      }}

      /* Header layout: giữ text bên trái, GIF sát lề phải */
      .qc-header-inner {{
        width: 100%;
        display: flex;
        align-items: center;
        gap: 16px;
      }}
      .qc-title-block {{ flex: 1 1 auto; }}
      .qc-gif-wrap {{
        flex: 0 0 auto;
        margin-left: auto;
        display: flex;
        align-items: center;
        justify-content: flex-end;
        padding-right: 0 !important;
      }}

      /* Top strip to make banner look darker/premium */
      .qc-header::before {{
        content: "";
        position: absolute;
        left: 0;
        right: 0;
        top: 0;
        height: 10px;
        background: linear-gradient(90deg, var(--qc-panel-dark), var(--qc-gold));
        opacity: 0.95;
      }}

      /* GIF in header: smaller and snug to banner height */
      .qc-header-gif {{
        height: 150px; /* smaller than before */
        width: auto;
        border-radius: 16px;
        border: 1px solid rgba(184, 138, 43, 0.42);
        box-shadow: 0 14px 26px rgba(15,23,42,0.14);
        display:block;
        margin-left: auto;
        margin-right: -6px; /* sát lề phải hơn */
      }}
      .qc-title-block h1 {{
        margin: 0;
        font-size: 1.25rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--qc-text);
      }}
      .qc-title-block p {{ margin: 0.4rem 0 0; font-size: 0.9rem; opacity: 0.92; color: var(--qc-text2); }}
      .qc-badge {{
        display:inline-flex;
        align-items:center;
        gap:0.4rem;
        padding:0.18rem 0.65rem;
        font-size:0.72rem;
        border-radius:999px;
        background: rgba(184,138,43,0.16);
        border: 1px solid rgba(184,138,43,0.62);
        margin-bottom:0.5rem;
        color: var(--qc-text);
      }}

      /* Cards */
      .qc-card {{
        background: var(--qc-card-strong);
        border-radius: 22px;
        padding: 1.05rem 1.15rem;
        border: 1px solid rgba(184,138,43,0.22);
        box-shadow: 0 28px 64px var(--qc-shadow-strong);
      }}
      .qc-card-title {{
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--qc-text2);
        margin-bottom: 0.25rem;
      }}
      .qc-card-value {{ font-size: 1.1rem; font-weight: 700; color: var(--qc-text); }}
      .qc-card-sub {{ margin-top:0.15rem; font-size:0.8rem; color: var(--qc-text2); }}

      /* Rule chip */
      .qc-rule-tag {{ display:flex; flex-wrap:wrap; gap:0.25rem; margin-top:0.3rem; }}
      .qc-rule-chip {{
        background: var(--qc-gold-soft);
        color: var(--qc-text);
        border-radius: 999px;
        padding: 0.15rem 0.55rem;
        font-size: 0.75rem;
        border: 1px solid rgba(184,138,43,0.55);
      }}

      /* Buttons */
      div.stButton > button {{
        border-radius: 14px !important;
        border: 1px solid rgba(184,138,43,0.85) !important;
        background: var(--qc-gold) !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        letter-spacing: 0.02em;
        box-shadow: 0 18px 34px rgba(15,23,42,0.14);
      }}
      div.stButton > button:hover {{
        transform: translateY(-1px);
        box-shadow: 0 26px 44px rgba(15,23,42,0.20);
        border: 1px solid rgba(184,138,43,0.95) !important;
        background: var(--qc-gold-hover) !important;
      }}

      /* Tabs */
      button[data-baseweb="tab"] {{
        border-radius: 999px !important;
        border: 1px solid rgba(184,138,43,0.42) !important;
        color: var(--qc-text) !important;
        background: rgba(255,255,255,0.75) !important;
      }}
      button[data-baseweb="tab"][aria-selected="true"] {{
        background: var(--qc-gold-soft) !important;
        border-color: rgba(184,138,43,0.70) !important;
      }}

      /* Widget overrides */
      div[data-baseweb="select"] > div,
      div[data-baseweb="input"] > div,
      div[data-baseweb="textarea"] > div {{
        border-radius: 12px;
        border-color: rgba(185,150,60,0.30) !important;
        background: rgba(255,255,255,0.88);
      }}
      div[data-baseweb="select"] > div:focus-within,
      div[data-baseweb="input"] > div:focus-within,
      div[data-baseweb="textarea"] > div:focus-within {{
        box-shadow: 0 0 0 3px rgba(201,162,77,0.22) !important;
        border-color: rgba(185,150,60,0.55) !important;
      }}

      /* Radio/checkbox accent */
      input[type="radio"], input[type="checkbox"] {{ accent-color: {t['gold']}; }}

      /* Dataframe rounding */
      [data-testid="stDataFrame"] {{
        border-radius: 14px;
        overflow: hidden;
        border: 1px solid rgba(185,150,60,0.18);
      }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def _init_multi_analyte_store():
    """Khởi tạo cấu trúc lưu nhiều xét nghiệm trong session_state."""
    if "iqc_multi" not in st.session_state:
        st.session_state["iqc_multi"] = {}
    if "active_analyte" not in st.session_state:
        st.session_state["active_analyte"] = "Xét nghiệm 1"

    store = st.session_state["iqc_multi"]
    active = st.session_state["active_analyte"]

    if active not in store:
        # Default in-memory state
        store[active] = {
            "config": {
                "test_name": active,
                "unit": "",
                "device": "",
                "method": "",
                "qc_name": "",
                "qc_lot": "",
                "qc_expiry": "",
                "num_levels": 2,
                "sigma_value": 6.0,
            },
            "baseline_df": None,
            "qc_stats": None,
            "daily_df": None,
            "z_df": None,
            "summary_df": None,
            "point_df": None,
            "export_df": None,
        }

        # (NEW) Nếu đã đăng nhập + có Supabase secrets -> load state đã lưu
        try:
            user = st.session_state.get("current_user")
            if user and user.get("lab_id") and supabase_is_configured():
                loaded = db_load_state(user["lab_id"], active)
                if loaded:
                    store[active] = loaded
        except Exception:
            # Không làm app crash nếu DB lỗi
            pass
    st.session_state["iqc_multi"] = store
    return store, active


def get_current_analyte_state():
    """Trả về dict state của xét nghiệm đang chọn."""
    store, active = _init_multi_analyte_store()
    return store[active]


def update_current_analyte_state(**kwargs):
    """Cập nhật state cho xét nghiệm đang chọn."""
    store, active = _init_multi_analyte_store()
    cur = store.get(active, {})
    cur.update(kwargs)
    store[active] = cur
    st.session_state["iqc_multi"] = store

    # (NEW) autosave DB (nếu đã login)
    try:
        user = st.session_state.get("current_user")
        if user and user.get("lab_id") and supabase_is_configured():
            db_save_state(user["lab_id"], active, cur)
    except Exception:
        pass


# =====================================================
# SIDEBAR & HEADER
# =====================================================


def render_sidebar():
    """
    Sidebar dùng chung cho tất cả pages.
    Hỗ trợ multi-analyte: chọn / tạo xét nghiệm.
    """
    store, active = _init_multi_analyte_store()

    with st.sidebar:
        # Logo nhỏ + menu điều hướng (ẩn menu mặc định bằng CSS)
        logo_path = "assets/qc_logo.png"
        if os.path.exists(logo_path):
            st.image(logo_path, width=120)

        st.markdown('<div class="qc-nav">', unsafe_allow_html=True)
        st.page_link("app.py", label="Trang chủ", icon="🏠")
        st.page_link("pages/1_Thiet_lap_chi_so_thong_ke.py", label="Thiết lập chỉ số thống kê", icon="🧮")
        st.page_link("pages/2_Ghi_nhan_va_danh_gia.py", label="Ghi nhận và đánh giá kết quả", icon="✍️")
        st.page_link("pages/3_Bieu_do_Levey_Jennings.py", label="Levey-Jennings", icon="📈")
        st.page_link("pages/4_Huong_dan_va_About.py", label="Hướng dẫn", icon="📘")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### 🧬 Chọn xét nghiệm")

        analyte_names = sorted(store.keys())
        if active not in analyte_names:
            analyte_names.insert(0, active)

        selected = st.selectbox(
            "Xét nghiệm đang làm việc",
            analyte_names,
            index=analyte_names.index(active) if active in analyte_names else 0,
        )
        st.session_state["active_analyte"] = selected
        store, active = _init_multi_analyte_store()
        cur = store[active]

        new_name = st.text_input("Tên xét nghiệm mới")
        if st.button("➕ Thêm xét nghiệm mới", use_container_width=True):
            if new_name.strip():
                name = new_name.strip()
                if name not in store:
                    store[name] = {
                        "config": {
                            "test_name": name,
                            "unit": "",
                            "device": "",
                            "method": "",
                            "qc_name": "",
                            "qc_lot": "",
                            "qc_expiry": "",
                            "num_levels": 2,
                            "sigma_value": 6.0,
                        },
                        "baseline_df": None,
                        "qc_stats": None,
                        "daily_df": None,
                        "z_df": None,
                        "summary_df": None,
                        "point_df": None,
                        "export_df": None,
                    }
                st.session_state["active_analyte"] = name
                store, active = _init_multi_analyte_store()
                cur = store[active]
                _rerun()

        st.markdown("---")
        st.markdown("### ⚙️ Thông tin xét nghiệm")

        cfg = cur.get("config", {})
        test_name = st.text_input("Tên xét nghiệm", value=cfg.get("test_name", ""))
        unit = st.text_input("Đơn vị đo", value=cfg.get("unit", ""))
        device = st.text_input("Thiết bị", value=cfg.get("device", ""))
        method = st.text_input("Phương pháp", value=cfg.get("method", ""))
        qc_name = st.text_input("Tên QC", value=cfg.get("qc_name", ""))
        qc_lot = st.text_input("LOT QC", value=cfg.get("qc_lot", ""))
        qc_expiry = st.text_input("Hạn dùng QC", value=cfg.get("qc_expiry", ""))


        st.markdown("---")
        st.markdown("### 🧾 Thông tin biểu mẫu")
        report_period = st.text_input("Tháng / Năm", value=cfg.get("report_period", ""))
        don_vi = st.text_input("Đơn vị", value=cfg.get("don_vi", ""))
        phien_ban = st.text_input("Phiên bản", value=cfg.get("phien_ban", ""))
        ngay_hieu_luc = st.text_input("Ngày hiệu lực", value=cfg.get("ngay_hieu_luc", ""))

        st.markdown("---")
        st.markdown("### 🎚️ Cấu hình nội kiểm")

        num_levels = st.radio(
            "Số mức QC",
            [2, 3],
            index=0 if cfg.get("num_levels", 2) == 2 else 1,
            horizontal=True,
        )

        sigma_value = st.number_input(
            "Sigma phương pháp (nếu có)",
            min_value=0.0,
            value=float(cfg.get("sigma_value", 6.0)),
            step=0.1,
            help="Nếu =0 hoặc <4, app dùng bộ quy tắc nhóm <4-sigma.",
        )

        st.markdown("---")
        st.caption(
            "💡 Copyright © 2025 LINH CSQL."
        )

    cfg_new = {
        "test_name": test_name,
        "unit": unit,
        "device": device,
        "method": method,
        "qc_name": qc_name,
        "qc_lot": qc_lot,
        "qc_expiry": qc_expiry,
        "report_period": report_period,
        "don_vi": don_vi,
        "phien_ban": phien_ban,
        "ngay_hieu_luc": ngay_hieu_luc,
        "num_levels": num_levels,
        "sigma_value": sigma_value,
    }
    cur["config"] = cfg_new
    store[active] = cur
    st.session_state["iqc_multi"] = store
    st.session_state["active_analyte"] = active
    st.session_state["iqc_config"] = cfg_new  # để tiện nếu code cũ có dùng
    return cfg_new


def render_global_header():
    gif_data = _img_to_base64("assets/header_anim.gif")
    gif_html = (
        f"<img class='qc-header-gif' src='{gif_data}' alt='IQC animation'/>"
        if gif_data else ""
    )

    st.markdown(
        f"""
        <div class="qc-header">
          <div class="qc-header-inner">
            <div class="qc-title-block">
              <div class="qc-badge">
                <span>Internal Quality Control • Levey–Jennings • Westgard • Sigma</span>
              </div>
              <h1>PHẦN MỀM NỘI KIỂM TRA CHẤT LƯỢNG XÉT NGHIỆM</h1>
              <p>🧪 Theo dõi IQC, cảnh báo sai số theo Westgard, tối ưu hoá nội kiểm dựa trên sigma.</p>
            </div>
            <div class="qc-gif-wrap">{gif_html}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_top_info_cards(cfg, sigma_cat, active_rules):
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            f"""
            <div class="qc-card">
              <div class="qc-card-title">🧫 Xét nghiệm</div>
              <div class="qc-card-value">{cfg['test_name'] or "Chưa nhập"}</div>
              <div class="qc-card-sub">
                Đơn vị: {cfg['unit'] or "—"}<br/>
                QC: {(cfg['qc_name'] + " • LOT " + cfg['qc_lot']) if (cfg['qc_name'] or cfg['qc_lot']) else "—"}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            f"""
            <div class="qc-card">
              <div class="qc-card-title">🔬 Thiết bị & Phương pháp</div>
              <div class="qc-card-value">{cfg['device'] or "Chưa nhập"}</div>
              <div class="qc-card-sub">
                Phương pháp: {cfg['method'] or "—"}<br/>
                Hạn dùng QC: {cfg['qc_expiry'] or "—"}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if active_rules:
        chips = "".join(
            f"<span class='qc-rule-chip'>{r}</span>" for r in sorted(active_rules)
        )
        rules_html = f"<div class='qc-rule-tag'>{chips}</div>"
    else:
        rules_html = "<span style='font-size:0.8rem;color:#d1d5db;'>Chưa có quy tắc</span>"

    with c3:
        st.markdown(
            f"""
            <div class="qc-card qc-card-ghost">
              <div class="qc-card-title">📐 Nhóm sigma & Quy tắc</div>
              <div class="qc-card-value">{cfg['sigma_value']:.2f} σ → {sigma_cat}-sigma</div>
              <div class="qc-card-sub">
                Bộ quy tắc loại bỏ áp dụng:
              </div>
              {rules_html}
            </div>
            """,
            unsafe_allow_html=True,
        )


# =====================================================
# HÀM TÍNH TOÁN
# =====================================================


def compute_stats(values):
    arr = np.array([v for v in values if v not in (None, "")])
    arr = arr.astype(float) if arr.size > 0 else arr

    if arr.size == 0:
        return np.nan, np.nan, np.nan

    mean = float(arr.mean())
    sd = float(arr.std(ddof=1)) if arr.size > 1 else np.nan
    cv = float(sd / mean * 100) if (mean != 0 and not np.isnan(sd)) else np.nan
    return mean, sd, cv


def compute_zscore(value, mean, sd):
    try:
        v = float(value)
        if sd is None or sd == 0 or np.isnan(sd):
            return np.nan
        return (v - mean) / sd
    except Exception:
        return np.nan


def extract_rule_short(text):
    if not isinstance(text, str) or not text.strip():
        return ""
    codes = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        token = part.split()[0]
        if token not in codes:
            codes.append(token)
    return ", ".join(codes)


def create_levey_jennings_chart(df_long, title):
    if df_long.empty:
        return None

    df = df_long.copy()
    df["z_clip"] = df["z_score"].clip(-3, 3)
    df["shape"] = np.where(df["z_score"].abs() > 3, "square", "circle")

    base = alt.Chart(df).encode(
        x=alt.X("Run:O", title="Ngày / Lần"),
        y=alt.Y("z_clip:Q", title="Z-score"),
    )

    lines = base.mark_line().encode(
        color=alt.Color("Control:N", title="Mức QC"),
        detail="Control:N",
    )

    points = base.mark_point(filled=True, size=70).encode(
        color=alt.Color("Control:N", title="Mức QC"),
        shape=alt.Shape("shape:N", legend=None),
        tooltip=[
            "Run",
            "Control",
            alt.Tooltip("z_score:Q", format=".4f", title="z-score"),
            "point_status",
            "rule_codes",
        ],
    )

    rules_data = pd.DataFrame(
        {
            "y": [0, 1, -1, 2, -2, 3, -3],
            "label": ["0", "+1 SD", "-1 SD", "+2 SD", "-2 SD", "+3 SD", "-3 SD"],
            "color": ["black", "green", "green", "orange", "orange", "red", "red"],
        }
    )

    rules = alt.Chart(rules_data).mark_rule().encode(
        y="y:Q",
        color=alt.Color("color:N", scale=None, legend=None),
    )

    text_labels = alt.Chart(rules_data).mark_text(align="left", dx=3, dy=-3).encode(
        y="y:Q",
        text="label:N",
        color=alt.Color("color:N", scale=None, legend=None),
    )

    ext_rules_data = pd.DataFrame({"y": [3.5, -3.5]})
    ext_rules = alt.Chart(ext_rules_data).mark_rule(
        strokeDash=[4, 4], color="black"
    ).encode(y="y:Q")

    viol_points = base.transform_filter(
        "datum.point_status != 'Đạt'"
    ).mark_point(filled=False, strokeWidth=2).encode(
        color=alt.value("red"),
        shape=alt.Shape("shape:N", legend=None),
        size=alt.value(200),
    )

    viol_text = base.transform_filter(
        "datum.point_status != 'Đạt'"
    ).mark_text(dy=-12, color="red").encode(text="rule_short:N")

    t = get_theme()
    chart = (
        rules + text_labels + ext_rules + lines + points + viol_points + viol_text
    ).properties(title=title, height=400, background=t.get("chartBg", "#FFFDF7"))

    chart = (
        chart
        .configure_view(stroke=None)
        .configure_axis(
            grid=True,
            gridColor=t.get("grid", "rgba(58, 46, 31, 0.18)"),
            domainColor=t.get("grid", "rgba(58, 46, 31, 0.18)"),
            labelColor=t.get("text2", "#6B5A44"),
            titleColor=t.get("text", "#3A2E1F"),
        )
        .configure_title(color=t.get("text", "#3A2E1F"), fontSize=14)
        .configure_legend(labelColor=t.get("text", "#3A2E1F"), titleColor=t.get("text", "#3A2E1F"))
    )

    return chart


def get_sigma_category_and_rules(sigma, num_levels):
    if sigma is None or (isinstance(sigma, float) and math.isnan(sigma)) or sigma == 0:
        cat = "<4"
    else:
        if sigma >= 6:
            cat = "6"
        elif sigma >= 5:
            cat = "5"
        elif sigma >= 4:
            cat = "4"
        else:
            cat = "<4"

    rules = {"1_3s"}  # luôn có 1_3s

    if num_levels == 2:
        if cat == "6":
            pass
        elif cat == "5":
            rules.update(["R_4s", "2_2s"])
        elif cat == "4":
            rules.update(["R_4s", "2_2s", "4_1s"])
        else:
            rules.update(["R_4s", "2_2s", "4_1s", "10x"])
    else:
        if cat == "6":
            pass
        elif cat == "5":
            rules.update(["R_4s", "2of3_2s"])
        elif cat == "4":
            rules.update(["R_4s", "2of3_2s", "3_1s"])
        else:
            rules.update(["R_4s", "2of3_2s", "3_1s", "9x"])

    return cat, rules


def evaluate_westgard(z_df, num_levels, sigma):
    runs = z_df["Ngày/Lần"].tolist()
    z_cols = [c for c in z_df.columns if c.startswith("z_Ctrl")]
    z_cols = sorted(z_cols, key=lambda x: int(x.split("Ctrl ")[1]))
    Z = z_df[z_cols].to_numpy(dtype=float)
    n_runs, n_levels = Z.shape

    sigma_cat, active_rules = get_sigma_category_and_rules(sigma, num_levels)

    warn_by_run = [set() for _ in range(n_runs)]
    rej_by_run = [set() for _ in range(n_runs)]
    warn_point = [[set() for _ in range(n_levels)] for _ in range(n_runs)]
    rej_point = [[set() for _ in range(n_levels)] for _ in range(n_runs)]

    def add_warn(i, msg, levels=None):
        warn_by_run[i].add(msg)
        if levels is not None:
            for l in levels:
                warn_point[i][l].add(msg)

    def add_rej(i, msg, levels=None):
        rej_by_run[i].add(msg)
        if levels is not None:
            for l in levels:
                rej_point[i][l].add(msg)

    # 1_2s
    for i in range(n_runs):
        for l in range(n_levels):
            z = Z[i, l]
            if np.isnan(z):
                continue
            if 2 <= abs(z) < 3:
                msg = f"1_2s (Ctrl {l+1}, z={z:.2f})"
                add_warn(i, msg, levels=[l])

    # 1_3s
    if "1_3s" in active_rules:
        for i in range(n_runs):
            for l in range(n_levels):
                z = Z[i, l]
                if np.isnan(z):
                    continue
                if abs(z) >= 3:
                    msg = f"1_3s (Ctrl {l+1}, z={z:.2f})"
                    add_rej(i, msg, levels=[l])

    # 2_2s
    if "2_2s" in active_rules:
        # cùng lần chạy, 2 mức khác nhau
        for i in range(n_runs):
            idxs = []
            signs = []
            for l in range(n_levels):
                z = Z[i, l]
                if np.isnan(z):
                    continue
                if 2 <= abs(z) < 3:
                    idxs.append(l)
                    signs.append(np.sign(z) or 1)
            for s in (+1, -1):
                levels = [l for l, sgn in zip(idxs, signs) if sgn == s]
                if len(levels) >= 2:
                    msg = (
                        "2_2s (cùng lần chạy, "
                        + ", ".join(f"Ctrl {l+1}" for l in levels)
                        + " cùng phía 2–3SD)"
                    )
                    add_rej(i, msg, levels=levels)

        # cùng mức, 2 lần liên tiếp
        for l in range(n_levels):
            for i in range(1, n_runs):
                z1, z2 = Z[i - 1, l], Z[i, l]
                if any(np.isnan([z1, z2])):
                    continue
                if (
                    2 <= abs(z1) < 3
                    and 2 <= abs(z2) < 3
                    and np.sign(z1) == np.sign(z2)
                ):
                    msg = f"2_2s (Ctrl {l+1}, runs {runs[i-1]}–{runs[i]})"
                    add_rej(i, msg, levels=[l])

    # 2/3_2s
    if "2of3_2s" in active_rules:
        # cùng mức, 3 lần liên tiếp
        for l in range(n_levels):
            for i in range(2, n_runs):
                window_idx = [i - 2, i - 1, i]
                vals = [Z[j, l] for j in window_idx]
                if all(np.isnan(v) for v in vals):
                    continue
                for s in (+1, -1):
                    cnt = sum(
                        (not np.isnan(v)) and abs(v) >= 2 and np.sign(v) == s
                        for v in vals
                    )
                    if cnt >= 2:
                        msg = f"2/3_2s (Ctrl {l+1}, runs {runs[i-2]}–{runs[i]})"
                        add_rej(i, msg, levels=[l])
                        break

        # cùng lần chạy, nhiều mức
        for i in range(n_runs):
            vals = [Z[i, l] for l in range(n_levels)]
            for s in (+1, -1):
                levels = [
                    l
                    for l, v in enumerate(vals)
                    if (not np.isnan(v)) and abs(v) >= 2 and np.sign(v) == s
                ]
                if len(levels) >= 2:
                    msg = f"2/3_2s (run {runs[i]}, ≥2 mức QC cùng phía ≥2SD)"
                    add_rej(i, msg, levels=levels)
                    break

    # R_4s
    if "R_4s" in active_rules:
        for i in range(n_runs):
            vals = [Z[i, l] for l in range(n_levels) if not np.isnan(Z[i, l])]
            if len(vals) < 2:
                continue
            maxz = max(vals)
            minz = min(vals)
            if (maxz - minz) >= 4 and maxz >= 2 and minz <= -2:
                levels = []
                for l in range(n_levels):
                    if np.isnan(Z[i, l]):
                        continue
                    if Z[i, l] == maxz or Z[i, l] == minz:
                        levels.append(l)
                msg = f"R_4s (run {runs[i]}, chênh lệch ≥4SD giữa các mức QC)"
                add_rej(i, msg, levels=levels)

    # 3_1s
    if "3_1s" in active_rules:
        for l in range(n_levels):
            for i in range(2, n_runs):
                window_idx = [i - 2, i - 1, i]
                vals = [Z[j, l] for j in window_idx]
                if any(np.isnan(v) for v in vals):
                    continue
                for s in (+1, -1):
                    if all(abs(v) >= 1 and np.sign(v) == s for v in vals):
                        msg = f"3_1s (Ctrl {l+1}, runs {runs[i-2]}–{runs[i]})"
                        add_rej(i, msg, levels=[l])
                        break

        if n_levels >= 3:
            for i in range(n_runs):
                vals = [Z[i, l] for l in range(n_levels)]
                if any(np.isnan(v) for v in vals):
                    continue
                for s in (+1, -1):
                    levels = [
                        l for l, v in enumerate(vals) if abs(v) >= 1 and np.sign(v) == s
                    ]
                    if len(levels) >= 3:
                        msg = f"3_1s (run {runs[i]}, ≥3 mức QC cùng phía ≥1SD)"
                        add_rej(i, msg, levels=levels)
                        break

    # 4_1s
    if "4_1s" in active_rules:
        for l in range(n_levels):
            for i in range(3, n_runs):
                window_idx = [i - 3, i - 2, i - 1, i]
                vals = [Z[j, l] for j in window_idx]
                if any(np.isnan(v) for v in vals):
                    continue
                for s in (+1, -1):
                    if all(abs(v) >= 1 and np.sign(v) == s for v in vals):
                        msg = f"4_1s (Ctrl {l+1}, runs {runs[i-3]}–{runs[i]})"
                        add_rej(i, msg, levels=[l])
                        break

        if n_levels == 2:
            for i in range(1, n_runs):
                idxs = [i - 1, i]
                vals = [Z[j, l] for j in idxs for l in range(n_levels)]
                if any(np.isnan(v) for v in vals):
                    continue
                for s in (+1, -1):
                    if all(abs(v) >= 1 and np.sign(v) == s for v in vals):
                        msg = "4_1s (2 lần chạy x 2 mức QC, tất cả cùng phía ≥1SD)"
                        add_rej(i, msg, levels=[0, 1])
                        break

    # 9x
    if "9x" in active_rules:
        for l in range(n_levels):
            for i in range(8, n_runs):
                window_idx = list(range(i - 8, i + 1))
                vals = [Z[j, l] for j in window_idx]
                if any(np.isnan(v) for v in vals):
                    continue
                for s in (+1, -1):
                    if all(np.sign(v) == s for v in vals):
                        msg = f"9x (Ctrl {l+1}, 9 kết quả liên tiếp cùng phía)"
                        add_rej(i, msg, levels=[l])
                        break

        if n_levels == 3:
            for i in range(2, n_runs):
                window_idx = [i - 2, i - 1, i]
                vals = [Z[j, l] for j in window_idx for l in range(n_levels)]
                if any(np.isnan(v) for v in vals):
                    continue
                for s in (+1, -1):
                    if all(np.sign(v) == s for v in vals):
                        msg = "9x (3 lần chạy x 3 mức QC, tất cả cùng phía)"
                        add_rej(i, msg, levels=[0, 1, 2])
                        break

    # 10x
    if "10x" in active_rules and n_levels == 2:
        for l in range(n_levels):
            for i in range(9, n_runs):
                window_idx = list(range(i - 9, i + 1))
                vals = [Z[j, l] for j in window_idx]
                if any(np.isnan(v) for v in vals):
                    continue
                for s in (+1, -1):
                    if all(np.sign(v) == s for v in vals):
                        msg = f"10x (Ctrl {l+1}, 10 kết quả liên tiếp cùng phía)"
                        add_rej(i, msg, levels=[l])
                        break

        for i in range(4, n_runs):
            window_idx = list(range(i - 4, i + 1))
            vals = [Z[j, l] for j in window_idx for l in range(n_levels)]
            if any(np.isnan(v) for v in vals):
                continue
            for s in (+1, -1):
                if all(np.sign(v) == s for v in vals):
                    msg = "10x (5 lần chạy x 2 mức QC, tất cả cùng phía)"
                    add_rej(i, msg, levels=[0, 1])
                    break

    # Tổng hợp theo run
    rows = []
    for i, run in enumerate(runs):
        warns = sorted(warn_by_run[i])
        rejs = sorted(rej_by_run[i])
        if rejs:
            status = "Không đạt (Reject QC)"
        elif warns:
            status = "Cảnh báo (1_2s)"
        else:
            status = "Đạt"
        all_msgs = rejs + warns
        rows.append(
            {
                "Ngày/Lần": run,
                "Trạng thái": status,
                "Vi phạm loại bỏ": "; ".join(all_msgs),
                "Người thực hiện": "",
            }
        )
    summary_df = pd.DataFrame(rows)

    # Tổng hợp theo điểm
    point_rows = []
    for i, run in enumerate(runs):
        for l in range(n_levels):
            warns = sorted(warn_point[i][l])
            rejs = sorted(rej_point[i][l])
            if rejs:
                p_status = "Không đạt (Reject QC)"
            elif warns:
                p_status = "Cảnh báo (1_2s)"
            else:
                p_status = "Đạt"
            all_msgs = rejs + warns
            point_rows.append(
                {
                    "Ngày/Lần": run,
                    "Control": f"Ctrl {l+1}",
                    "point_status": p_status,
                    "rule_codes": "; ".join(all_msgs),
                }
            )
    point_df = pd.DataFrame(point_rows)

    return sigma_cat, active_rules, summary_df, point_df
