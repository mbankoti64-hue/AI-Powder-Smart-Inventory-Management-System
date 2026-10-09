
import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from pathlib import Path
import re

# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="SmartStock AI",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# DATABASE
# =========================================================

DB_FILE = Path("smartstock.db")


def db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def query_df(sql, params=()):
    conn = db()
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


def execute(sql, params=()):
    conn = db()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    result = cur.lastrowid
    conn.close()
    return result


def money(value):
    return f"₹{value:,.0f}"


# =========================================================
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

    conn.commit()

    # -----------------------------------------------------
    # CHECK WHETHER PRODUCTS EXIST
    # -----------------------------------------------------

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
                sku,name,brand,category,
                purchase_price,selling_price,
                stock,reorder_level,supplier
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
                name,phone,email,address
            )
            VALUES(?,?,?,?)
        """, suppliers)

        conn.commit()

        # -------------------------------------------------
        # PRODUCT MAP
        # -------------------------------------------------

        rows = cur.execute(
            "SELECT id,name FROM products"
        ).fetchall()

        product_map = {
            row["name"]: row["id"]
            for row in rows
        }

        # -------------------------------------------------
        # GENERATE SALES FOR LAST 30 DAYS
        # -------------------------------------------------

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
            "Rahul",
            "Sneha",
            "Aman",
            "Neha",
            "Karan",
            "Riya",
            "Mohit",
            "Pooja"
        ]

        today = datetime.now().date()

        invoice_counter = 100

        for day_offset in range(29, -1, -1):

            sale_day = today - timedelta(
                days=day_offset
            )

            # 1-3 sales per day
            number_of_sales = 1 + (day_offset % 3)

            for n in range(number_of_sales):

                item = sales_pattern[
                    (day_offset + n)
                    % len(sales_pattern)
                ]

                product_name = item[0]
                qty = item[1]
                price = item[2]
                cost = item[3]

                # Reduce some demo quantity
                if day_offset % 7 == 0:
                    qty += 1

                total = qty * price
                profit = qty * (price - cost)

                invoice_counter += 1

                cur.execute("""
                    INSERT INTO sales(
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
                    f"SO-{invoice_counter}",
                    product_map[product_name],
                    product_name,
                    customers[
                        (day_offset+n)
                        % len(customers)
                    ],
                    qty,
                    price,
                    cost,
                    total,
                    profit,
                    sale_day.isoformat()
                ))

        # -------------------------------------------------
        # PURCHASES
        # -------------------------------------------------

        purchase_data = [
            ("iPhone 15", "Mobile World", 10, 52000),
            ("OnePlus 12", "Tech Zone", 15, 39000),
            ("Boat Airdopes 131", "Audio World", 30, 1200),
            ("LG 55 4K TV", "Home Appliances", 8, 46000),
            ("HP Pavilion 15", "NextGen Distributors", 6, 56000)
        ]

        for i, item in enumerate(purchase_data):

            product_name = item[0]
            supplier = item[1]
            qty = item[2]
            cost = item[3]

            cur.execute("""
                INSERT INTO purchases(
                    purchase_no,
                    product_id,
                    product_name,
                    supplier,
                    quantity,
                    unit_cost,
                    total,
                    purchase_date,
                    status
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
                (
                    today
                    -
                    timedelta(days=i+1)
                ).isoformat(),
                "Completed"
            ))

    conn.commit()
    conn.close()


initialize_database()


# =========================================================
# CSS
# =========================================================


st.markdown("""
<style>
/* Main application */
.stApp {
    background: #000000;
    color: #ffffff;
}

/* Main content area */
.block-container {
    max-width: 1450px;
    padding-top: 1.5rem;
    padding-bottom: 2rem;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: #111111;
    border-right: 1px solid #333333;
}

/* Sidebar text */
[data-testid="stSidebar"] * {
    color: #ffffff;
}

/* Metric cards */
div[data-testid="stMetric"] {
    background: #111111;
    border: 1px solid #333333;
    border-radius: 8px;
    padding: 14px;
}

div[data-testid="stMetricLabel"] {
    color: #cccccc !important;
}

div[data-testid="stMetricValue"] {
    color: #ffffff !important;
}

/* Buttons */
div.stButton > button {
    background: #222222;
    color: #ffffff;
    border: 1px solid #444444;
    border-radius: 6px;
}

div.stButton > button:hover {
    background: #333333;
    border-color: #777777;
    color: #ffffff;
}

/* Tables */
[data-testid="stDataFrame"] {
    border-radius: 8px;
}

/* Headings */
h1, h2, h3 {
    color: #ffffff;
    letter-spacing: normal;
}

/* Custom title and subtitle */
.ss-title {
    font-size: 28px;
    font-weight: 600;
}

.ss-subtitle {
    color: #bbbbbb;
    margin-bottom: 16px;
}

/* Alert boxes */
.alert-box {
    background: #111111;
    color: #ffffff;
    border: 1px solid #333333;
    padding: 14px;
    border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)



# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.markdown(
        "#  SmartStock AI"
    )

    st.caption(
        "Inventory Smarter • Grow Faster"
    )

    st.divider()

    page = st.radio(
        "Navigation",
        [
            " Dashboard",
            " Inventory",
            " Sales",
            " Purchases",
            " Suppliers",
            " Reports",
            " AI Assistant",
            " Alerts",
            " Settings"
        ],
        label_visibility="collapsed"
    )

    st.divider()

    st.markdown(
        "###  Quick Actions"
    )

    st.caption(
        "Manage your business from one place."
    )

    st.divider()

    st.caption(
        "SmartStock AI"
    )

    st.caption(
        "Phase 1 Prototype"
    )


# =========================================================
# COMMON DATA
# =========================================================

products = query_df(
    "SELECT * FROM products"
)

sales = query_df(
    "SELECT * FROM sales"
)

purchases = query_df(
    "SELECT * FROM purchases"
)


# =========================================================
# DASHBOARD
# =========================================================

def dashboard():


    st.title("Inventory Dashboard")
    st.caption("Overview of stock, sales, profit, and inventory alerts.")




    # -----------------------------------------------------
    # DATE SLIDER
    # -----------------------------------------------------

    sales["sale_date"] = pd.to_datetime(
        sales["sale_date"]
    )

    minimum_date = sales["sale_date"].min().date()
    maximum_date = sales["sale_date"].max().date()

    start_date, end_date = st.slider(
        "📅 Visualization Date Range",
        min_value=minimum_date,
        max_value=maximum_date,
        value=(minimum_date, maximum_date)
    )

    filtered = sales[
        (
            sales["sale_date"].dt.date
            >= start_date
        )
        &
        (
            sales["sale_date"].dt.date
            <= end_date
        )
    ].copy()

    # -----------------------------------------------------
    # KPI CARDS
    # -----------------------------------------------------

    total_stock = int(
        products["stock"].sum()
    )

    total_revenue = float(
        filtered["total"].sum()
    )

    total_profit = float(
        filtered["profit"].sum()
    )

    low_stock = int(
        (
            products["stock"]
            <=
            products["reorder_level"]
        ).sum()
    )

    out_stock = int(
        (
            products["stock"] <= 0
        ).sum()
    )

    c1,c2,c3,c4,c5 = st.columns(5)

    c1.metric(
        " Total Stock",
        f"{total_stock:,}"
    )

    c2.metric(
        " Sales",
        money(total_revenue)
    )

    c3.metric(
        "📈 Profit",
        money(total_profit)
    )

    c4.metric(
        "⚠️ Low Stock",
        low_stock
    )

    c5.metric(
        "🚨 Out of Stock",
        out_stock
    )

    st.markdown("")

    # =====================================================
    # MAIN VISUALIZATION
    # =====================================================

    col1, col2 = st.columns(
        [1.65, 1]
    )

    # -----------------------------------------------------
    # SALES TREND
    # -----------------------------------------------------

    with col1:

        st.markdown(
            "### 📈 Sales & Profit Trend"
        )

        trend = (
            filtered
            .groupby(
                "sale_date",
                as_index=False
            )
            .agg(
                Sales=("total","sum"),
                Profit=("profit","sum")
            )
        )

        if not trend.empty:

            fig = go.Figure()

            fig.add_trace(
                go.Scatter(
                    x=trend["sale_date"],
                    y=trend["Sales"],
                    mode="lines+markers",
                    name="Sales",
                    line=dict(
                        width=3
                    ),
                    marker=dict(
                        size=7
                    )
                )
            )

            fig.add_trace(
                go.Scatter(
                    x=trend["sale_date"],
                    y=trend["Profit"],
                    mode="lines+markers",
                    name="Profit",
                    line=dict(
                        width=3,
                        dash="dot"
                    ),
                    marker=dict(
                        size=6
                    )
                )
            )


            fig.update_layout(
                 template="plotly_white",
                 height=320,
                 margin=dict(
                     l=10,
                     r=10,
                     t=15,
                     b=10
                 ),
                 hovermode="x unified",
                 legend=dict(
                     orientation="h",
                     y=1.05
            ),
             xaxis_title="Date",
             yaxis_title="Amount (₹)"
            )


            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "displayModeBar": False
                }
            )

    # -----------------------------------------------------
    # CATEGORY DONUT
    # -----------------------------------------------------

    with col2:

        st.markdown(
            "### 🍩 Sales by Category"
        )

        category_sales = (
            filtered
            .merge(
                products[
                    ["id","category"]
                ],
                left_on="product_id",
                right_on="id"
            )
            .groupby(
                "category",
                as_index=False
            )["total"]
            .sum()
        )

        if not category_sales.empty:

            fig = px.pie(
                category_sales,
                names="category",
                values="total",
                hole=.62
            )

            fig.update_layout(
                template="plotly_dark",
                height=390,
                margin=dict(
                    l=10,
                    r=10,
                    t=20,
                    b=10
                ),
                legend=dict(
                    orientation="h"
                )
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "displayModeBar": False
                }
            )

    # =====================================================
    # SECOND ROW
    # =====================================================

    col3,col4 = st.columns(2)

    # -----------------------------------------------------
    # STOCK BY CATEGORY
    # -----------------------------------------------------

    with col3:

        st.markdown(
            "###  Stock by Category"
        )

        stock_category = (
            products
            .groupby(
                "category",
                as_index=False
            )["stock"]
            .sum()
            .sort_values(
                "stock",
                ascending=True
            )
        )

        fig = px.bar(
            stock_category,
            x="stock",
            y="category",
            orientation="h",
            text="stock"
        )

        fig.update_layout(
            template="plotly_dark",
            height=370,
            margin=dict(
                l=10,
                r=10,
                t=20,
                b=10
            ),
            xaxis_title="Units",
            yaxis_title=""
        )

        fig.update_traces(
            textposition="outside"
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displayModeBar": False
            }
        )

    # -----------------------------------------------------
    # REVENUE VS PROFIT
    # -----------------------------------------------------

    with col4:

        st.markdown(
            "### 💹 Revenue vs Profit"
        )

        compare = (
            filtered
            .groupby(
                "sale_date",
                as_index=False
            )
            .agg(
                Revenue=("total","sum"),
                Profit=("profit","sum")
            )
        )

        fig = px.bar(
            compare,
            x="sale_date",
            y=[
                "Revenue",
                "Profit"
            ],
            barmode="group"
        )

        fig.update_layout(
            template="plotly_dark",
            height=370,
            margin=dict(
                l=10,
                r=10,
                t=20,
                b=10
            ),
            xaxis_title="Date",
            yaxis_title="Amount (₹)",
            legend_title=""
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displayModeBar": False
            }
        )

    # =====================================================
    # THIRD ROW
    # =====================================================

    col5,col6 = st.columns(
        [1.25,1]
    )

    # -----------------------------------------------------
    # TOP PRODUCTS
    # -----------------------------------------------------

    with col5:

        st.markdown(
            "### 🏆 Top Selling Products"
        )

        top = (
            filtered
            .groupby(
                "product_name",
                as_index=False
            )["quantity"]
            .sum()
            .sort_values(
                "quantity",
                ascending=False
            )
            .head(7)
        )

        if not top.empty:

            fig = px.bar(
                top,
                x="quantity",
                y="product_name",
                orientation="h",
                text="quantity"
            )

            fig.update_layout(
                template="plotly_dark",
                height=350,
                margin=dict(
                    l=10,
                    r=10,
                    t=20,
                    b=10
                ),
                xaxis_title="Units Sold",
                yaxis_title=""
            )

            fig.update_traces(
                textposition="outside"
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "displayModeBar": False
                }
            )

    # -----------------------------------------------------
    # LOW STOCK
    # -----------------------------------------------------

    with col6:

        st.markdown(
            "### ⚠️ Inventory Health"
        )

        healthy = int(
            (
                products["stock"]
                >
                products["reorder_level"]
            ).sum()
        )

        low = int(
            (
                (
                    products["stock"]
                    <=
                    products["reorder_level"]
                )
                &
                (
                    products["stock"] > 0
                )
            ).sum()
        )

        out = int(
            (
                products["stock"] <= 0
            ).sum()
        )

        health_df = pd.DataFrame({
            "Status": [
                "Healthy",
                "Low Stock",
                "Out of Stock"
            ],
            "Products": [
                healthy,
                low,
                out
            ]
        })

        fig = px.pie(
            health_df,
            names="Status",
            values="Products",
            hole=.58
        )

        fig.update_layout(
            template="plotly_dark",
            height=350,
            margin=dict(
                l=10,
                r=10,
                t=20,
                b=10
            )
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displayModeBar": False
            }
        )

    # =====================================================
    # LOW STOCK TABLE
    # =====================================================

    st.markdown(
        "### 🚨 Products Requiring Attention"
    )

    attention = products[
        products["stock"]
        <=
        products["reorder_level"]
    ][
        [
            "name",
            "category",
            "stock",
            "reorder_level",
            "selling_price"
        ]
    ].copy()

    attention.columns = [
        "Product",
        "Category",
        "Stock",
        "Reorder Level",
        "Selling Price"
    ]

    if attention.empty:

        st.success(
            "All inventory levels look healthy."
        )

    else:

        st.dataframe(
            attention,
            use_container_width=True,
            hide_index=True
        )

    # =====================================================
    # RECENT SALES
    # =====================================================

    st.markdown(
        "### 🧾 Recent Transactions"
    )

    recent = (
        filtered
        .sort_values(
            "sale_date",
            ascending=False
        )
        .head(8)
        .copy()
    )

    recent["sale_date"] = (
        recent["sale_date"]
        .dt.strftime("%d %b %Y")
    )

    recent = recent[
        [
            "invoice_no",
            "product_name",
            "customer",
            "quantity",
            "total",
            "profit",
            "sale_date"
        ]
    ]

    recent.columns = [
        "Invoice",
        "Product",
        "Customer",
        "Qty",
        "Amount",
        "Profit",
        "Date"
    ]

    st.dataframe(
        recent,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# INVENTORY
# =========================================================

def inventory_page():

    st.markdown("#  Inventory")

    tab1,tab2,tab3 = st.tabs(
        [
            "📋 Products",
            "➕ Add Product",
            "✏️ Edit Product"
        ]
    )

    current = query_df(
        "SELECT * FROM products ORDER BY id DESC"
    )

    # -----------------------------------------------------
    # PRODUCT LIST
    # -----------------------------------------------------

    with tab1:

        search = st.text_input(
            "🔎 Search product"
        )

        display = current.copy()

        if search:

            mask = (
                display["name"]
                .str.contains(
                    search,
                    case=False,
                    na=False
                )
                |
                display["brand"]
                .str.contains(
                    search,
                    case=False,
                    na=False
                )
                |
                display["category"]
                .str.contains(
                    search,
                    case=False,
                    na=False
                )
            )

            display = display[mask]

        st.dataframe(
            display[
                [
                    "sku",
                    "name",
                    "brand",
                    "category",
                    "purchase_price",
                    "selling_price",
                    "stock",
                    "reorder_level",
                    "supplier"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

        if not display.empty:

            delete_name = st.selectbox(
                "Select product to delete",
                display["name"].tolist()
            )

            if st.button(
                "🗑️ Delete Product"
            ):

                execute(
                    "DELETE FROM products WHERE name=?",
                    (delete_name,)
                )

                st.success(
                    "Product deleted."
                )

                st.rerun()

    # -----------------------------------------------------
    # ADD PRODUCT
    # -----------------------------------------------------

    with tab2:

        with st.form(
            "add_product"
        ):

            c1,c2,c3 = st.columns(3)

            name = c1.text_input(
                "Product Name"
            )

            brand = c2.text_input(
                "Brand"
            )

            category = c3.text_input(
                "Category"
            )

            c1,c2,c3 = st.columns(3)

            purchase_price = c1.number_input(
                "Purchase Price",
                min_value=0.0,
                step=100.0
            )

            selling_price = c2.number_input(
                "Selling Price",
                min_value=0.0,
                step=100.0
            )

            stock = c3.number_input(
                "Opening Stock",
                min_value=0,
                step=1
            )

            c1,c2,c3 = st.columns(3)

            reorder = c1.number_input(
                "Reorder Level",
                min_value=0,
                value=5
            )

            supplier = c2.text_input(
                "Supplier"
            )

            sku = c3.text_input(
                "SKU"
            )

            submit = st.form_submit_button(
                "➕ Add Product"
            )

        if submit:

            if not name:

                st.error(
                    "Product name is required."
                )

            else:

                if not sku:

                    sku = (
                        "SKU-"
                        +
                        datetime.now().strftime(
                            "%H%M%S"
                        )
                    )

                try:

                    execute("""
                        INSERT INTO products(
                            sku,name,brand,category,
                            purchase_price,selling_price,
                            stock,reorder_level,supplier
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
                        reorder,
                        supplier
                    ))

                    st.success(
                        "Product added successfully."
                    )

                    st.rerun()

                except sqlite3.IntegrityError:

                    st.error(
                        "SKU already exists."
                    )

    # -----------------------------------------------------
    # EDIT
    # -----------------------------------------------------

    with tab3:

        if current.empty:

            st.info(
                "No products."
            )

        else:

            selected = st.selectbox(
                "Product",
                current["name"].tolist()
            )

            row = current[
                current["name"] == selected
            ].iloc[0]

            with st.form(
                "edit_product"
            ):

                new_name = st.text_input(
                    "Name",
                    value=row["name"]
                )

                new_price = st.number_input(
                    "Selling Price",
                    min_value=0.0,
                    value=float(
                        row["selling_price"]
                    ),
                    step=100.0
                )

                new_stock = st.number_input(
                    "Stock",
                    min_value=0,
                    value=int(
                        row["stock"]
                    )
                )

                save = st.form_submit_button(
                    "💾 Save Changes"
                )

            if save:

                old_price = float(
                    row["selling_price"]
                )

                if new_price != old_price:

                    execute("""
                        INSERT INTO price_history(
                            product_id,
                            old_price,
                            new_price,
                            changed_at
                        )
                        VALUES(?,?,?,?)
                    """, (
                        row["id"],
                        old_price,
                        new_price,
                        datetime.now().isoformat()
                    ))

                execute("""
                    UPDATE products
                    SET
                        name=?,
                        selling_price=?,
                        stock=?,
                        updated_at=?
                    WHERE id=?
                """, (
                    new_name,
                    new_price,
                    new_stock,
                    datetime.now().isoformat(),
                    row["id"]
                ))

                st.success(
                    "Product updated."
                )

                st.rerun()


# =========================================================
# SALES
# =========================================================

def sales_page():

    st.markdown("#  Sales Management")

    product_data = query_df(
        "SELECT * FROM products ORDER BY name"
    )

    tab1,tab2 = st.tabs(
        [
            "➕ New Sale",
            "📜 Sales History"
        ]
    )

    with tab1:

        with st.form(
            "new_sale"
        ):

            product_name = st.selectbox(
                "Product",
                product_data["name"].tolist()
            )

            product = product_data[
                product_data["name"]
                ==
                product_name
            ].iloc[0]

            customer = st.text_input(
                "Customer"
            )

            quantity = st.number_input(
                "Quantity",
                min_value=1,
                max_value=max(
                    1,
                    int(product["stock"])
                ),
                value=1
            )

            st.info(
                f"Selling Price: "
                f"{money(product['selling_price'])} | "
                f"Available: "
                f"{product['stock']}"
            )

            submit = st.form_submit_button(
                "✅ Complete Sale"
            )

        if submit:

            total = (
                quantity
                *
                product["selling_price"]
            )

            profit = quantity * (
                product["selling_price"]
                -
                product["purchase_price"]
            )

            invoice = (
                "SO-"
                +
                datetime.now().strftime(
                    "%Y%m%d%H%M%S"
                )
            )

            execute("""
                INSERT INTO sales(
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

            execute("""
                UPDATE products
                SET stock=stock-?
                WHERE id=?
            """, (
                quantity,
                product["id"]
            ))

            st.success(
                f"Sale completed: {invoice}"
            )

            st.rerun()

    with tab2:

        history = query_df("""
            SELECT *
            FROM sales
            ORDER BY id DESC
        """)

        st.dataframe(
            history,
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# PURCHASES
# =========================================================

def purchases_page():

    st.markdown("#  Purchases")

    product_data = query_df(
        "SELECT * FROM products ORDER BY name"
    )

    suppliers_data = query_df(
        "SELECT * FROM suppliers ORDER BY name"
    )

    tab1,tab2 = st.tabs(
        [
            "➕ New Purchase",
            "📜 Purchase History"
        ]
    )

    with tab1:

        with st.form(
            "purchase_form"
        ):

            product_name = st.selectbox(
                "Product",
                product_data["name"].tolist()
            )

            product = product_data[
                product_data["name"]
                ==
                product_name
            ].iloc[0]

            supplier = st.selectbox(
                "Supplier",
                suppliers_data["name"].tolist()
            )

            quantity = st.number_input(
                "Quantity",
                min_value=1,
                value=1
            )

            unit_cost = st.number_input(
                "Unit Cost",
                min_value=0.0,
                value=float(
                    product["purchase_price"]
                ),
                step=100.0
            )

            submit = st.form_submit_button(
                "📥 Complete Purchase"
            )

        if submit:

            total = quantity * unit_cost

            purchase_no = (
                "PO-"
                +
                datetime.now().strftime(
                    "%Y%m%d%H%M%S"
                )
            )

            execute("""
                INSERT INTO purchases(
                    purchase_no,
                    product_id,
                    product_name,
                    supplier,
                    quantity,
                    unit_cost,
                    total,
                    purchase_date,
                    status
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

            execute("""
                UPDATE products
                SET stock=stock+?
                WHERE id=?
            """, (
                quantity,
                product["id"]
            ))

            st.success(
                "Purchase completed."
            )

            st.rerun()

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

    st.markdown("#  Suppliers")

    data = query_df(
        "SELECT * FROM suppliers ORDER BY name"
    )

    st.dataframe(
        data,
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    with st.expander(
        "➕ Add Supplier"
    ):

        with st.form(
            "supplier_form"
        ):

            name = st.text_input(
                "Supplier Name"
            )

            phone = st.text_input(
                "Phone"
            )

            email = st.text_input(
                "Email"
            )

            address = st.text_input(
                "Address"
            )

            submit = st.form_submit_button(
                "Add Supplier"
            )

        if submit:

            try:

                execute("""
                    INSERT INTO suppliers(
                        name,phone,email,address
                    )
                    VALUES(?,?,?,?)
                """, (
                    name,
                    phone,
                    email,
                    address
                ))

                st.success(
                    "Supplier added."
                )

                st.rerun()

            except sqlite3.IntegrityError:

                st.error(
                    "Supplier already exists."
                )


# =========================================================
# REPORTS
# =========================================================

def reports_page():

    st.markdown("#  Reports & Analytics")

    data = query_df(
        "SELECT * FROM sales"
    )

    data["sale_date"] = pd.to_datetime(
        data["sale_date"]
    )

    start,end = st.date_input(
        "Select Report Period",
        value=(
            data["sale_date"].min().date(),
            data["sale_date"].max().date()
        )
    )

    selected = data[
        (
            data["sale_date"].dt.date
            >= start
        )
        &
        (
            data["sale_date"].dt.date
            <= end
        )
    ]

    revenue = selected["total"].sum()
    profit = selected["profit"].sum()
    units = selected["quantity"].sum()

    c1,c2,c3 = st.columns(3)

    c1.metric(
        "Revenue",
        money(revenue)
    )

    c2.metric(
        "Profit",
        money(profit)
    )

    c3.metric(
        "Units Sold",
        f"{units:,}"
    )

    trend = (
        selected
        .groupby(
            "sale_date",
            as_index=False
        )
        .agg(
            Revenue=("total","sum"),
            Profit=("profit","sum")
        )
    )

    fig = px.line(
        trend,
        x="sale_date",
        y=[
            "Revenue",
            "Profit"
        ],
        markers=True
    )

    fig.update_layout(
        template="plotly_dark",
        height=420
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    st.download_button(
        "📥 Download Sales CSV",
        selected.to_csv(
            index=False
        ),
        file_name="smartstock_sales.csv",
        mime="text/csv"
    )


# =========================================================
# AI ASSISTANT
# =========================================================

def process_ai(command):

    command = command.lower().strip()

    data = query_df(
        "SELECT * FROM products"
    )

    # -----------------------------------------------------
    # TOTAL STOCK
    # -----------------------------------------------------

    if "total stock" in command:

        total = data["stock"].sum()

        return (
            f" Current total stock is "
            f"{int(total):,} units."
        )

    # -----------------------------------------------------
    # PROFIT
    # -----------------------------------------------------

    if "profit" in command:

        sales_data = query_df(
            "SELECT * FROM sales"
        )

        profit = sales_data["profit"].sum()

        return (
            f"📈 Total recorded profit is "
            f"{money(profit)}."
        )

    # -----------------------------------------------------
    # SALES
    # -----------------------------------------------------

    if "sales" in command:

        sales_data = query_df(
            "SELECT * FROM sales"
        )

        revenue = sales_data["total"].sum()

        return (
            f" Total recorded sales are "
            f"{money(revenue)}."
        )

    # -----------------------------------------------------
    # LOW STOCK
    # -----------------------------------------------------

    if "low stock" in command:

        low = data[
            data["stock"]
            <=
            data["reorder_level"]
        ]

        if low.empty:

            return (
                "✅ No low-stock products."
            )

        names = [
            f"{row['name']} ({row['stock']})"
            for _,row in low.iterrows()
        ]

        return (
            "⚠️ Low stock:\n\n"
            +
            "\n".join(names)
        )

    # -----------------------------------------------------
    # OUT OF STOCK
    # -----------------------------------------------------

    if "out of stock" in command:

        out = data[
            data["stock"] <= 0
        ]

        if out.empty:

            return (
                "✅ No products are out of stock."
            )

        return (
            "🚨 Out of stock:\n\n"
            +
            "\n".join(
                out["name"].tolist()
            )
        )

    # -----------------------------------------------------
    # TOP SELLING
    # -----------------------------------------------------

    if (
        "top selling" in command
        or
        "best selling" in command
    ):

        sales_data = query_df(
            "SELECT * FROM sales"
        )

        top = (
            sales_data
            .groupby(
                "product_name"
            )["quantity"]
            .sum()
            .sort_values(
                ascending=False
            )
            .head(5)
        )

        return (
            "🏆 Top selling products:\n\n"
            +
            "\n".join(
                [
                    f"{name} — {qty} units"
                    for name,qty
                    in top.items()
                ]
            )
        )

    # -----------------------------------------------------
    # ADD STOCK
    # -----------------------------------------------------

    match = re.search(
        r"(?:add|increase)\s+(\d+)\s+(?:pieces?|units?).*?(.+)",
        command
    )

    if match:

        qty = int(
            match.group(1)
        )

        product_text = (
            match.group(2)
            .replace("of","")
            .strip()
        )

        found = data[
            data["name"]
            .str.lower()
            .str.contains(
                product_text,
                na=False
            )
        ]

        if not found.empty:

            row = found.iloc[0]

            execute("""
                UPDATE products
                SET stock=stock+?
                WHERE id=?
            """, (
                qty,
                row["id"]
            ))

            return (
                f"✅ Added {qty} units "
                f"to {row['name']}."
            )

    return (
        " I can understand commands like:\n\n"
        "• Show total stock\n"
        "• Show sales\n"
        "• Show profit\n"
        "• Show low stock\n"
        "• Show out of stock\n"
        "• Show top selling products\n"
        "• Add 20 pieces of OnePlus Buds"
    )


def ai_page():

    st.markdown(
        "#  SmartStock AI Assistant"
    )

    st.caption(
        "Use natural-language commands to interact with inventory."
    )

    st.success(
        "🟢 AI Assistant Online"
    )

    st.markdown(
        "### Example Commands"
    )

    examples = [
        "Show total stock",
        "Show sales",
        "Show profit",
        "Show low stock",
        "Show top selling products",
        "Add 20 pieces of OnePlus Buds"
    ]

    for example in examples:

        st.code(
            example,
            language="text"
        )

    command = st.text_input(
        "Enter your command"
    )

    if st.button(
        "🚀 Run Command",
        type="primary"
    ):

        if command:

            result = process_ai(
                command
            )

            st.info(
                result
            )


# =========================================================
# ALERTS
# =========================================================

def alerts_page():

    st.markdown(
        "#  Inventory Alerts"
    )

    data = query_df(
        "SELECT * FROM products"
    )

    low = data[
        data["stock"]
        <=
        data["reorder_level"]
    ]

    out = data[
        data["stock"] <= 0
    ]

    c1,c2 = st.columns(2)

    with c1:

        st.markdown(
            "### ⚠️ Low Stock"
        )

        if low.empty:

            st.success(
                "No low-stock products."
            )

        else:

            for _,row in low.iterrows():

                st.warning(
                    f"{row['name']} — "
                    f"{row['stock']} units"
                )

    with c2:

        st.markdown(
            "### 🚨 Out of Stock"
        )

        if out.empty:

            st.success(
                "No out-of-stock products."
            )

        else:

            for _,row in out.iterrows():

                st.error(
                    row["name"]
                )


# =========================================================
# SETTINGS
# =========================================================

def settings_page():

    st.markdown(
        "#  Settings"
    )

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
- Natural-language prototype

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
# ROUTER
# =========================================================

if page == " Dashboard":

    dashboard()

elif page == " Inventory":

    inventory_page()

elif page == " Sales":

    sales_page()

elif page == " Purchases":

    purchases_page()

elif page == " Suppliers":

    suppliers_page()

elif page == " Reports":

    reports_page()

elif page == " AI Assistant":

    ai_page()

elif page == " Alerts":

    alerts_page()

elif page == " Settings":
    settings_page()
