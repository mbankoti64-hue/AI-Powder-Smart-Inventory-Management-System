import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import re


# PAGE CONFIGURATION==============================

st.set_page_config(
    page_title="SmartStock AI",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = Path("smartstock.db")


# DATABASE HELPERS==========================


def db():
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def query_df(sql, params=()):
    conn = db()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


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

    count = cur.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]

    if count == 0:

        products = [
            ("SKU001", "iPhone 15", "Apple",
             "Mobile Phones", 52000, 57000, 32, 8,
             "Mobile World"),

            ("SKU002", "OnePlus 12", "OnePlus",
             "Mobile Phones", 39000, 45000, 27, 7,
             "Tech Zone"),

            ("SKU003", "Samsung S24", "Samsung",
             "Mobile Phones", 47000, 55000, 24, 7,
             "Tech Zone"),

            ("SKU004", "Boat Airdopes 131", "Boat",
             "Earbuds & Audio", 1200, 2450, 44, 10,
             "Audio World"),

            ("SKU005", "Samsung Galaxy Buds 2", "Samsung",
             "Earbuds & Audio", 6500, 7999, 13, 5,
             "Audio World"),

            ("SKU006", "OnePlus Buds", "OnePlus",
             "Earbuds & Audio", 3000, 3999, 8, 5,
             "Audio World"),

            ("SKU007", "LG 55 4K TV", "LG",
             "Television", 46000, 52000, 14, 5,
             "Home Appliances"),

            ("SKU008", "Sony Bravia 55", "Sony",
             "Television", 52000, 61000, 9, 4,
             "Home Appliances"),

            ("SKU009", "HP Pavilion 15", "HP",
             "Laptops", 56000, 65000, 11, 5,
             "NextGen Distributors"),

            ("SKU010", "Dell Inspiron 14", "Dell",
             "Laptops", 51000, 59000, 4, 5,
             "NextGen Distributors"),

            ("SKU011", "Samsung Washing Machine", "Samsung",
             "Washing Machines", 36000, 42500, 3, 5,
             "Home Appliances"),

            ("SKU012", "LG Refrigerator", "LG",
             "Refrigerators", 42000, 49000, 7, 5,
             "Home Appliances")
        ]

        cur.executemany("""
            INSERT INTO products(
                sku, name, brand, category,
                purchase_price, selling_price,
                stock, reorder_level, supplier
            )
            VALUES(?,?,?,?,?,?,?,?,?)
        """, products)

        suppliers = [
            ("Mobile World", "9876500011",
             "mobile@example.com", "Dehradun"),

            ("Tech Zone", "9876500012",
             "tech@example.com", "Delhi"),

            ("Audio World", "9876500013",
             "audio@example.com", "Haridwar"),

            ("Home Appliances", "9876500014",
             "home@example.com", "Dehradun"),

            ("NextGen Distributors", "9876500015",
             "nextgen@example.com", "Noida")
        ]

        cur.executemany("""
            INSERT OR IGNORE INTO suppliers(
                name, phone, email, address
            )
            VALUES(?,?,?,?)
        """, suppliers)

        conn.commit()

        product_map = {
            row["name"]: row["id"]
            for row in cur.execute(
                "SELECT id, name FROM products"
            ).fetchall()
        }

        sales_pattern = [
            ("iPhone 15", 1, 57000, 52000),
            ("OnePlus 12", 2, 45000, 39000),
            ("Samsung S24", 1, 55000, 47000),
            ("Boat Airdopes 131", 5, 2450, 1200),
            ("Samsung Galaxy Buds 2", 2, 7999, 6500),
            ("OnePlus Buds", 3, 3999, 3000),
            ("LG 55 4K TV", 1, 52000, 46000),
            ("Sony Bravia 55", 1, 61000, 52000),
            ("HP Pavilion 15", 1, 65000, 56000),
            ("Dell Inspiron 14", 2, 59000, 51000)
        ]

        customers = [
            "MAYANK", "PAWANI", "ANSHUMAN", "ADVAIT",
            "LUCKY", "Riya", "Mohit", "Pooja"
        ]

        today = datetime.now().date()
        invoice_counter = 100

        for day_offset in range(29, -1, -1):

            sale_day = today - timedelta(days=day_offset)
            number_of_sales = 1 + (day_offset % 3)

            for n in range(number_of_sales):

                item = sales_pattern[
                    (day_offset + n) % len(sales_pattern)
                ]

                product_name, qty, price, cost = item

                if day_offset % 7 == 0:
                    qty += 1

                invoice_counter += 1

                cur.execute("""
                    INSERT INTO sales(
                        invoice_no, product_id, product_name,
                        customer, quantity, unit_price,
                        unit_cost, total, profit, sale_date
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                """, (
                    f"SO-{invoice_counter}",
                    product_map[product_name],
                    product_name,
                    customers[(day_offset + n) % len(customers)],
                    qty,
                    price,
                    cost,
                    qty * price,
                    qty * (price - cost),
                    sale_day.isoformat()
                ))

        purchase_data = [
            ("iPhone 15", "Mobile World", 10, 52000),
            ("OnePlus 12", "Tech Zone", 15, 39000),
            ("Boat Airdopes 131", "Audio World", 30, 1200),
            ("LG 55 4K TV", "Home Appliances", 8, 46000),
            ("HP Pavilion 15", "NextGen Distributors", 6, 56000)
        ]

        for i, item in enumerate(purchase_data):

            product_name, supplier, qty, cost = item

            cur.execute("""
                INSERT INTO purchases(
                    purchase_no, product_id, product_name,
                    supplier, quantity, unit_cost, total,
                    purchase_date, status
                )
                VALUES(?,?,?,?,?,?,?,?,?)
            """, (
                f"PO-{500+i}",
                product_map[product_name],
                product_name,
                supplier,
                qty,
                cost,
                qty * cost,
                (today - timedelta(days=i+1)).isoformat(),
                "Completed"
            ))

    conn.commit()
    conn.close()


# =========================================================
# REFRESH DEMO DATES TO CURRENT DATE
# =========================================================

def refresh_demo_dates():
    """
    Refresh dates only for the predefined demo invoices
    and demo purchase numbers.
    """

    today = datetime.now().date()
    conn = db()
    cur = conn.cursor()

    try:
        invoice_counter = 100

        for day_offset in range(29, -1, -1):

            sale_day = today - timedelta(days=day_offset)
            number_of_sales = 1 + (day_offset % 3)

            for _ in range(number_of_sales):

                invoice_counter += 1

                cur.execute("""
                    UPDATE sales
                    SET sale_date=?
                    WHERE invoice_no=?
                """, (
                    sale_day.isoformat(),
                    f"SO-{invoice_counter}"
                ))

        for i in range(5):

            purchase_day = today - timedelta(days=i+1)

            cur.execute("""
                UPDATE purchases
                SET purchase_date=?
                WHERE purchase_no=?
            """, (
                purchase_day.isoformat(),
                f"PO-{500+i}"
            ))

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


initialize_database()
refresh_demo_dates()


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
        sales["sale_date"] = pd.to_datetime(sales["sale_date"], errors="coerce")
        valid_dates = sales["sale_date"].dropna()
        today = datetime.now().date()
        default_start = max(valid_dates.min().date(), today - timedelta(days=6)) if not valid_dates.empty else today
        date_range = st.date_input(
            "📅 Visualization Date Range",
            value=(default_start, today),
            key="dashboard_date_range"
        )
        if not isinstance(date_range, tuple) or len(date_range) != 2:
            st.info("Select a start date and an end date.")
            return
        start_date, end_date = date_range
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
                recent = filtered.sort_values("sale_date", ascending=False).head(6)
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
            "Which product is low in stock?",
            "Show profit",
            "Show top selling products"
        ]:
            if st.button(suggestion, key="dash_ai_" + suggestion, use_container_width=True):
                st.session_state["dashboard_ai_command"] = suggestion
                st.session_state["active_page"] = "🤖 AI Assistant"
                st.rerun()
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

                st.success("Product deleted.")
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

                    st.success("Product added successfully.")
                    st.rerun()

                except sqlite3.IntegrityError:
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

                st.success("Product updated.")
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
                            datetime.now().date().isoformat()
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

                        st.success(f"Sale completed: {invoice}")
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
                        datetime.now().date().isoformat(),
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

                    st.success("Purchase completed.")
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

                    st.success("Supplier added.")
                    st.rerun()

                except sqlite3.IntegrityError:
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

    data["sale_date"] = pd.to_datetime(data["sale_date"])

    min_date = data["sale_date"].min().date()
    max_date = data["sale_date"].max().date()

    date_range = st.date_input(
        "Select Report Period",
        value=(min_date, max_date)
    )

    if not isinstance(date_range, tuple) or len(date_range) != 2:

        st.info("Select both a start date and an end date.")
        return

    start, end = date_range

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

def process_ai(command):

    command = command.lower().strip()

    products = query_df("SELECT * FROM products")

    if "total stock" in command:

        total = products["stock"].sum()

        return f"📦 Current total stock: {int(total):,} units."

    if "profit" in command:

        sales = query_df("SELECT * FROM sales")

        return f"📈 Total recorded profit: {money(sales['profit'].sum())}"

    if "sales" in command or "revenue" in command:

        sales = query_df("SELECT * FROM sales")

        return f"💰 Total recorded sales: {money(sales['total'].sum())}"

    if "low stock" in command:

        low = products[
            products["stock"] <= products["reorder_level"]
        ]

        if low.empty:
            return "✅ No low-stock products."

        return "⚠️ Low-stock products:\n\n" + "\n".join(
            f"{row['name']} — {row['stock']} units"
            for _, row in low.iterrows()
        )

    if "out of stock" in command:

        out = products[products["stock"] <= 0]

        if out.empty:
            return "✅ No products are out of stock."

        return "🚨 Out-of-stock products:\n\n" + "\n".join(
            out["name"].tolist()
        )

    if "top selling" in command or "best selling" in command:

        sales = query_df("SELECT * FROM sales")

        if sales.empty:
            return "No sales data available."

        top = (
            sales.groupby("product_name")["quantity"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
        )

        return "🏆 Top-selling products:\n\n" + "\n".join(
            f"{name} — {qty} units"
            for name, qty in top.items()
        )

    match = re.search(
        r"(?:add|increase)\s+(\d+)\s+(?:pieces?|units?).*?(.+)",
        command
    )

    if match:

        qty = int(match.group(1))

        product_text = (
            match.group(2)
            .replace("of", "")
            .strip()
        )

        found = products[
            products["name"].str.lower().str.contains(
                re.escape(product_text),
                na=False
            )
        ]

        if not found.empty:

            row = found.iloc[0]

            execute("""
                UPDATE products
                SET stock=stock+?, updated_at=?
                WHERE id=?
            """, (
                qty,
                datetime.now().isoformat(),
                row["id"]
            ))

            return f"✅ Added {qty} units to {row['name']}."

        return "Product not found. Check the product name."

    return (
        "🤖 Try these commands:\n\n"
        "• Show total stock\n"
        "• Show sales\n"
        "• Show profit\n"
        "• Show low stock\n"
        "• Show out of stock\n"
        "• Show top selling products\n"
        "• Add 20 pieces of OnePlus Buds"
    )


def ai_page():

    st.markdown("# 🤖 SmartStock AI Assistant")

    st.caption(
        "Use natural-language commands to interact with inventory."
    )

    st.success("🟢 AI Assistant Online")

    st.markdown("### Example Commands")

    examples = [
        "Show total stock",
        "Show sales",
        "Show profit",
        "Show low stock",
        "Show top selling products",
        "Add 20 pieces of OnePlus Buds"
    ]

    for example in examples:
        st.code(example, language="text")

    command = st.text_input(
        "Enter your command",
        value=st.session_state.pop("dashboard_ai_command", "")
    )

    if st.button("🚀 Run Command", type="primary"):

        if command.strip():

            result = process_ai(command)
            st.info(result)


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


# =========================================================
# FINAL PAGE ROUTER
# =========================================================

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


