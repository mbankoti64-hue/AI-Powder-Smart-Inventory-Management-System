import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date as _date
import calendar
import io
import zipfile
from decimal import Decimal
from zoneinfo import ZoneInfo
from pathlib import Path
import re
import os
import json
import shutil

try:
    import psycopg2
    import psycopg2.pool
except ImportError:
    psycopg2 = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


# PAGE CONFIGURATION==============================

st.set_page_config(
    page_title="SmartStock AI",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Stable local database location; override with SMARTSTOCK_DB_PATH when needed.
DB_FILE = Path(os.getenv("SMARTSTOCK_DB_PATH", str(Path(__file__).resolve().parent / "smartstock.db"))).expanduser()
DB_FILE.parent.mkdir(parents=True, exist_ok=True)

# One-time migration: preserve an older database created from the launch directory.
LEGACY_DB_FILE = Path("smartstock.db").resolve()
if LEGACY_DB_FILE != DB_FILE.resolve() and LEGACY_DB_FILE.exists() and not DB_FILE.exists():
    shutil.copy2(LEGACY_DB_FILE, DB_FILE)


# CLOUD DATABASE (optional) ==========================
# Add DATABASE_URL to Streamlit Secrets (or environment) to store ALL data in a
# permanent PostgreSQL database such as Supabase. Without it, the local
# SQLite file is used exactly as before.

def _read_database_url():
    url = None
    try:
        url = st.secrets.get("DATABASE_URL")
    except Exception:
        url = None
    return str(url or os.getenv("DATABASE_URL") or "").strip()


DATABASE_URL = _read_database_url()
USE_PG = bool(DATABASE_URL)

if USE_PG and psycopg2 is None:
    st.error("DATABASE_URL is set, but 'psycopg2-binary' is not installed. "
             "Add psycopg2-binary to requirements.txt and reboot the app.")
    st.stop()

DB_INTEGRITY_ERRORS = (sqlite3.IntegrityError,) + (
    (psycopg2.IntegrityError,) if psycopg2 else ()
)


# DATABASE HELPERS==========================


def _pg_translate(sql, has_params):
    """Convert the app's SQLite-style SQL into PostgreSQL."""
    s = sql.strip().rstrip(";")
    if "CREATE TABLE" in s.upper():
        s = s.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        s = s.replace("DEFAULT CURRENT_TIMESTAMP", "DEFAULT (CURRENT_TIMESTAMP::text)")
        s = re.sub(r"\bREAL\b", "DOUBLE PRECISION", s)
    if re.match(r"INSERT\s+OR\s+REPLACE\s+INTO\s+app_meta", s, re.I):
        s = re.sub(r"INSERT\s+OR\s+REPLACE\s+INTO", "INSERT INTO", s, count=1, flags=re.I)
        s += " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
    elif re.match(r"INSERT\s+OR\s+IGNORE\s+INTO", s, re.I):
        s = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", s, count=1, flags=re.I)
        s += " ON CONFLICT DO NOTHING"
    if has_params:
        s = s.replace("%", "%%")
    return s.replace("?", "%s")


def _clean_params(params):
    # numpy / pandas scalars -> plain Python values
    return tuple(p.item() if hasattr(p, "item") else p for p in (params or ()))


class PGCursor:
    def __init__(self, cur):
        self._cur = cur
        self.lastrowid = None

    def execute(self, sql, params=()):
        params = _clean_params(params)
        self._cur.execute(_pg_translate(sql, bool(params)), params or None)
        return self

    def executescript(self, script):
        self._cur.execute(_pg_translate(script, False))
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def description(self):
        return self._cur.description

    @property
    def rowcount(self):
        return self._cur.rowcount


class PGConn:
    """Small wrapper so the rest of the app can keep using sqlite-style calls."""

    def __init__(self, raw, pool):
        self._raw = raw
        self._pool = pool
        self._closed = False

    def cursor(self):
        return PGCursor(self._raw.cursor())

    def execute(self, sql, params=()):
        return self.cursor().execute(sql, params)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._raw.rollback()
            self._pool.putconn(self._raw)
        except Exception:
            try:
                self._pool.putconn(self._raw, close=True)
            except Exception:
                pass


@st.cache_resource(show_spinner=False)
def _pg_pool():
    return psycopg2.pool.ThreadedConnectionPool(
        1, 5, dsn=DATABASE_URL, connect_timeout=15
    )


def db():
    if USE_PG:
        try:
            pool = _pg_pool()
            raw = pool.getconn()
        except Exception as exc:
            reason = str(exc).replace(DATABASE_URL, "<DATABASE_URL>").strip()
            st.error(
                "☁️ Could not connect to the cloud database.\n\n"
                f"**Reason:** {reason}\n\n"
                "Check: (1) the Session pooler string is used (host contains 'pooler'), "
                "(2) password is correct, written without [ ] and without spaces, "
                "(3) the Supabase project is active (not paused)."
            )
            st.stop()
        try:
            test = raw.cursor()
            test.execute("SELECT 1")
            test.close()
            raw.rollback()
        except Exception:
            pool.putconn(raw, close=True)
            raw = pool.getconn()
        return PGConn(raw, pool)

    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def query_df(sql, params=()):
    conn = db()
    try:
        if USE_PG:
            cur = conn.cursor()
            cur.execute(sql, params)
            df = pd.DataFrame(
                cur.fetchall(),
                columns=[d[0] for d in cur.description]
            )
            for c in df.columns:
                if df[c].dtype == object and len(df) and isinstance(df[c].iloc[0], Decimal):
                    df[c] = df[c].astype(float)
            return df
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def export_zip():
    """All tables as CSV files inside one ZIP (for downloading a copy of the data)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for t in ("products", "sales", "purchases",
                  "suppliers", "customers", "price_history"):
            z.writestr(f"{t}.csv", query_df(f"SELECT * FROM {t}").to_csv(index=False))
    return buf.getvalue()


def execute(sql, params=()):
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def money(value):
    return f"₹{float(value or 0):,.2f}"


# =========================================================
# DATE / PERIOD / MESSAGE HELPERS (India time)
# =========================================================

def today_ist():
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


def months_back(d, n):
    """The same day n months earlier (clipped to month end)."""
    total = d.year * 12 + (d.month - 1) - n
    y, m = divmod(total, 12)
    m += 1
    return _date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def to_date_series(series):
    """Works for 'YYYY-MM-DD' and full timestamps; keeps only the date part."""
    return pd.to_datetime(series.astype(str).str[:10], errors="coerce")


def flash(message, kind="success"):
    """Show a message after st.rerun() (st.success would vanish on rerun)."""
    st.session_state["_flash"] = (kind, message)


def show_flash():
    item = st.session_state.pop("_flash", None)
    if item:
        getattr(st, item[0])(item[1])


PERIOD_OPTIONS = [
    "Today", "Last 7 days", "Last 1 month", "Last 2 months",
    "Last 3 months", "This month", "All time", "Custom range"
]


def period_selector(key, min_date, max_date=None, default="Last 1 month"):
    """Quick period picker. Returns (start_date, end_date) or None."""
    today = today_ist()
    choice = st.selectbox(
        "📅 Period",
        PERIOD_OPTIONS,
        index=PERIOD_OPTIONS.index(default),
        key=f"{key}_period"
    )
    if choice == "Today":
        return today, today
    if choice == "Last 7 days":
        return today - timedelta(days=6), today
    if choice == "Last 1 month":
        return months_back(today, 1) + timedelta(days=1), today
    if choice == "Last 2 months":
        return months_back(today, 2) + timedelta(days=1), today
    if choice == "Last 3 months":
        return months_back(today, 3) + timedelta(days=1), today
    if choice == "This month":
        return today.replace(day=1), today
    if choice == "All time":
        return min(min_date, today), max(max_date or today, today)
    value = st.date_input(
        "Select start and end date",
        value=(min(max(min_date, today - timedelta(days=29)), today), today),
        key=f"{key}_custom"
    )
    if isinstance(value, tuple) and len(value) == 2:
        return value
    return None


# DATABASE INITIALIZATION
# =========================================================

def initialize_database():
    conn = db()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE,
            name TEXT NOT NULL,
            brand TEXT,
            category TEXT,
            purchase_price REAL DEFAULT 0,
            selling_price REAL DEFAULT 0,
            stock INTEGER DEFAULT 0,
            reorder_level INTEGER DEFAULT 5,
            supplier TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT,
            product_id INTEGER,
            product_name TEXT,
            customer TEXT,
            quantity INTEGER,
            unit_price REAL,
            unit_cost REAL,
            total REAL,
            profit REAL,
            sale_date TEXT
        );

        CREATE TABLE IF NOT EXISTS purchases(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_no TEXT,
            product_id INTEGER,
            product_name TEXT,
            supplier TEXT,
            quantity INTEGER,
            unit_cost REAL,
            total REAL,
            purchase_date TEXT,
            status TEXT
        );

        CREATE TABLE IF NOT EXISTS suppliers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            phone TEXT,
            email TEXT,
            address TEXT
        );

        CREATE TABLE IF NOT EXISTS customers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            phone TEXT,
            favorite_product TEXT
        );

        CREATE TABLE IF NOT EXISTS price_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            old_price REAL,
            new_price REAL,
            changed_at TEXT
        );
    """)

    # One-time cleanup of the old built-in demo data.
    # Runs only once per database (flag stored in app_meta); after that every
    # entry you add from the UI is kept permanently.
    cur.execute(
        "CREATE TABLE IF NOT EXISTS app_meta(key TEXT PRIMARY KEY, value TEXT)"
    )
    flag = cur.execute(
        "SELECT value FROM app_meta WHERE key='demo_data_cleared'"
    ).fetchone()

    if flag is None:
        tables = ("products", "sales", "purchases",
                  "suppliers", "customers", "price_history")
        has_rows = any(
            cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in tables
        )
        if has_rows:
            conn.commit()
            try:
                shutil.copy2(
                    DB_FILE,
                    DB_FILE.with_name("smartstock_backup_before_clear.db")
                )
            except Exception:
                pass
            for t in tables:
                cur.execute(f"DELETE FROM {t}")
            if not USE_PG:
                try:
                    cur.execute("DELETE FROM sqlite_sequence")
                except sqlite3.OperationalError:
                    pass
        cur.execute(
            "INSERT OR REPLACE INTO app_meta(key, value) VALUES('demo_data_cleared', ?)",
            (datetime.now().isoformat(),)
        )

    conn.commit()
    conn.close()


@st.cache_resource(show_spinner=False)
def _initialize_once():
    initialize_database()
    return True


if USE_PG:
    _initialize_once()   # cloud DB: create tables once per app start
else:
    initialize_database()




# CSS DESIGN — SMARTSTOCK AI DARK NAVY DASHBOARD
# =========================================================

st.markdown("""
<style>
:root {
    --page: #080F1D;
    --sidebar: #091426;
    --panel: #101D32;
    --panel-2: #13233B;
    --border: #263956;
    --text: #F2F6FF;
    --muted: #A8B6D0;
    --purple: #6D35F5;
    --blue: #3478F6;
    --green: #19D6A0;
    --orange: #FFB84D;
    --red: #FF5C83;
}
.stApp {
    background:
        radial-gradient(ellipse at 60% 0%, rgba(42, 75, 145, .16), transparent 45%),
        var(--page) !important;
    color: var(--text) !important;
}
[data-testid="stHeader"] {
    background: rgba(8, 15, 29, .96) !important;
}
[data-testid="stToolbar"] { right: 1rem; }
[data-testid="stDecoration"] { display: none; }
.block-container {
    max-width: 1900px;
    padding-top: 2.8rem !important;
    padding-bottom: 2rem;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0A1528 0%, #081222 100%) !important;
    border-right: 1px solid #1D2D49 !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 1.1rem; }
[data-testid="stSidebar"] * { color: var(--text); }
h1, h2, h3, h4, h5, h6 {
    color: var(--text) !important;
    letter-spacing: -.025em;
}
p, label, [data-testid="stCaptionContainer"] {
    color: var(--muted);
}
[data-testid="stMetric"] {
    background: linear-gradient(145deg, #142541, #101B30) !important;
    border: 1px solid #2B4267 !important;
    border-radius: 13px !important;
    padding: 15px 16px !important;
    box-shadow: 0 8px 24px rgba(0,0,0,.12);
    min-height: 112px;
}
[data-testid="stMetricLabel"] {
    color: #B7C5DF !important;
    font-size: .82rem !important;
}
[data-testid="stMetricValue"] {
    color: #F7FAFF !important;
    font-weight: 750 !important;
    font-size: clamp(1.15rem, 1.8vw, 1.8rem) !important;
}
[data-testid="stMetricDelta"] { font-size: .75rem !important; }
[data-testid="stForm"],
[data-testid="stExpander"],
[data-testid="stVerticalBlockBorderWrapper"] {
    background: linear-gradient(145deg, #101D32, #0D192B) !important;
    border: 1px solid var(--border) !important;
    border-radius: 13px !important;
}
div.stButton > button,
[data-testid="stFormSubmitButton"] button,
[data-testid="stDownloadButton"] button {
    background: linear-gradient(135deg, #7138FF, #4E2BE0) !important;
    color: #FFFFFF !important;
    border: 1px solid #8057FF !important;
    border-radius: 9px !important;
    font-weight: 650 !important;
    transition: all .18s ease-in-out;
}
div.stButton > button:hover,
[data-testid="stFormSubmitButton"] button:hover,
[data-testid="stDownloadButton"] button:hover {
    background: linear-gradient(135deg, #8050FF, #5D3AE8) !important;
    border-color: #A18BFF !important;
    transform: translateY(-1px);
}
.stTextInput input, .stNumberInput input, .stDateInput input,
.stTextArea textarea, [data-baseweb="select"] > div {
    background: #15243B !important;
    color: var(--text) !important;
    border: 1px solid #2A3D5D !important;
    border-radius: 9px !important;
}
input::placeholder, textarea::placeholder { color: #91A2C0 !important; }
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    border-bottom: 1px solid var(--border);
}
.stTabs [data-baseweb="tab"] {
    background: #111E33;
    color: #B7C5DF !important;
    border-radius: 8px 8px 0 0;
    padding: 8px 15px;
}
.stTabs [aria-selected="true"] {
    color: #FFFFFF !important;
    border-bottom: 2px solid #7445FF !important;
}
[data-testid="stDataFrame"], [data-testid="stTable"] {
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    overflow: hidden;
}
a { color: #8B9CFF !important; }
hr { border-color: #233652 !important; }
[data-testid="stAlert"] {
    background: #12213A;
    border: 1px solid #2A4163;
    border-radius: 10px;
}
.js-plotly-plot {
    border: 1px solid #233652;
    border-radius: 12px;
    overflow: hidden;
    background: #0D192B;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    background: transparent;
    border-radius: 9px;
    padding: 5px 8px;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: #172744;
}
[data-testid="stSidebar"] [data-testid="stRadio"] [aria-checked="true"] {
    background: linear-gradient(90deg, #5F2FEA, #4023A9);
    border-radius: 9px;
}
[data-testid="stSidebar"] [data-testid="stRadio"] [aria-checked="true"] * {
    color: white !important;
}
@media (max-width: 900px) {
    .block-container { padding-left: 1rem; padding-right: 1rem; }
    [data-testid="stMetric"] { padding: 10px !important; }
}
</style>
""", unsafe_allow_html=True)


# SIDEBAR NAVIGATION
# =========================================================

with st.sidebar:

    st.markdown("# 📦 SmartStock AI")
    st.caption("Inventory Smarter • Grow Faster")
    st.divider()

    nav_options = [
        " Dashboard",
        " Inventory",
        "💰 Sales",
        "🛒 Purchases",
        "👥 Suppliers",
        "📊 Reports",
        "🤖 AI Assistant",
        "🔔 Alerts",
        "⚙️ Settings"
    ]
    default_page = st.session_state.pop("active_page", " Dashboard")
    default_index = nav_options.index(default_page) if default_page in nav_options else 0
    page = st.radio(
        "Navigation",
        nav_options,
        index=default_index,
        label_visibility="collapsed"
    )

    st.divider()
    st.markdown("### ⚡ Quick Actions")
    st.caption("Manage your business from one place.")
    st.divider()
    st.caption("SmartStock AI")
    st.caption("Phase 1 Prototype")


# =========================================================
# DASHBOARD


@st.fragment(run_every="60s")
def render_live_dashboard_header():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    if now.hour < 12:
        greeting = "Good Morning"
    elif now.hour < 17:
        greeting = "Good Afternoon"
    else:
        greeting = "Good Evening"

    head_left, head_right = st.columns([3.4, 1])
    with head_left:
        st.markdown(
            f"<div style='font-size:1.85rem;font-weight:800;color:#F2F6FF;"
            f"line-height:1.35;padding-top:8px;overflow-wrap:anywhere;'>{greeting}! 👋</div>"
            "<div style='color:#A8B6D0;margin-top:5px;'>"
            "Here's what's happening with your business today.</div>",
            unsafe_allow_html=True
        )
    with head_right:
        st.markdown(
            f"<div style='text-align:right;color:#D7E2F6;padding-top:4px;"
            f"font-weight:650;'>📅 {now.strftime('%d %b %Y')}<br>"
            f"<span style='font-size:.82rem;color:#A8B6D0;font-weight:400;'>"
            f"{now.strftime('%A, %I:%M:%S %p')}</span></div>",
            unsafe_allow_html=True
        )


def dashboard():
    products = query_df("SELECT * FROM products")
    sales = query_df("SELECT * FROM sales")
    purchases = query_df("SELECT * FROM purchases ORDER BY id DESC")
    suppliers = query_df("SELECT * FROM suppliers")

    # Live header: greeting/date/time update every 60 seconds without reloading the full app.
    render_live_dashboard_header()
    st.markdown("")
    if sales.empty:
        st.info("No sales data available yet. Add a sale to populate your dashboard.")
        total_revenue = total_profit = 0
        filtered = sales.copy()
    else:
        sales["sale_date"] = to_date_series(sales["sale_date"])
        valid_dates = sales["sale_date"].dropna()
        picked = period_selector(
            "dashboard",
            valid_dates.min().date() if not valid_dates.empty else today_ist(),
            valid_dates.max().date() if not valid_dates.empty else today_ist()
        )
        if picked is None:
            st.info("Select a start date and an end date.")
            return
        start_date, end_date = picked
        filtered = sales[
            sales["sale_date"].dt.date.between(start_date, end_date)
        ].copy()
        total_revenue = float(filtered["total"].sum()) if not filtered.empty else 0
        total_profit = float(filtered["profit"].sum()) if not filtered.empty else 0

    total_stock = int(products["stock"].sum()) if not products.empty else 0
    low_stock = int((products["stock"] <= products["reorder_level"]).sum()) if not products.empty else 0
    out_stock = int((products["stock"] <= 0).sum()) if not products.empty else 0

    # Main metrics row
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("📦 Total Stock", f"{total_stock:,}")
    m2.metric("💰 Sales", money(total_revenue))
    m3.metric("📈 Profit", money(total_profit))
    m4.metric("⚠️ Low Stock", low_stock)
    m5.metric("🚨 Out of Stock", out_stock)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # Main analytics area + compact AI panel on the right, inspired by the reference image.
    main_area, assistant_area = st.columns([3.2, 1.0], gap="medium")
    with main_area:
        chart_left, chart_right = st.columns([1.55, 1])
        with chart_left:
            st.markdown("<h3 style='font-size:1.22rem;margin-bottom:8px;'>📈 Sales &amp; Profit Trend</h3>", unsafe_allow_html=True)
            if not filtered.empty:
                trend_source = filtered.copy()
                trend_source["Date"] = trend_source["sale_date"].dt.date
                trend = (
                    trend_source.groupby("Date", as_index=False)
                    .agg(Sales=("total", "sum"), Profit=("profit", "sum"))
                    .sort_values("Date")
                )
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=trend["Date"], y=trend["Sales"], mode="lines+markers",
                    name="Sales", line=dict(color="#54B8FF", width=3),
                    marker=dict(size=5), fill="tozeroy",
                    fillcolor="rgba(84,184,255,0.08)"
                ))
                fig.add_trace(go.Scatter(
                    x=trend["Date"], y=trend["Profit"], mode="lines+markers",
                    name="Profit", line=dict(color="#FF9C78", width=2.5),
                    marker=dict(size=4)
                ))
                fig.update_layout(
                    template="plotly_dark", height=360,
                    paper_bgcolor="#07111F", plot_bgcolor="#07111F",
                    margin=dict(l=28, r=16, t=34, b=34),
                    legend=dict(
                        orientation="h", y=1.12, x=0.52, xanchor="left",
                        font=dict(size=12, color="#E3ECFF")
                    ),
                    hovermode="x unified",
                    font=dict(family="Arial, sans-serif", size=12, color="#D8E4F8"),
                    xaxis=dict(
                        title=None, showgrid=True, gridcolor="rgba(77,100,137,0.18)",
                        color="#D3DDF0", tickformat="%d %b",
                        tickfont=dict(size=11), automargin=True,
                        linecolor="#263956", zerolinecolor="#263956"
                    ),
                    yaxis=dict(
                        title=None, gridcolor="rgba(111,132,164,0.28)", color="#D3DDF0",
                        tickfont=dict(size=11), separatethousands=True,
                        automargin=True, zerolinecolor="#425575",
                        tickformat="~s"
                    )
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Your sales trend will appear here after the first sale.")

        with chart_right:
            st.markdown("<h3 style='font-size:1.22rem;margin-bottom:8px;'>🍩 Sales by Category</h3>", unsafe_allow_html=True)
            if not filtered.empty and not products.empty:
                category_sales = (
                    filtered.merge(
                        products[["id", "category"]],
                        left_on="product_id", right_on="id", how="left"
                    )
                    .groupby("category", as_index=False)["total"].sum()
                )
                category_sales["category"] = category_sales["category"].fillna("Other")
                if not category_sales.empty:
                    fig = px.pie(
                        category_sales, names="category", values="total",
                        hole=0.58,
                        color_discrete_sequence=[
                            "#39A9FF", "#FF9F76", "#1DD6A1",
                            "#A68BFF", "#F5C451", "#F06FA9"
                        ]
                    )
                    fig.update_traces(
                        textposition="inside",
                        textinfo="percent",
                        textfont=dict(size=12, color="#FFFFFF"),
                        marker=dict(line=dict(color="#0D192B", width=2)),
                        hovertemplate="<b>%{label}</b><br>Sales: ₹%{value:,.0f}<br>Share: %{percent}<extra></extra>"
                    )
                    fig.update_layout(
                        template="plotly_dark", height=360,
                        paper_bgcolor="#07111F", plot_bgcolor="#07111F",
                        margin=dict(l=4, r=4, t=16, b=8),
                        font=dict(family="Arial, sans-serif", size=11, color="#DCE6F8"),
                        legend=dict(
                            font=dict(size=11, color="#DCE6F8"),
                            orientation="v", x=1.0, y=0.5
                        )
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Category sales will appear here.")

        low_col, stock_col = st.columns([1.25, 1])
        with low_col:
            st.markdown("### ⚠️ Low Stock Items")
            if not products.empty:
                low = products[products["stock"] <= products["reorder_level"]].copy()
                if low.empty:
                    st.success("All products have sufficient stock.")
                else:
                    low_view = low[["name", "category", "stock", "reorder_level"]].copy()
                    low_view.columns = ["Product", "Category", "Stock", "Reorder At"]
                    st.dataframe(low_view, use_container_width=True, hide_index=True, height=220)
            else:
                st.info("Add products to monitor stock.")

        with stock_col:
            st.markdown("### 📊 Stock by Category")
            if not products.empty:
                stock_category = (
                    products.groupby("category", as_index=False)["stock"].sum()
                    .sort_values("stock", ascending=True)
                )
                fig = px.bar(
                    stock_category, x="stock", y="category",
                    orientation="h", text="stock",
                    color="stock",
                    color_continuous_scale=["#263A70", "#3478F6", "#6D35F5"]
                )
                fig.update_layout(
                    template="plotly_dark", height=260,
                    paper_bgcolor="#0D192B", plot_bgcolor="#0D192B",
                    margin=dict(l=5, r=8, t=12, b=8),
                    showlegend=False, coloraxis_showscale=False,
                    xaxis=dict(gridcolor="#2A3B58", color="#C0CEE5",
                               tickfont=dict(size=11), title=None),
                    yaxis=dict(color="#C0CEE5", tickfont=dict(size=11),
                               title=None, automargin=True)
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Stock summary will appear here.")

        # Lower section
        bottom_left, bottom_right = st.columns(2)
        with bottom_left:
            st.markdown("### 🧾 Recent Sales")
            if not filtered.empty:
                recent = filtered.sort_values(["sale_date", "id"], ascending=False).head(6)
                cols = ["invoice_no", "product_name", "customer", "total", "sale_date"]
                recent = recent[[c for c in cols if c in recent.columns]].copy()
                if "total" in recent.columns:
                    recent["total"] = recent["total"].apply(money)
                if "sale_date" in recent.columns:
                    recent["sale_date"] = pd.to_datetime(recent["sale_date"]).dt.strftime("%d %b %Y")
                recent.columns = ["Invoice" if c == "invoice_no" else
                                  "Product" if c == "product_name" else
                                  "Customer" if c == "customer" else
                                  "Amount" if c == "total" else
                                  "Date" if c == "sale_date" else c for c in recent.columns]
                st.dataframe(recent, use_container_width=True, hide_index=True, height=230)
            else:
                st.info("No sales in the selected date range.")

        with bottom_right:
            st.markdown("### 🛒 Recent Purchases")
            if not purchases.empty:
                recent_purchases = purchases.head(6)[
                    ["purchase_no", "supplier", "total", "purchase_date", "status"]
                ].copy()
                recent_purchases["total"] = recent_purchases["total"].apply(money)
                recent_purchases["purchase_date"] = pd.to_datetime(
                    recent_purchases["purchase_date"], errors="coerce"
                ).dt.strftime("%d %b %Y")
                recent_purchases.columns = ["Purchase ID", "Supplier", "Amount", "Date", "Status"]
                st.dataframe(recent_purchases, use_container_width=True, hide_index=True, height=230)
            else:
                st.info("No purchases recorded yet.")

        # Quick overview tiles
        st.markdown("### 📌 Business Overview")
        q1, q2, q3, q4, q5 = st.columns(5)
        q1.metric("Total Products", f"{len(products):,}")
        q2.metric("Categories", f"{products['category'].nunique() if not products.empty else 0:,}")
        q3.metric("Suppliers", f"{len(suppliers):,}")
        q4.metric("Units Sold", f"{int(filtered['quantity'].sum()) if not filtered.empty else 0:,}")
        q5.metric("Period Profit", money(total_profit))

    with assistant_area:
        st.markdown(
            "<div style='border:1px solid #2B4267;border-radius:16px;"
            "padding:16px;background:linear-gradient(180deg,#13223B,#0D182B);'>"
            "<div style='font-size:1.1rem;font-weight:750;color:#F2F6FF;'>🤖 AI Assistant</div>"
            "<div style='font-size:.78rem;color:#19D6A0;margin:4px 0 12px;'>● Online</div>"
            "<div style='text-align:center;font-size:4.2rem;line-height:1.2;'>🤖</div>"
            "<div style='font-size:1.1rem;font-weight:750;text-align:center;color:#F2F6FF;'>"
            "Hello! 👋<br>How can I help today?</div>"
            "<div style='text-align:center;color:#A8B6D0;font-size:.82rem;margin-top:8px;'>"
            "Ask about sales, stock, or profit.</div></div>",
            unsafe_allow_html=True
        )
        st.markdown("#### Try a command")
        for suggestion in [
            "Show today's sales",
            "Show 1 month sales and profit",
            "Show 2 months sales and profit",
            "Which product is low in stock?"
        ]:
            if st.button(suggestion, key="dash_ai_" + suggestion, use_container_width=True):
                st.session_state["dashboard_ai_result"] = process_ai(suggestion)
                st.rerun()
        if st.session_state.get("dashboard_ai_result"):
            st.info(st.session_state["dashboard_ai_result"])
        st.markdown("---")
        st.caption("Quick actions")
        if st.button("➕ Add Product", use_container_width=True):
            st.session_state["active_page"] = " Inventory"
            st.rerun()
        if st.button("💰 New Sale", use_container_width=True):
            st.session_state["active_page"] = "💰 Sales"
            st.rerun()
        if st.button("🛒 New Purchase", use_container_width=True):
            st.session_state["active_page"] = "🛒 Purchases"
            st.rerun()


# =========================================================
# INVENTORY MANAGEMENT
# =========================================================

def inventory_page():

    st.markdown("# 📦 Inventory Management")

    tab1, tab2, tab3 = st.tabs([
        "📋 Products",
        "➕ Add Product",
        "✏️ Edit Product"
    ])

    current = query_df("SELECT * FROM products ORDER BY id DESC")

    with tab1:

        if current.empty:
            st.info("Inventory is empty. Use the 'Add Product' tab to add your first product.")

        search = st.text_input("🔎 Search Product")

        display = current.copy()

        if search:

            mask = (
                display["name"].str.contains(search, case=False, na=False) |
                display["brand"].str.contains(search, case=False, na=False) |
                display["category"].str.contains(search, case=False, na=False)
            )

            display = display[mask]

        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True
        )

        if not display.empty:

            delete_name = st.selectbox(
                "Select product to delete",
                display["name"].tolist()
            )

            if st.button("🗑️ Delete Product"):

                execute(
                    "DELETE FROM products WHERE name=?",
                    (delete_name,)
                )

                flash("Product deleted.")
                st.rerun()

    with tab2:

        with st.form("add_product_form"):

            c1, c2, c3 = st.columns(3)

            sku = c1.text_input("SKU")
            name = c2.text_input("Product Name")
            brand = c3.text_input("Brand")

            c1, c2, c3 = st.columns(3)

            category = c1.text_input("Category")

            purchase_price = c2.number_input(
                "Purchase Price",
                min_value=0.0,
                step=100.0
            )

            selling_price = c3.number_input(
                "Selling Price",
                min_value=0.0,
                step=100.0
            )

            c1, c2, c3 = st.columns(3)

            stock = c1.number_input(
                "Opening Stock",
                min_value=0,
                step=1
            )

            reorder_level = c2.number_input(
                "Reorder Level",
                min_value=0,
                value=5
            )

            supplier = c3.text_input("Supplier")

            submit = st.form_submit_button("➕ Add Product")

        if submit:

            if not name.strip():

                st.error("Product name is required.")

            else:

                if not sku.strip():
                    sku = "SKU-" + datetime.now().strftime("%Y%m%d%H%M%S")

                try:

                    execute("""
                        INSERT INTO products(
                            sku, name, brand, category,
                            purchase_price, selling_price,
                            stock, reorder_level, supplier
                        )
                        VALUES(?,?,?,?,?,?,?,?,?)
                    """, (
                        sku,
                        name,
                        brand,
                        category,
                        purchase_price,
                        selling_price,
                        stock,
                        reorder_level,
                        supplier
                    ))

                    if supplier.strip():
                        execute(
                            "INSERT OR IGNORE INTO suppliers(name) VALUES(?)",
                            (supplier.strip(),)
                        )

                    flash("Product added successfully.")
                    st.rerun()

                except DB_INTEGRITY_ERRORS:
                    st.error("This SKU already exists.")

    with tab3:

        if current.empty:

            st.info("No products available.")

        else:

            selected_name = st.selectbox(
                "Select product",
                current["name"].tolist(),
                key="edit_product_select"
            )

            row = current[
                current["name"] == selected_name
            ].iloc[0]

            with st.form("edit_product_form"):

                new_name = st.text_input(
                    "Product Name",
                    value=row["name"]
                )

                new_brand = st.text_input(
                    "Brand",
                    value=str(row["brand"] or "")
                )

                new_category = st.text_input(
                    "Category",
                    value=str(row["category"] or "")
                )

                new_purchase_price = st.number_input(
                    "Purchase Price",
                    min_value=0.0,
                    value=float(row["purchase_price"]),
                    step=100.0
                )

                new_selling_price = st.number_input(
                    "Selling Price",
                    min_value=0.0,
                    value=float(row["selling_price"]),
                    step=100.0
                )

                new_stock = st.number_input(
                    "Stock",
                    min_value=0,
                    value=int(row["stock"])
                )

                new_reorder = st.number_input(
                    "Reorder Level",
                    min_value=0,
                    value=int(row["reorder_level"])
                )

                new_supplier = st.text_input(
                    "Supplier",
                    value=str(row["supplier"] or "")
                )

                save = st.form_submit_button("💾 Save Changes")

            if save:

                if new_selling_price != float(row["selling_price"]):

                    execute("""
                        INSERT INTO price_history(
                            product_id, old_price,
                            new_price, changed_at
                        )
                        VALUES(?,?,?,?)
                    """, (
                        row["id"],
                        float(row["selling_price"]),
                        new_selling_price,
                        datetime.now().isoformat()
                    ))

                execute("""
                    UPDATE products
                    SET name=?, brand=?, category=?,
                        purchase_price=?, selling_price=?,
                        stock=?, reorder_level=?, supplier=?,
                        updated_at=?
                    WHERE id=?
                """, (
                    new_name,
                    new_brand,
                    new_category,
                    new_purchase_price,
                    new_selling_price,
                    new_stock,
                    new_reorder,
                    new_supplier,
                    datetime.now().isoformat(),
                    row["id"]
                ))

                flash("Product updated.")
                st.rerun()


# =========================================================
# SALES MANAGEMENT
# =========================================================

def sales_page():

    st.markdown("# 💰 Sales Management")

    products = query_df(
        "SELECT * FROM products ORDER BY name"
    )

    tab1, tab2 = st.tabs([
        "➕ New Sale",
        "📜 Sales History"
    ])

    with tab1:

        if products.empty:

            st.warning("Add products before making a sale.")

        else:

            with st.form("new_sale_form"):

                product_name = st.selectbox(
                    "Product",
                    products["name"].tolist()
                )

                customer = st.text_input("Customer Name")

                product = products[
                    products["name"] == product_name
                ].iloc[0]

                st.info(
                    f"Price: {money(product['selling_price'])} | "
                    f"Available stock: {product['stock']}"
                )

                quantity = st.number_input(
                    "Quantity",
                    min_value=1,
                    max_value=max(1, int(product["stock"])),
                    value=1
                )

                sale_date = st.date_input(
                    "Sale Date",
                    value=today_ist(),
                    max_value=today_ist()
                )

                submit = st.form_submit_button("✅ Complete Sale")

            if submit:

                if int(product["stock"]) < quantity:

                    st.error("Insufficient stock.")

                else:

                    total = quantity * float(product["selling_price"])

                    profit = quantity * (
                        float(product["selling_price"]) -
                        float(product["purchase_price"])
                    )

                    invoice = (
                        "SALE-" +
                        datetime.now().strftime("%Y%m%d%H%M%S%f")
                    )

                    conn = db()

                    try:

                        cur = conn.cursor()

                        cur.execute("""
                            INSERT INTO sales(
                                invoice_no, product_id, product_name,
                                customer, quantity, unit_price,
                                unit_cost, total, profit, sale_date
                            )
                            VALUES(?,?,?,?,?,?,?,?,?,?)
                        """, (
                            invoice,
                            product["id"],
                            product["name"],
                            customer,
                            quantity,
                            product["selling_price"],
                            product["purchase_price"],
                            total,
                            profit,
                            sale_date.isoformat()
                        ))

                        cur.execute("""
                            UPDATE products
                            SET stock=stock-?, updated_at=?
                            WHERE id=?
                        """, (
                            quantity,
                            datetime.now().isoformat(),
                            product["id"]
                        ))

                        if customer.strip():

                            cur.execute("""
                                INSERT INTO customers(
                                    name, favorite_product
                                )
                                VALUES(?,?)
                                ON CONFLICT(name)
                                DO UPDATE SET
                                    favorite_product=excluded.favorite_product
                            """, (
                                customer.strip(),
                                product["name"]
                            ))

                        conn.commit()

                        flash(f"Sale completed: {invoice}")
                        st.rerun()

                    except Exception as e:

                        conn.rollback()
                        st.error(f"Sale failed: {e}")

                    finally:
                        conn.close()

    with tab2:

        history = query_df("""
            SELECT invoice_no, product_name, customer,
                   quantity, unit_price, total, profit, sale_date
            FROM sales
            ORDER BY id DESC
        """)

        st.dataframe(
            history,
            use_container_width=True,
            hide_index=True
        )

        if not history.empty:

            st.download_button(
                "📥 Download Sales CSV",
                history.to_csv(index=False),
                file_name="smartstock_sales.csv",
                mime="text/csv"
            )


# =========================================================
# PURCHASE MANAGEMENT
# =========================================================

def purchases_page():

    st.markdown("# 🛒 Purchase Management")

    products = query_df(
        "SELECT * FROM products ORDER BY name"
    )

    suppliers = query_df(
        "SELECT * FROM suppliers ORDER BY name"
    )

    tab1, tab2 = st.tabs([
        "➕ New Purchase",
        "📜 Purchase History"
    ])

    with tab1:

        if products.empty:

            st.warning("Add a product first.")

        elif suppliers.empty:

            st.warning("Add a supplier first.")

        else:

            with st.form("purchase_form"):

                product_name = st.selectbox(
                    "Product",
                    products["name"].tolist()
                )

                product = products[
                    products["name"] == product_name
                ].iloc[0]

                supplier = st.selectbox(
                    "Supplier",
                    suppliers["name"].tolist()
                )

                quantity = st.number_input(
                    "Quantity",
                    min_value=1,
                    value=1
                )

                unit_cost = st.number_input(
                    "Unit Cost",
                    min_value=0.0,
                    value=float(product["purchase_price"]),
                    step=100.0
                )

                purchase_date = st.date_input(
                    "Purchase Date",
                    value=today_ist(),
                    max_value=today_ist()
                )

                submit = st.form_submit_button("📥 Complete Purchase")

            if submit:

                purchase_no = (
                    "PUR-" +
                    datetime.now().strftime("%Y%m%d%H%M%S%f")
                )

                total = quantity * unit_cost

                conn = db()

                try:

                    cur = conn.cursor()

                    cur.execute("""
                        INSERT INTO purchases(
                            purchase_no, product_id, product_name,
                            supplier, quantity, unit_cost,
                            total, purchase_date, status
                        )
                        VALUES(?,?,?,?,?,?,?,?,?)
                    """, (
                        purchase_no,
                        product["id"],
                        product["name"],
                        supplier,
                        quantity,
                        unit_cost,
                        total,
                        purchase_date.isoformat(),
                        "Completed"
                    ))

                    cur.execute("""
                        UPDATE products
                        SET stock=stock+?,
                            purchase_price=?,
                            supplier=?,
                            updated_at=?
                        WHERE id=?
                    """, (
                        quantity,
                        unit_cost,
                        supplier,
                        datetime.now().isoformat(),
                        product["id"]
                    ))

                    conn.commit()

                    flash("Purchase completed.")
                    st.rerun()

                except Exception as e:

                    conn.rollback()
                    st.error(f"Purchase failed: {e}")

                finally:
                    conn.close()

    with tab2:

        data = query_df("""
            SELECT *
            FROM purchases
            ORDER BY id DESC
        """)

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# SUPPLIERS
# =========================================================

def suppliers_page():

    st.markdown("# 👥 Supplier Management")

    data = query_df(
        "SELECT * FROM suppliers ORDER BY name"
    )

    st.dataframe(
        data,
        use_container_width=True,
        hide_index=True
    )

    with st.expander("➕ Add Supplier"):

        with st.form("supplier_form"):

            name = st.text_input("Supplier Name")
            phone = st.text_input("Phone")
            email = st.text_input("Email")
            address = st.text_input("Address")

            submit = st.form_submit_button("Add Supplier")

        if submit:

            if not name.strip():

                st.error("Supplier name is required.")

            else:

                try:

                    execute("""
                        INSERT INTO suppliers(
                            name, phone, email, address
                        )
                        VALUES(?,?,?,?)
                    """, (
                        name.strip(),
                        phone,
                        email,
                        address
                    ))

                    flash("Supplier added.")
                    st.rerun()

                except DB_INTEGRITY_ERRORS:
                    st.error("Supplier already exists.")


# =========================================================
# REPORTS AND ANALYTICS
# =========================================================

def reports_page():

    st.markdown("# 📊 Reports & Analytics")

    data = query_df("SELECT * FROM sales")

    if data.empty:

        st.info("No sales data available.")
        return

    data["sale_date"] = to_date_series(data["sale_date"])

    valid = data["sale_date"].dropna()

    if valid.empty:

        st.info("No valid sales dates found.")
        return

    picked = period_selector(
        "reports",
        valid.min().date(),
        valid.max().date(),
        default="Last 1 month"
    )

    if picked is None:

        st.info("Select both a start date and an end date.")
        return

    start, end = picked

    selected = data[
        (data["sale_date"].dt.date >= start) &
        (data["sale_date"].dt.date <= end)
    ]

    revenue = selected["total"].sum()
    profit = selected["profit"].sum()
    units = selected["quantity"].sum()

    c1, c2, c3 = st.columns(3)

    c1.metric("Revenue", money(revenue))
    c2.metric("Profit", money(profit))
    c3.metric("Units Sold", f"{units:,}")

    if not selected.empty:

        by_product = (
            selected.groupby("product_name", as_index=False)
            .agg(
                Units=("quantity", "sum"),
                Sales=("total", "sum"),
                Profit=("profit", "sum")
            )
            .sort_values("Sales", ascending=False)
        )

        st.markdown("### 🏷️ Product-wise Sales & Profit")
        st.dataframe(by_product, use_container_width=True, hide_index=True)

        trend = (
            selected.groupby("sale_date", as_index=False)
            .agg(
                Revenue=("total", "sum"),
                Profit=("profit", "sum")
            )
        )

        fig = px.line(
            trend,
            x="sale_date",
            y=["Revenue", "Profit"],
            markers=True
        )

        fig.update_layout(
            template="plotly_dark",
            height=420
        )

        st.plotly_chart(fig, use_container_width=True)

    st.download_button(
        "📥 Download Sales CSV",
        selected.to_csv(index=False),
        file_name="smartstock_sales.csv",
        mime="text/csv"
    )


# =========================================================
# AI ASSISTANT
# =========================================================

def _find_product(product_text, products):
    product_text = re.sub(r"\b(the|of|for|product|stock)\b", " ", product_text, flags=re.I)
    product_text = re.sub(r"\s+", " ", product_text).strip(" .?!,\"'")
    if not product_text or products.empty:
        return None
    names = products["name"].fillna("").astype(str)
    exact = products[names.str.casefold() == product_text.casefold()]
    if not exact.empty:
        return exact.iloc[0]
    matches = products[names.str.contains(re.escape(product_text), case=False, na=False)]
    if len(matches) == 1:
        return matches.iloc[0]
    reverse = products[names.str.casefold().apply(lambda n: bool(n) and n in product_text.casefold())]
    return reverse.iloc[0] if len(reverse) == 1 else None



def _get_gemini_client():
    """Return a Gemini client when a Gemini API key is configured."""
    if genai is None:
        return None
    api_key = None
    try:
        api_key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        api_key = None
    api_key = api_key or os.getenv("GEMINI_API_KEY")
    return genai.Client(api_key=api_key) if api_key else None


def _gemini_model_name():
    try:
        return st.secrets.get("GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    except Exception:
        return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _ai_database_snapshot():
    """Small, factual database snapshot for conversational answers."""
    products = query_df("""
        SELECT name, brand, category, purchase_price, selling_price,
               stock, reorder_level, supplier
        FROM products ORDER BY name LIMIT 100
    """)
    suppliers = query_df("SELECT name, phone, email, address FROM suppliers ORDER BY name LIMIT 100")
    sales = query_df("""
        SELECT COUNT(*) AS bills, COALESCE(SUM(total),0) AS revenue,
               COALESCE(SUM(profit),0) AS profit,
               COALESCE(SUM(quantity),0) AS units
        FROM sales
    """)
    purchases = query_df("""
        SELECT COUNT(*) AS entries, COALESCE(SUM(total),0) AS amount,
               COALESCE(SUM(quantity),0) AS units
        FROM purchases
    """)
    return {
        "products": products.to_dict(orient="records"),
        "suppliers": suppliers.to_dict(orient="records"),
        "sales_summary": sales.iloc[0].to_dict() if not sales.empty else {},
        "purchase_summary": purchases.iloc[0].to_dict() if not purchases.empty else {},
    }


def _ai_make_plan(user_text):
    """
    Convert natural language into a constrained JSON action using Gemini.
    The model never receives SQL access; Python validates and executes actions.
    """
    client = _get_gemini_client()
    if client is None:
        return None, "Gemini API not connected. Add GEMINI_API_KEY to Streamlit Secrets."
    snapshot = _ai_database_snapshot()
    system_prompt = """
You are the advanced conversational AI assistant inside SmartStock AI inventory and sales software.
Understand Hindi, Hinglish and English. Be friendly, concise and practical.
Return ONLY valid JSON with keys:
action, product_name, sku, brand, category, purchase_price, selling_price,
quantity, reorder_level, supplier, supplier_name, phone, email, address,
new_name, new_phone, new_email, new_address, customer, date_range, question.
Allowed action values:
answer, list_products, list_suppliers, stock_summary, low_stock, out_of_stock,
sales_summary, today_sales, profit_summary, top_products, purchase_summary,
add_product, add_stock, remove_stock, set_stock, set_price, add_supplier,
update_supplier, delete_supplier, delete_product, add_purchase, record_sale,
product_details, supplier_details, recent_sales, recent_purchases, period_report.
Extra keys for period_report: start_date, end_date (YYYY-MM-DD), metric (sales, profit or both).
Rules:
- For sales/profit over a time period (e.g. last 1 month, 2 mahine, this week, 15 din)
  use action=period_report. Compute start_date and end_date from TODAY (given with the
  request). "N mahine" means the last N months up to today.
- Use answer for general questions or questions unrelated to the database.
- For database questions, choose the best matching action.
- Never invent names, quantities, prices, phone numbers, emails or addresses.
- For add_product require product_name; include only fields the user supplied.
- For add_supplier require supplier_name; include only supplied contact details.
- For stock/purchase/sale changes, extract exact product_name and quantity.
- For delete_supplier/delete_product, identify exact name; Python will ask confirmation.
- For ambiguous/missing details, use action=answer and ask one concise clarification.
- question should contain the user's actual question for answer action.
- Do not claim a change has happened. Python will perform it.
"""
    try:
        response = client.models.generate_content(
            model=_gemini_model_name(),
            contents=(
                "TODAY (IST): " + today_ist().isoformat() +
                "\nDATABASE FACTS (JSON): " + json.dumps(snapshot, default=str) +
                "\nUSER REQUEST: " + user_text
            ),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        raw = response.text or "{}"
        return json.loads(raw), None
    except Exception as exc:
        return None, f"Gemini API error: {exc}"


def _ai_answer_with_context(question):
    client = _get_gemini_client()
    if client is None:
        return ("Gemini API is not connected. Please configure GEMINI_API_KEY "
                "in Streamlit Secrets.")
    facts = _ai_database_snapshot()
    try:
        response = client.models.generate_content(
            model=_gemini_model_name(),
            contents=(
                "Current store database snapshot:\n" + json.dumps(facts, default=str) +
                "\n\nUser asks: " + question
            ),
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are the advanced AI assistant for SmartStock AI. Reply in the user's "
                    "language (Hindi/Hinglish/English). Be helpful and clear. For inventory facts, "
                    "use ONLY the supplied database snapshot. If data is absent, say so. "
                    "Never pretend to perform actions. You may answer general knowledge "
                    "questions, but clearly distinguish general knowledge from store data."
                ),
                temperature=0.3,
            ),
        )
        return response.text or "I couldn't generate a response."
    except Exception as exc:
        return f"Gemini response error: {exc}"


def _ai_find_supplier(name):
    rows = query_df("SELECT * FROM suppliers WHERE lower(name)=lower(?)", (name.strip(),))
    if rows.empty:
        rows = query_df("SELECT * FROM suppliers WHERE lower(name) LIKE lower(?)", (f"%{name.strip()}%",))
    return rows.iloc[0] if len(rows) == 1 else None


def _ai_execute_plan(plan):
    action = str(plan.get("action", "answer")).strip().lower()
    product_name = str(plan.get("product_name") or "").strip()
    supplier_name = str(plan.get("supplier_name") or plan.get("supplier") or "").strip()
    now = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()

    def ask_confirmation(label, sql, params):
        st.session_state["ai_pending_action"] = {
            "label": label, "sql": sql, "params": params
        }
        return f"⚠️ Confirmation required: {label}. Press **Confirm action** below to proceed."

    if action == "answer":
        return _ai_answer_with_context(str(plan.get("question") or "Please clarify your request."))

    if action == "period_report":
        try:
            start = _date.fromisoformat(str(plan.get("start_date"))[:10])
            end = _date.fromisoformat(str(plan.get("end_date") or today)[:10])
        except Exception:
            return "Kaunsi period ki report chahiye? Jaise: 'pichle 1 mahine ki sales aur profit dikhao'."
        if start > end:
            start, end = end, start
        return _period_report(
            start, end,
            f"{start:%d %b %Y} – {end:%d %b %Y}",
            str(plan.get("metric") or "both").lower()
        )

    if action in ("list_products", "stock_summary"):
        df = query_df("SELECT name, sku, stock, selling_price, supplier FROM products ORDER BY name")
        if df.empty:
            return "No products are saved in the database yet."
        if action == "stock_summary":
            return f"Total stock is {int(df.stock.sum())} units across {len(df)} products."
        return "📦 Products:\n" + "\n".join(
            f"• {r['name']} | SKU: {r['sku'] or '-'} | Stock: {int(r['stock'])} | Price: {money(r['selling_price'])}"
            for _, r in df.iterrows())

    if action == "list_suppliers":
        df = query_df("SELECT name, phone, email, address FROM suppliers ORDER BY name")
        return "No suppliers found." if df.empty else "👥 Suppliers:\n" + "\n".join(
            f"• {r['name']} | {r['phone'] or '-'} | {r['email'] or '-'} | {r['address'] or '-'}"
            for _, r in df.iterrows())

    if action == "low_stock":
        df = query_df("SELECT name, stock, reorder_level FROM products WHERE stock<=reorder_level ORDER BY stock")
        return "✅ No low-stock products." if df.empty else "⚠️ Low stock:\n" + "\n".join(
            f"• {r['name']}: {int(r['stock'])} (reorder at {int(r['reorder_level'])})" for _, r in df.iterrows())

    if action == "out_of_stock":
        df = query_df("SELECT name FROM products WHERE stock<=0 ORDER BY name")
        return "✅ No products are out of stock." if df.empty else "🚨 Out of stock:\n" + "\n".join("• " + n for n in df.name)

    if action in ("sales_summary", "today_sales", "profit_summary", "top_products", "recent_sales"):
        if action == "today_sales":
            df = query_df("SELECT COALESCE(SUM(total),0) revenue, COALESCE(SUM(profit),0) profit, COALESCE(SUM(quantity),0) units FROM sales WHERE date(sale_date)=?", (today,))
            r = df.iloc[0]
            return f"Today's sales: {money(r.revenue)} | Profit: {money(r.profit)} | Units sold: {int(r.units)}."
        if action == "profit_summary":
            df = query_df("SELECT COALESCE(SUM(profit),0) profit FROM sales")
            return f"Total recorded profit: {money(df.iloc[0].profit)}."
        if action == "top_products":
            df = query_df("SELECT product_name, SUM(quantity) units FROM sales GROUP BY product_name ORDER BY units DESC LIMIT 5")
            return "No sales data yet." if df.empty else "🏆 Top products:\n" + "\n".join(
                f"• {r.product_name}: {int(r.units)} units" for _, r in df.iterrows())
        if action == "recent_sales":
            df = query_df("SELECT product_name, customer, quantity, total, sale_date FROM sales ORDER BY id DESC LIMIT 10")
            return "No sales found." if df.empty else "🧾 Recent sales:\n" + "\n".join(
                f"• {r.product_name} × {int(r.quantity)} | {money(r.total)} | {r.sale_date}" for _, r in df.iterrows())
        df = query_df("SELECT COUNT(*) bills, COALESCE(SUM(total),0) revenue, COALESCE(SUM(profit),0) profit, COALESCE(SUM(quantity),0) units FROM sales")
        r = df.iloc[0]
        return f"Sales: {money(r.revenue)} | Profit: {money(r.profit)} | Units: {int(r.units)} | Sale entries: {int(r.bills)}."

    if action in ("purchase_summary", "recent_purchases"):
        df = query_df("SELECT product_name, supplier, quantity, total, purchase_date FROM purchases ORDER BY id DESC LIMIT 10")
        return "No purchase records found." if df.empty else "🛒 Recent purchases:\n" + "\n".join(
            f"• {r.product_name} × {int(r.quantity)} | {r.supplier or '-'} | {money(r.total)} | {r.purchase_date}"
            for _, r in df.iterrows())

    if action in ("product_details", "add_stock", "remove_stock", "set_stock", "set_price", "delete_product", "add_purchase", "record_sale"):
        products = query_df("SELECT * FROM products ORDER BY name")
        row = _find_product(product_name, products) if product_name else None
        if action == "add_product":
            row = None
        elif row is None and action != "add_product":
            return f"I couldn't uniquely identify '{product_name}'. Please provide the exact product name."
        if action == "product_details":
            return (f"{row['name']}: stock {int(row['stock'])}, selling price {money(row['selling_price'])}, "
                    f"purchase price {money(row['purchase_price'])}, category {row['category'] or '-'}, supplier {row['supplier'] or '-'}.")
        if action == "delete_product":
            return ask_confirmation(f"Delete product '{row['name']}'", "DELETE FROM products WHERE id=?", (int(row["id"]),))
        qty = int(plan.get("quantity") or 0)
        if action in ("add_stock", "remove_stock", "add_purchase", "record_sale") and qty <= 0:
            return "Please specify a quantity greater than zero."
        if action == "add_stock":
            execute("UPDATE products SET stock=stock+?, updated_at=? WHERE id=?", (qty, now, int(row["id"])))
            return f"✅ Added {qty} units to {row['name']}. New stock: {int(row['stock'])+qty}."
        if action == "remove_stock":
            if qty > int(row["stock"]):
                return f"Not enough stock. {row['name']} has only {int(row['stock'])} units."
            execute("UPDATE products SET stock=stock-?, updated_at=? WHERE id=?", (qty, now, int(row["id"])))
            return f"✅ Removed {qty}. Remaining stock: {int(row['stock'])-qty}."
        if action == "set_stock":
            if plan.get("quantity") is None:
                return "Please tell me the exact stock quantity to set."
            return ask_confirmation(f"Set {row['name']} stock to {qty}", "UPDATE products SET stock=?, updated_at=? WHERE id=?", (qty, now, int(row["id"])))
        if action == "set_price":
            price = plan.get("selling_price")
            if price is None or float(price) < 0:
                return "Please provide a valid selling price."
            conn = db()
            try:
                cur = conn.cursor()
                cur.execute("INSERT INTO price_history(product_id,old_price,new_price,changed_at) VALUES(?,?,?,?)",
                            (int(row["id"]), float(row["selling_price"]), float(price), now))
                cur.execute("UPDATE products SET selling_price=?,updated_at=? WHERE id=?", (float(price), now, int(row["id"])))
                conn.commit()
            finally:
                conn.close()
            return f"✅ {row['name']} price updated to {money(price)}."
        if action == "add_purchase":
            cost = float(plan.get("purchase_price") or row["purchase_price"] or 0)
            total = cost * qty
            execute("UPDATE products SET stock=stock+?, purchase_price=?, updated_at=? WHERE id=?", (qty, cost, now, int(row["id"])))
            execute("INSERT INTO purchases(purchase_no,product_id,product_name,supplier,quantity,unit_cost,total,purchase_date,status) VALUES(?,?,?,?,?,?,?,?,?)",
                    (f"AI-{datetime.now().strftime('%Y%m%d%H%M%S')}", int(row["id"]), row["name"], supplier_name or row["supplier"], qty, cost, total, today, "Completed"))
            return f"✅ Purchase saved: {qty} × {row['name']}; stock is now {int(row['stock'])+qty}. Purchase total {money(total)}."
        if action == "record_sale":
            if qty > int(row["stock"]):
                return f"Not enough stock. Available: {int(row['stock'])}."
            price = float(plan.get("selling_price") or row["selling_price"])
            total = price * qty
            profit = (price - float(row["purchase_price"] or 0)) * qty
            execute("UPDATE products SET stock=stock-?, updated_at=? WHERE id=?", (qty, now, int(row["id"])))
            execute("INSERT INTO sales(invoice_no,product_id,product_name,customer,quantity,unit_price,unit_cost,total,profit,sale_date) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (f"AI-{datetime.now().strftime('%Y%m%d%H%M%S')}", int(row["id"]), row["name"], plan.get("customer") or "Walk-in", qty, price, float(row["purchase_price"] or 0), total, profit, today))
            return f"✅ Sale recorded: {qty} × {row['name']} for {money(total)}. Remaining stock: {int(row['stock'])-qty}."
        return "I couldn't complete that product action."

    if action == "add_product":
        name = product_name
        if not name:
            return "Please provide the product name."
        sku = str(plan.get("sku") or "").strip() or None
        try:
            execute("""INSERT INTO products(sku,name,brand,category,purchase_price,selling_price,stock,reorder_level,supplier,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (sku, name, plan.get("brand"), plan.get("category"),
                     float(plan.get("purchase_price") or 0), float(plan.get("selling_price") or 0),
                     int(plan.get("quantity") or 0), int(plan.get("reorder_level") or 5),
                     supplier_name or None, now, now))
            if supplier_name:
                execute("INSERT OR IGNORE INTO suppliers(name) VALUES(?)", (supplier_name,))
            return f"✅ Product '{name}' added to inventory."
        except DB_INTEGRITY_ERRORS:
            return "A product with that SKU/name already exists. Check the inventory first."

    if action in ("add_supplier", "update_supplier", "delete_supplier", "supplier_details"):
        if not supplier_name:
            return "Please tell me the supplier's exact name."
        row = _ai_find_supplier(supplier_name)
        if action == "supplier_details":
            return "Supplier not found or name is ambiguous." if row is None else (
                f"{row['name']} | Phone: {row['phone'] or '-'} | Email: {row['email'] or '-'} | Address: {row['address'] or '-'}.")
        if action == "add_supplier":
            try:
                execute("INSERT INTO suppliers(name,phone,email,address) VALUES(?,?,?,?)",
                        (supplier_name, plan.get("phone"), plan.get("email"), plan.get("address")))
                return f"✅ Supplier '{supplier_name}' added successfully."
            except DB_INTEGRITY_ERRORS:
                return "This supplier already exists. Ask me to update its details instead."
        if row is None:
            return "Supplier not found or name is ambiguous."
        if action == "delete_supplier":
            return ask_confirmation(f"Delete supplier '{row['name']}'", "DELETE FROM suppliers WHERE id=?", (int(row["id"]),))
        fields = []
        values = []
        for field, key in (("phone","new_phone"),("email","new_email"),("address","new_address")):
            if plan.get(key) is not None:
                fields.append(field + "=?")
                values.append(plan[key])
        if not fields:
            return "Tell me which supplier detail to update (phone, email or address)."
        values.append(int(row["id"]))
        execute("UPDATE suppliers SET " + ", ".join(fields) + " WHERE id=?", tuple(values))
        return f"✅ Supplier '{row['name']}' details updated."

    return "I understood the request, but need one more detail. Please rephrase it or tell me the exact product/supplier name."


_NUM_WORDS = {
    "ek": 1, "one": 1, "do": 2, "two": 2, "teen": 3, "three": 3,
    "char": 4, "chaar": 4, "four": 4, "paanch": 5, "panch": 5, "five": 5,
    "chhe": 6, "che": 6, "six": 6, "saat": 7, "seven": 7,
    "aath": 8, "eight": 8, "nau": 9, "nine": 9, "das": 10, "ten": 10,
}
_NUM = r"(\d+|ek|one|do|two|teen|three|char|chaar|four|paanch|panch|five|chhe|che|six|saat|seven|aath|eight|nau|nine|das|ten)"
_MONTH_UNIT = r"(mahine|mahina|mahinon|mahinay|month|months|महीने|महीना|महिने)"
_WEEK_UNIT = r"(hafte|hafta|haftey|week|weeks|हफ्ते|हफ्ता|सप्ताह)"
_DAY_UNIT = r"(din|dino|days|day|दिन)"
_YEAR_UNIT = r"(saal|saalon|year|years|साल|वर्ष)"
_SALES_RE = r"(?<![a-z])(sale|sales|bikri|bikree|revenue|becha|bika)(?![a-z])|बिक्री"
_PROFIT_RE = r"(?<![a-z])(profit|munafa|munaafa|labh|fayda|nafa|naafa)(?![a-z])|मुनाफा|मुनाफ़ा|लाभ"
_WRITE_RE = r"(?<![a-z])(sell|bech|add|delete|remove|hata|update|set|record|create|naya|new)(?![a-z])"


def _to_int(token):
    token = token.strip().lower()
    return int(token) if token.isdigit() else _NUM_WORDS.get(token, 1)


def _parse_period(text, today):
    """Return (start, end, label) for phrases like '1 mahine', 'last 15 din', 'pichle mahine'."""
    t = " " + str(text).lower() + " "

    m = re.search(_NUM + r"\s*" + _MONTH_UNIT, t)
    if m:
        n = _to_int(m.group(1))
        return months_back(today, n) + timedelta(days=1), today, f"Last {n} month{'s' if n > 1 else ''}"

    m = re.search(_NUM + r"\s*" + _WEEK_UNIT, t)
    if m:
        n = _to_int(m.group(1))
        return today - timedelta(days=7 * n - 1), today, f"Last {n} week{'s' if n > 1 else ''}"

    m = re.search(_NUM + r"\s*" + _DAY_UNIT, t)
    if m:
        n = _to_int(m.group(1))
        return today - timedelta(days=n - 1), today, f"Last {n} day{'s' if n > 1 else ''}"

    m = re.search(_NUM + r"\s*" + _YEAR_UNIT, t)
    if m:
        n = _to_int(m.group(1))
        return months_back(today, 12 * n) + timedelta(days=1), today, f"Last {n} year{'s' if n > 1 else ''}"

    if re.search(r"(pichl[ae]|pichhl[ae]|last|previous|पिछले)\s+" + _MONTH_UNIT, t):
        first_this = today.replace(day=1)
        end = first_this - timedelta(days=1)
        return end.replace(day=1), end, "Previous month"

    if re.search(r"(?<![a-z])(is|iss|this|current|इस)\s+" + _MONTH_UNIT, t):
        return today.replace(day=1), today, "This month"

    if re.search(r"(?<![a-z])(is|iss|this|इस)\s+" + _WEEK_UNIT, t):
        return today - timedelta(days=today.weekday()), today, "This week"

    if re.search(r"(?<![a-z])(is|iss|this|इस)\s+" + _YEAR_UNIT, t):
        return today.replace(month=1, day=1), today, "This year"

    if re.search(r"(?<![a-z])(aaj|today)(?![a-z])|आज", t):
        return today, today, "Today"

    if re.search(r"(?<![a-z])(kal|yesterday)(?![a-z])|कल", t):
        y = today - timedelta(days=1)
        return y, y, "Yesterday"

    if re.search(_MONTH_UNIT, t):
        return months_back(today, 1) + timedelta(days=1), today, "Last 1 month"

    return None


def _period_report(start, end, label, focus="both"):
    s_iso, e_iso = start.isoformat(), end.isoformat()
    where = "WHERE substr(sale_date,1,10) BETWEEN ? AND ?"
    tot = query_df(
        "SELECT COUNT(*) bills, COALESCE(SUM(total),0) revenue, "
        "COALESCE(SUM(profit),0) profit, COALESCE(SUM(quantity),0) units "
        "FROM sales " + where, (s_iso, e_iso)
    ).iloc[0]
    heading = f"📊 **{label}** ({start:%d %b %Y} – {end:%d %b %Y})"
    if int(tot.bills) == 0:
        return heading + "\n\nIs period me koi sale record nahi hui."

    revenue, profit = float(tot.revenue), float(tot.profit)
    margin = (profit / revenue * 100) if revenue else 0
    lines = [heading, ""]
    if focus != "profit":
        lines.append(f"- 💰 **Sales:** {money(revenue)}")
    if focus != "sales":
        lines.append(f"- 📈 **Profit:** {money(profit)} (margin {margin:.1f}%)")
    lines.append(f"- 📦 Units sold: {int(tot.units)} | 🧾 Sale entries: {int(tot.bills)}")

    order = "profit" if focus == "profit" else "revenue"
    top = query_df(
        "SELECT product_name, SUM(quantity) units, SUM(total) revenue, SUM(profit) profit "
        "FROM sales " + where + f" GROUP BY product_name ORDER BY {order} DESC LIMIT 5",
        (s_iso, e_iso)
    )
    if not top.empty:
        lines += ["", "**🏆 Top products**"]
        for _, r in top.iterrows():
            lines.append(
                f"- {r.product_name} — {int(r.units)} units | Sales {money(r.revenue)} | Profit {money(r.profit)}"
            )
    return "\n".join(lines)


def _quick_period_answer(text):
    """Answers 'N mahine ki sales/profit' style questions directly from the database."""
    t = str(text).lower()
    has_sales = bool(re.search(_SALES_RE, t))
    has_profit = bool(re.search(_PROFIT_RE, t))
    if not (has_sales or has_profit) or re.search(_WRITE_RE, t):
        return None
    period = _parse_period(t, today_ist())
    if period is None:
        return None
    start, end, label = period
    focus = "profit" if (has_profit and not has_sales) else "sales" if (has_sales and not has_profit) else "both"
    return _period_report(start, end, label, focus)


def process_ai(command):
    original = str(command or "").strip()
    if not original:
        return "Please ask me something."
    quick = _quick_period_answer(original)
    if quick:
        return quick
    plan, error = _ai_make_plan(original)
    if error:
        return error
    if not isinstance(plan, dict):
        return "I couldn't understand that. Please try again in simple words."
    return _ai_execute_plan(plan)


def ai_page():
    st.markdown("# 🤖 SmartStock AI Assistant")
    st.caption("Your intelligent inventory and sales assistant. Talk naturally in Hindi, Hinglish or English.")
    client = _get_gemini_client()
    if client:
        st.success("🟢 AI Assistant online — Gemini API connected")
    else:
        st.warning("API not connected. Add GEMINI_API_KEY in Streamlit Secrets to enable advanced AI.")

    with st.expander("What can I ask the AI Assistant?"):
        st.markdown("""
        - "Aaj kitni sale hui aur kitna profit hua?"
        - "1 mahine ki sales aur profit dikhao."
        - "2 mahine ki sales dikhao."
        - "Pichle mahine ka profit batao."
        - "Last 15 din ki sales dikhao."
        - "Mere low-stock products batao."
        - "Add 30 units of Maggi."
        - "Naya product add karo: Amul Butter, category Dairy, price 60, stock 20."
        - "Ravi Traders naam ka supplier add karo, phone 9876543210."
        - "Supplier Tech Zone ka phone update karo."
        - "OnePlus Buds ka stock 10 kar do."
        - "5 Samsung S24 sell karo."
        - "Recent purchases dikhao."
        - "Which products are most profitable?"
        """)

    if "ai_chat_history" not in st.session_state:
        st.session_state["ai_chat_history"] = []
    for item in st.session_state["ai_chat_history"][-12:]:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])

    prompt = st.chat_input("Ask anything about your store...")
    if prompt:
        st.session_state["ai_chat_history"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        result = process_ai(prompt)
        st.session_state["ai_chat_history"].append({"role": "assistant", "content": result})
        with st.chat_message("assistant"):
            st.markdown(result)

    pending = st.session_state.get("ai_pending_action")
    if pending:
        st.warning(pending["label"] + " — this action changes your database.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Confirm action", type="primary", key="ai_confirm_action"):
                execute(pending["sql"], tuple(pending["params"]))
                st.session_state.pop("ai_pending_action", None)
                st.success("Action completed successfully.")
                st.rerun()
        with c2:
            if st.button("Cancel", key="ai_cancel_action"):
                st.session_state.pop("ai_pending_action", None)
                st.info("Action cancelled.")
                st.rerun()


# =========================================================
# INVENTORY ALERTS
# =========================================================

def alerts_page():

    st.markdown("# 🔔 Inventory Alerts")

    data = query_df("SELECT * FROM products")

    low = data[
        data["stock"] <= data["reorder_level"]
    ]

    out = data[data["stock"] <= 0]

    c1, c2 = st.columns(2)

    with c1:

        st.markdown("### ⚠️ Low Stock")

        if low.empty:

            st.success("No low-stock products.")

        else:

            for _, row in low.iterrows():

                st.warning(
                    f"{row['name']} — {row['stock']} units"
                )

    with c2:

        st.markdown("### 🚨 Out of Stock")

        if out.empty:

            st.success("No out-of-stock products.")

        else:

            for _, row in out.iterrows():
                st.error(row["name"])


# =========================================================
# SETTINGS
# =========================================================

def settings_page():

    st.markdown("# ⚙️ Settings")

    st.markdown("""
### SmartStock AI

**Frontend**
- Streamlit

**Language**
- Python

**Database**
- SQLite

**Data Processing**
- Pandas

**Visualization**
- Plotly

**AI Layer**
- Natural-language command prototype

**Version Control**
- Git / GitHub

### Planned Advanced Features
- FastAPI backend
- PostgreSQL / MySQL
- User authentication
- Seller/Admin roles
- LLM integration
- Voice commands
- Demand forecasting
- AI purchase recommendations
- Sales prediction
- Cloud deployment
""")

    st.divider()

    if USE_PG:
        st.markdown("### ☁️ Cloud Database")
        st.success(
            "Connected to your cloud PostgreSQL database. Everything you add "
            "is saved permanently, even if the app restarts or is redeployed."
        )
        st.download_button(
            "📥 Download all data (ZIP of CSV files)",
            data=export_zip(),
            file_name=f"smartstock_data_{today_ist().isoformat()}.zip",
            mime="application/zip"
        )
        return

    st.markdown("### 💾 Backup & Restore")
    st.caption(
        "All your products, sales and purchases are saved in a SQLite file. "
        "Download a backup regularly so your data is never lost."
    )
    st.caption(f"Database file: {DB_FILE}")

    if DB_FILE.exists():
        st.download_button(
            "📥 Download full backup (.db)",
            data=DB_FILE.read_bytes(),
            file_name=f"smartstock_backup_{today_ist().isoformat()}.db",
            mime="application/octet-stream"
        )

    uploaded = st.file_uploader(
        "Restore from a backup file",
        type=["db", "sqlite", "sqlite3"],
        key="restore_upload"
    )
    if uploaded is not None:
        st.warning("Restoring will replace ALL current data with the backup.")
        if st.button("♻️ Restore this backup", key="restore_btn"):
            blob = uploaded.getvalue()
            safety_copy = DB_FILE.with_name("smartstock_before_restore.db")
            if not blob.startswith(b"SQLite format 3"):
                st.error("This is not a valid SmartStock backup file.")
            else:
                try:
                    shutil.copy2(DB_FILE, safety_copy)
                    DB_FILE.write_bytes(blob)
                    conn = db()
                    try:
                        conn.execute("SELECT COUNT(*) FROM products")
                        conn.execute("CREATE TABLE IF NOT EXISTS app_meta(key TEXT PRIMARY KEY, value TEXT)")
                        conn.execute(
                            "INSERT OR REPLACE INTO app_meta(key, value) VALUES('demo_data_cleared', ?)",
                            (datetime.now().isoformat(),)
                        )
                        conn.commit()
                    finally:
                        conn.close()
                    initialize_database()
                    flash("Backup restored successfully.")
                    st.rerun()
                except sqlite3.Error as exc:
                    try:
                        shutil.copy2(safety_copy, DB_FILE)
                    except Exception:
                        pass
                    st.error(f"Restore failed, previous data kept: {exc}")


# =========================================================
# FINAL PAGE ROUTER
# =========================================================

show_flash()

if page == " Dashboard":

    dashboard()

elif page == " Inventory":

    inventory_page()

elif page == "💰 Sales":

    sales_page()

elif page == "🛒 Purchases":

    purchases_page()

elif page == "👥 Suppliers":

    suppliers_page()

elif page == "📊 Reports":

    reports_page()

elif page == "🤖 AI Assistant":

    ai_page()

elif page == "🔔 Alerts":

    alerts_page()

elif page == "⚙️ Settings":

    settings_page()


