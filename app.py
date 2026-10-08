import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import date, datetime
from pathlib import Path
import re

# ============================================================
# SMARTSTOCK AI
# AI POWERED SMART INVENTORY MANAGEMENT SYSTEM
# ============================================================

st.set_page_config(
    page_title="SmartStock AI",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# DATABASE
# ============================================================

DB_PATH = Path("smartstock.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def execute(query, params=()):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    result = cur.lastrowid
    conn.close()
    return result


def read_df(query, params=()):
    conn = get_connection()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def money(value):
    return f"₹{value:,.0f}"


# ============================================================
# CREATE DATABASE
# ============================================================

def init_database():

    conn = get_connection()
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
        status TEXT DEFAULT 'Completed'
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
        changed_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    """)

    # ========================================================
    # DEMO DATA
    # ========================================================

    count = cur.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]

    if count == 0:

        products = [

            (
                "SKU001",
                "iPhone 15 (128GB)",
                "Apple",
                "Mobile Phones",
                52000,
                57000,
                32,
                8,
                "Mobile World Pvt. Ltd."
            ),

            (
                "SKU002",
                "OnePlus 12 (256GB)",
                "OnePlus",
                "Mobile Phones",
                39000,
                45000,
                28,
                7,
                "Tech Zone Suppliers"
            ),

            (
                "SKU003",
                "Samsung S24 (256GB)",
                "Samsung",
                "Mobile Phones",
                47000,
                55000,
                26,
                7,
                "Tech Zone Suppliers"
            ),

            (
                "SKU004",
                "Boat Airdopes 131",
                "Boat",
                "Earbuds & Audio",
                1200,
                2450,
                45,
                10,
                "Audio & More"
            ),

            (
                "SKU005",
                'LG 55" 4K TV',
                "LG",
                "Television",
                46000,
                52000,
                18,
                5,
                "Home Appliances Hub"
            ),

            (
                "SKU006",
                "Samsung WW80T",
                "Samsung",
                "Washing Machine",
                36000,
                42500,
                3,
                5,
                "Home Appliances Hub"
            ),

            (
                "SKU007",
                "iPhone 14 (128GB)",
                "Apple",
                "Mobile Phones",
                45000,
                51000,
                4,
                8,
                "Mobile World Pvt. Ltd."
            ),

            (
                "SKU008",
                "Samsung Galaxy Buds 2",
                "Samsung",
                "Earbuds & Audio",
                6500,
                7999,
                5,
                8,
                "Audio & More"
            ),

            (
                "SKU009",
                "OnePlus Buds",
                "OnePlus",
                "Earbuds & Audio",
                3000,
                3999,
                9,
                8,
                "Audio & More"
            ),

            (
                "SKU010",
                'Sony Bravia 55"',
                "Sony",
                "Television",
                52000,
                61000,
                12,
                5,
                "Home Appliances Hub"
            ),

            (
                "SKU011",
                "HP Pavilion 15",
                "HP",
                "Laptops",
                56000,
                65000,
                14,
                5,
                "Next Gen Distributors"
            ),

            (
                "SKU012",
                "Dell Inspiron 14",
                "Dell",
                "Laptops",
                51000,
                59000,
                10,
                5,
                "Next Gen Distributors"
            )
        ]

        cur.executemany("""
            INSERT INTO products
            (
                sku,
                name,
                brand,
                category,
                purchase_price,
                selling_price,
                stock,
                reorder_level,
                supplier
            )
            VALUES(?,?,?,?,?,?,?,?,?)
        """, products)

        suppliers = [

            (
                "Mobile World Pvt. Ltd.",
                "9876500011",
                "sales@mobileworld.com",
                "Dehradun"
            ),

            (
                "Tech Zone Suppliers",
                "9876500012",
                "contact@techzone.com",
                "Delhi"
            ),

            (
                "Audio & More",
                "9876500013",
                "audio@example.com",
                "Haridwar"
            ),

            (
                "Home Appliances Hub",
                "9876500014",
                "home@example.com",
                "Dehradun"
            ),

            (
                "Next Gen Distributors",
                "9876500015",
                "nextgen@example.com",
                "Noida"
            )
        ]

        cur.executemany("""
            INSERT OR IGNORE INTO suppliers
            (name,phone,email,address)
            VALUES(?,?,?,?)
        """, suppliers)

        # -----------------------------
        # Demo Sales
        # -----------------------------

        product_map = {}

        rows = cur.execute(
            "SELECT id,name FROM products"
        ).fetchall()

        for row in rows:
            product_map[row["name"]] = row["id"]

        sales = [

            (
                "#SO012",
                "iPhone 15 (128GB)",
                "Rahul Verma",
                1,
                57000,
                52000,
                "2025-05-31"
            ),

            (
                "#SO011",
                "OnePlus 12 (256GB)",
                "Sneha Kapoor",
                1,
                45000,
                39000,
                "2025-05-31"
            ),

            (
                "#SO010",
                "Samsung S24 (256GB)",
                "Rahul Singh",
                1,
                55000,
                47000,
                "2025-05-31"
            ),

            (
                "#SO009",
                "Boat Airdopes 131",
                "Ankit Sharma",
                1,
                2450,
                1200,
                "2025-05-31"
            ),

            (
                "#SO008",
                'LG 55" 4K TV',
                "Karan Patel",
                1,
                52000,
                46000,
                "2025-05-31"
            ),

            (
                "#SO007",
                "Boat Airdopes 131",
                "Neha Joshi",
                2,
                2450,
                1200,
                "2025-05-30"
            ),

            (
                "#SO006",
                "iPhone 14 (128GB)",
                "Aman Rawat",
                1,
                51000,
                45000,
                "2025-05-30"
            ),

            (
                "#SO005",
                "Samsung Galaxy Buds 2",
                "Riya Shah",
                1,
                7999,
                6500,
                "2025-05-29"
            ),

            (
                "#SO004",
                "OnePlus 12 (256GB)",
                "Mohit Negi",
                2,
                45000,
                39000,
                "2025-05-28"
            ),

            (
                "#SO003",
                'LG 55" 4K TV',
                "Arjun Singh",
                1,
                52000,
                46000,
                "2025-05-28"
            ),

            (
                "#SO002",
                "Samsung S24 (256GB)",
                "Pooja Bisht",
                2,
                55000,
                47000,
                "2025-05-27"
            ),

            (
                "#SO001",
                "Boat Airdopes 131",
                "Vikas Kumar",
                3,
                2450,
                1200,
                "2025-05-26"
            )
        ]

        for sale in sales:

            invoice = sale[0]
            product = sale[1]
            customer = sale[2]
            qty = sale[3]
            price = sale[4]
            cost = sale[5]
            dt = sale[6]

            total = qty * price
            profit = qty * (price - cost)

            cur.execute("""
                INSERT INTO sales
                (
                    invoice_no,
                    product_id,
                    product_name,
                    customer,
                    quantity,
                    unit_price,
                    unit_cost,
                    total,
                    profit,
                    sale_date
                )
                VALUES(?,?,?,?,?,?,?,?,?,?)
            """, (
                invoice,
                product_map[product],
                product,
                customer,
                qty,
                price,
                cost,
                total,
                profit,
                dt
            ))

        # -----------------------------
        # Demo Purchases
        # -----------------------------

        purchases = [

            (
                "#PO0057",
                "Mobile World Pvt. Ltd.",
                "iPhone 15 (128GB)",
                10,
                52000,
                "2025-05-31"
            ),

            (
                "#PO0056",
                "Tech Zone Suppliers",
                "OnePlus 12 (256GB)",
                8,
                39000,
                "2025-05-31"
            ),

            (
                "#PO0055",
                "Audio & More",
                "Boat Airdopes 131",
                20,
                1200,
                "2025-05-30"
            ),

            (
                "#PO0054",
                "Home Appliances Hub",
                'LG 55" 4K TV',
                5,
                46000,
                "2025-05-30"
            ),

            (
                "#PO0053",
                "Next Gen Distributors",
                "HP Pavilion 15",
                4,
                56000,
                "2025-05-29"
            )
        ]

        for purchase in purchases:

            no = purchase[0]
            supplier = purchase[1]
            product = purchase[2]
            qty = purchase[3]
            cost = purchase[4]
            dt = purchase[5]

            total = qty * cost

            cur.execute("""
                INSERT INTO purchases
                (
                    purchase_no,
                    product_id,
                    product_name,
                    supplier,
                    quantity,
                    unit_cost,
                    total,
                    purchase_date
                )
                VALUES(?,?,?,?,?,?,?,?)
            """, (
                no,
                product_map[product],
                product,
                supplier,
                qty,
                cost,
                total,
                dt
            ))

    conn.commit()
    conn.close()


init_database()


# ============================================================
# CSS
# ============================================================

st.markdown("""
<style>

.stApp {
    background:
        radial-gradient(
            circle at 15% 10%,
            rgba(80,70,220,.15),
            transparent 25%
        ),
        radial-gradient(
            circle at 85% 20%,
            rgba(0,150,255,.10),
            transparent 25%
        ),
        #07111f;
}

.block-container {
    padding-top: 1.2rem;
    max-width: 1600px;
}

[data-testid="stSidebar"] {
    background: #081426;
    border-right: 1px solid #20334d;
}

div[data-testid="stMetric"] {
    background:
        linear-gradient(
            145deg,
            #11243b,
            #0b1a2c
        );
    border: 1px solid #263e5d;
    border-radius: 15px;
    padding: 15px;
}

div[data-testid="stMetricLabel"] {
    color: #91a2b9 !important;
}

div[data-testid="stMetricValue"] {
    color: #ffffff !important;
}

div.stButton > button {
    border-radius: 10px;
    border: 1px solid #294263;
    background: #11243b;
    color: white;
}

div.stButton > button:hover {
    background: #1b3353;
    border-color: #765ff2;
}

.ss-card {
    background: #0d1c30;
    border: 1px solid #233b59;
    border-radius: 15px;
    padding: 18px;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("# 🔷 SmartStock AI")
    st.caption("Inventory Smarter, Grow Faster")

    st.divider()

    menu = st.radio(
        "Navigation",
        [
            "🏠 Dashboard",
            "📦 Inventory",
            "💰 Sales",
            "🛒 Purchases",
            "👥 Suppliers",
            "📊 Reports",
            "🤖 AI Assistant",
            "🔔 Alerts",
            "⚙️ Settings"
        ],
        label_visibility="collapsed"
    )

    st.divider()

    st.markdown("### ⚡ Quick Actions")

    if st.button(
        "➕ Add Product",
        use_container_width=True
    ):
        st.session_state["page"] = "Inventory"

    if st.button(
        "📦 Update Stock",
        use_container_width=True
    ):
        st.session_state["page"] = "Inventory"

    if st.button(
        "💰 New Sale",
        use_container_width=True
    ):
        st.session_state["page"] = "Sales"

    if st.button(
        "🛒 New Purchase",
        use_container_width=True
    ):
        st.session_state["page"] = "Purchases"

    st.divider()

    st.caption("Phase 1 / Phase 2 Prototype")
    st.caption(
        "Streamlit + Python + SQLite + Pandas + Plotly"
    )


# ============================================================
# DASHBOARD
# ============================================================

def dashboard():

    products = read_df(
        "SELECT * FROM products"
    )

    sales = read_df(
        "SELECT * FROM sales"
    )

    st.markdown(
        "# Good Evening, Mayank! 👋"
    )

    st.caption(
        "Here's what's happening with your business today."
    )

    # --------------------------------------------------------
    # Date Slider
    # --------------------------------------------------------

    min_date = pd.to_datetime(
        sales["sale_date"]
    ).min().date()

    max_date = pd.to_datetime(
        sales["sale_date"]
    ).max().date()

    start_date, end_date = st.slider(
        "📅 Visualization Date Range",
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date)
    )

    filtered_sales = sales[
        (
            pd.to_datetime(
                sales["sale_date"]
            ).dt.date >= start_date
        )
        &
        (
            pd.to_datetime(
                sales["sale_date"]
            ).dt.date <= end_date
        )
    ]

    # --------------------------------------------------------
    # KPI
    # --------------------------------------------------------

    total_stock = int(
        products["stock"].sum()
    )

    total_sales = float(
        filtered_sales["total"].sum()
    )

    total_profit = float(
        filtered_sales["profit"].sum()
    )

    low_stock = len(
        products[
            products["stock"]
            <=
            products["reorder_level"]
        ]
    )

    out_stock = len(
        products[
            products["stock"] <= 0
        ]
    )

    c1,c2,c3,c4,c5 = st.columns(5)

    c1.metric(
        "📦 Total Stock",
        f"{total_stock:,}"
    )

    c2.metric(
        "💰 Today's Sales",
        money(total_sales)
    )

    c3.metric(
        "📈 Today's Profit",
        money(total_profit)
    )

    c4.metric(
        "⚠️ Low Stock Items",
        low_stock
    )

    c5.metric(
        "🚨 Out of Stock",
        out_stock
    )

    st.divider()

    # ========================================================
    # SALES TREND + CATEGORY
    # ========================================================

    left,right = st.columns([1.5,1])

    with left:

        st.markdown(
            "### 📈 Sales Trend"
        )

        trend = (
            filtered_sales
            .groupby("sale_date", as_index=False)
            ["total"]
            .sum()
        )

        if not trend.empty:

            fig = px.line(
                trend,
                x="sale_date",
                y="total",
                markers=True
            )

            fig.update_layout(
                template="plotly_dark",
                height=330,
                margin=dict(
                    l=10,
                    r=10,
                    t=10,
                    b=10
                ),
                xaxis_title="Date",
                yaxis_title="Sales ₹"
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )
