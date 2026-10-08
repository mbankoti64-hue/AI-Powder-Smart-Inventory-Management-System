import streamlit as st
import sqlite3


# =========================
# DATABASE INITIALIZATION
# =========================

def init_db():
    conn = sqlite3.connect("inventory.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            brand TEXT,
            category TEXT,
            purchase_price REAL,
            selling_price REAL,
            stock INTEGER
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================
# PAGE CONFIGURATION
# =========================

st.set_page_config(
    page_title="AI-Powered Smart Inventory",
    page_icon="📦",
    layout="wide"
)


# =========================
# TITLE
# =========================

st.title("📦 AI-Powered Smart Inventory Management System")

st.write(
    "Welcome to the AI-powered inventory management system."
)


# =========================
# DASHBOARD METRICS
# =========================

conn = sqlite3.connect("inventory.db")
cursor = conn.cursor()

# Total number of different products
cursor.execute("SELECT COUNT(*) FROM products")
total_products = cursor.fetchone()[0]

# Total stock
cursor.execute("SELECT COALESCE(SUM(stock), 0) FROM products")
total_stock = cursor.fetchone()[0]

conn.close()


col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Products", total_products)

with col2:
    st.metric("Total Stock", total_stock)

with col3:
    st.metric("Today's Sales", "₹0")

with col4:
    st.metric("Today's Profit", "₹0")


st.divider()


# =========================
# INVENTORY OVERVIEW
# =========================

st.subheader("📊 Inventory Overview")

st.info(
    "Inventory data will appear here once products are added."
)

st.divider()


# =========================
# ADD PRODUCT
# =========================

st.subheader("📦 Add Product")

with st.form("product_form"):

    product_name = st.text_input("Product Name")

    brand = st.text_input("Brand")

    category = st.selectbox(
        "Category",
        [
            "Electronics",
            "Grocery",
            "Clothing",
            "Stationery",
            "Other"
        ]
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        purchase_price = st.number_input(
            "Purchase Price (₹)",
            min_value=0.0,
            step=1.0
        )

    with col2:
        selling_price = st.number_input(
            "Selling Price (₹)",
            min_value=0.0,
            step=1.0
        )

    with col3:
        stock = st.number_input(
            "Stock Quantity",
            min_value=0,
            step=1
        )

    # =========================
    # ADD PRODUCT BUTTON
    # =========================

    submitted = st.form_submit_button("➕ Add Product")

    if submitted:

        # Check product name
        if product_name.strip() == "":
            st.error("Please enter a product name.")

        else:

            # Connect to database
            conn = sqlite3.connect("inventory.db")
            cursor = conn.cursor()

            # Insert product
            cursor.execute("""
                INSERT INTO products
                (
                    product_name,
                    brand,
                    category,
                    purchase_price,
                    selling_price,
                    stock
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                product_name,
                brand,
                category,
                purchase_price,
                selling_price,
                stock
            ))

            # Save changes
            conn.commit()

            # Close database
            conn.close()

            # Success message
            st.success(
                f"✅ {product_name} added successfully!"
            )

            st.divider()


# =========================
# CURRENT INVENTORY
# =========================

st.subheader("📦 Current Inventory")


# Connect to database
conn = sqlite3.connect("inventory.db")
cursor = conn.cursor()


# Get all products
cursor.execute("""
    SELECT
        product_name,
        brand,
        category,
        purchase_price,
        selling_price,
        stock
    FROM products
""")


products = cursor.fetchall()


# Close database
conn.close()


# =========================
# DISPLAY PRODUCTS
# =========================

if products:

    for product in products:

        (
            product_name,
            brand,
            category,
            purchase_price,
            selling_price,
            stock
        ) = product

        st.write(
            f"**{product_name}** | "
            f"Brand: {brand} | "
            f"Category: {category} | "
            f"Purchase: ₹{purchase_price:.2f} | "
            f"Selling: ₹{selling_price:.2f} | "
            f"Stock: {stock}"
        )

else:

    st.info("No products added yet.")
    
    
    # =========================
# UPDATE PRODUCT
# =========================

st.divider()

st.subheader("✏️ Update Product")

conn = sqlite3.connect("inventory.db")
cursor = conn.cursor()

cursor.execute("""
    SELECT id, product_name
    FROM products
    ORDER BY product_name
""")

product_options = cursor.fetchall()
conn.close()

if product_options:

    product_dict = {
        f"{product[1]} (ID: {product[0]})": product[0]
        for product in product_options
    }

    selected_product = st.selectbox(
        "Select Product",
        list(product_dict.keys())
    )

    selected_id = product_dict[selected_product]

    conn = sqlite3.connect("inventory.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT product_name, brand, category,
               purchase_price, selling_price, stock
        FROM products
        WHERE id = ?
    """, (selected_id,))

    product_data = cursor.fetchone()
    conn.close()

    if product_data:

        (
            old_name,
            old_brand,
            old_category,
            old_purchase_price,
            old_selling_price,
            old_stock
        ) = product_data

        new_name = st.text_input(
            "Product Name",
            value=old_name
        )

        new_brand = st.text_input(
            "Brand",
            value=old_brand or ""
        )

        categories = [
            "Electronics",
            "Grocery",
            "Clothing",
            "Stationery",
            "Other"
        ]

        category_index = (
            categories.index(old_category)
            if old_category in categories
            else 0
        )

        new_category = st.selectbox(
            "Category",
            categories,
            index=category_index
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            new_purchase_price = st.number_input(
                "Purchase Price (₹)",
                min_value=0.0,
                value=float(old_purchase_price)
            )

        with col2:
            new_selling_price = st.number_input(
                "Selling Price (₹)",
                min_value=0.0,
                value=float(old_selling_price)
            )

        with col3:
            new_stock = st.number_input(
                "Stock Quantity",
                min_value=0,
                value=int(old_stock)
            )

        if st.button("💾 Save Changes"):

            conn = sqlite3.connect("inventory.db")
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE products
                SET product_name = ?,
                    brand = ?,
                    category = ?,
                    purchase_price = ?,
                    selling_price = ?,
                    stock = ?
                WHERE id = ?
            """, (
                new_name,
                new_brand,
                new_category,
                new_purchase_price,
                new_selling_price,
                new_stock,
                selected_id
            ))

            conn.commit()
            conn.close()

            st.success(
                f"✅ {new_name} updated successfully!"
            )

            st.rerun()

else:
    st.info("No products available to update.")
