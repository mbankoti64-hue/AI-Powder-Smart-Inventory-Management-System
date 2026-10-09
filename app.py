import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
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


# =========================================================
# DATABASE HELPERS
# =========================================================

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


# =========================================================
# CSS DESIGN
# =========================================================

st.markdown("""
<style>
.stApp {
    background: #000000;
    color: #ffffff;
}
.block-container {
    max-width: 1450px;
    padding-top: 1.5rem;
    padding-bottom: 2rem;
}
[data-testid="stSidebar"] {
    background: #111111;
    border-right: 1px solid #333333;
}
[data-testid="stSidebar"] * {
    color: #ffffff;
}
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
h1, h2, h3 {
    color: #ffffff;
}
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
# SIDEBAR NAVIGATION
# =========================================================

with st.sidebar:

    st.markdown("# 📦 SmartStock AI")
    st.caption("Inventory Smarter • Grow Faster")
    st.divider()

    page = st.radio(
        "Navigation",
        [
            " Dashboard",
            " Inventory",
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
    st.caption("Manage your business from one place.")
    st.divider()
    st.caption("SmartStock AI")
    st.caption("Phase 1 Prototype")


# =========================================================
# DASHBOARD
# =========================================================

def dashboard():

    st.title("Inventory Dashboard")
    st.caption("Overview of stock, sales, profit, and alerts.")

    products = query_df("SELECT * FROM products")
    sales = query_df("SELECT * FROM sales")

    if sales.empty:
        st.info("No sales data available.")
        return

    sales["sale_date"] = pd.to_datetime(sales["sale_date"])

    minimum_date = sales["sale_date"].min().date()
    maximum_date = sales["sale_date"].max().date()

    date_range = st.date_input(
        "📅 Visualization Date Range",
        value=(minimum_date, maximum_date)
    )

    if not isinstance(date_range, tuple) or len(date_range) != 2:
        st.info("Select a start date and an end date.")
        return

    start_date, end_date = date_range

    filtered = sales[
        (sales["sale_date"].dt.date >= start_date) &
        (sales["sale_date"].dt.date <= end_date)
    ].copy()

    total_stock = int(products["stock"].sum())
    total_revenue = filtered["total"].sum()
    total_profit = filtered["profit"].sum()

    low_stock = int(
        (products["stock"] <= products["reorder_level"]).sum()
    )

    out_stock = int((products["stock"] <= 0).sum())

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("📦 Total Stock", f"{total_stock:,}")
    c2.metric("💰 Sales", money(total_revenue))
    c3.metric("📈 Profit", money(total_profit))
    c4.metric("⚠️ Low Stock", low_stock)
    c5.metric("🚨 Out of Stock", out_stock)

    col1, col2 = st.columns([1.65, 1])

    with col1:

        st.markdown("### 📈 Sales & Profit Trend")

        trend = (
            filtered.groupby("sale_date", as_index=False)
            .agg(
                Sales=("total", "sum"),
                Profit=("profit", "sum")
            )
        )

        if not trend.empty:

            fig = go.Figure()

            fig.add_trace(go.Scatter(
                x=trend["sale_date"],
                y=trend["Sales"],
                mode="lines+markers",
                name="Sales"
            ))

            fig.add_trace(go.Scatter(
                x=trend["sale_date"],
                y=trend["Profit"],
                mode="lines+markers",
                name="Profit"
            ))

            fig.update_layout(
                template="plotly_dark",
                height=390,
                hovermode="x unified"
            )

            st.plotly_chart(fig, use_container_width=True)

    with col2:

        st.markdown("### 🍩 Sales by Category")

        category_sales = (
            filtered.merge(
                products[["id", "category"]],
                left_on="product_id",
                right_on="id",
                how="left"
            )
            .groupby("category", as_index=False)["total"]
            .sum()
        )

        if not category_sales.empty:

            fig = px.pie(
                category_sales,
                names="category",
                values="total",
                hole=0.6
            )

            fig.update_layout(
                template="plotly_dark",
                height=390
            )

            st.plotly_chart(fig, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:

        st.markdown("### 📦 Stock by Category")

        stock_category = (
            products.groupby("category", as_index=False)["stock"]
            .sum()
            .sort_values("stock")
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
            height=370
        )

        st.plotly_chart(fig, use_container_width=True)

    with col4:

        st.markdown("### 💹 Revenue vs Profit")

        compare = (
            filtered.groupby("sale_date", as_index=False)
            .agg(
                Revenue=("total", "sum"),
                Profit=("profit", "sum")
            )
        )

        fig = px.bar(
            compare,
            x="sale_date",
            y=["Revenue", "Profit"],
            barmode="group"
        )

        fig.update_layout(
            template="plotly_dark",
            height=370
        )

        st.plotly_chart(fig, use_container_width=True)

    col5, col6 = st.columns(2)

    with col5:

        st.markdown("### 🏆 Top Selling Products")

        top = (
            filtered.groupby("product_name", as_index=False)["quantity"]
            .sum()
            .sort_values("quantity", ascending=False)
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
                height=350
            )

            st.plotly_chart(fig, use_container_width=True)

    with col6:

        st.markdown("### ⚠️ Inventory Health")

        healthy = int(
            (products["stock"] > products["reorder_level"]).sum()
        )

        st.metric("Healthy Products", healthy)
        st.metric("Low Stock Products", low_stock)
        st.metric("Out of Stock Products", out_stock)


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

    command = st.text_input("Enter your command")

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


