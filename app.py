import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import datetime as dt
import plotly.express as px
import re

DB_FILE = "finance_db.db"

# ---------------- Database Setup ----------------
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        password TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        type TEXT,
                        category TEXT,
                        amount REAL,
                        date TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS budgets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        category TEXT,
                        amount REAL,
                        month INTEGER,
                        year INTEGER)""")
        conn.commit()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ---------------- User Management ----------------
def validate_password(password: str) -> str:
    """Validate password strength. Return error message if invalid, else empty string."""
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter."
    return ""

def register_user(username, password):
    pwd_error = validate_password(password)
    if pwd_error:
        return False, pwd_error

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                      (username, hash_password(password)))
            conn.commit()
            return True, "Account created successfully."
        except sqlite3.IntegrityError:
            return False, "Username already exists."

def login_user(username, password):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", 
                  (username, hash_password(password)))
        return c.fetchone()

# ---------------- Data Management ----------------
def add_entry(user_id, etype, category, amount, date):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO entries (user_id, type, category, amount, date) VALUES (?, ?, ?, ?, ?)", 
                  (user_id, etype, category, amount, date))
        conn.commit()

def set_budget(user_id, category, amount, month, year):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM budgets WHERE user_id=? AND category=? AND month=? AND year=?", 
                  (user_id, category, month, year))
        if c.fetchone():
            c.execute("UPDATE budgets SET amount=? WHERE user_id=? AND category=? AND month=? AND year=?", 
                      (amount, user_id, category, month, year))
        else:
            c.execute("INSERT INTO budgets (user_id, category, amount, month, year) VALUES (?, ?, ?, ?, ?)", 
                      (user_id, category, amount, month, year))
        conn.commit()

def get_entries_df(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query("SELECT * FROM entries WHERE user_id=?", conn, params=(user_id,))
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df

def get_budgets(user_id, year, month):
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql_query("SELECT * FROM budgets WHERE user_id=? AND year=? AND month=?", 
                                 conn, params=(user_id, year, month))

# ---------------- Budget Notifications ----------------
def check_budget_notifications(user_id, year, month):
    budgets = get_budgets(user_id, year, month)
    if budgets.empty:
        return []

    df = get_entries_df(user_id)
    spent = df[(df['type']=='expense') & 
               (df['date'].dt.year==year) & 
               (df['date'].dt.month==month)].groupby('category')['amount'].sum()

    notifications = []
    for _, row in budgets.iterrows():
        used = spent.get(row['category'], 0)
        if row['amount'] > 0:
            pct = used / row['amount']
            if pct >= 1.0:
                notifications.append(f"❌ Budget EXCEEDED for {row['category']}! "
                                     f"Spent ₹{used:.2f} of ₹{row['amount']:.2f}")
            elif pct >= 0.75:
                notifications.append(f"🚨 Budget almost used for {row['category']} "
                                     f"(₹{used:.2f}/₹{row['amount']:.2f})")
            elif pct >= 0.5:
                notifications.append(f"🔥 Warning: {row['category']} at {pct*100:.0f}% "
                                     f"(₹{used:.2f}/₹{row['amount']:.2f})")
            elif pct >= 0.25:
                notifications.append(f"⚠ Early alert: {row['category']} at {pct*100:.0f}% "
                                     f"(₹{used:.2f}/₹{row['amount']:.2f})")
    return notifications

# ---------------- Streamlit UI ----------------
st.set_page_config(page_title="Personal Finance Tracker", layout="wide")
init_db()

menu = ["Login", "Register"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Register":
    st.subheader("Create New Account")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Register"):
        success, msg = register_user(username, password)
        if success:
            st.success(msg)
        else:
            st.error(msg)

elif choice == "Login":
    st.subheader("Login to Your Account")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        user = login_user(username, password)
        if user:
            st.session_state['user'] = user
            st.success(f"Welcome {username}")
        else:
            st.error("Invalid username or password.")

# ---------------- Dashboard ----------------
if "user" in st.session_state:
    user = st.session_state['user']
    uid = user[0]
    today = dt.date.today()

    st.title("📊 Personal Finance Dashboard")

    # Predefined categories
    categories = ["Food", "Transport", "Shopping", "Bills", "Entertainment", "Health", "Salary", "Other"]

    # Add Entry
    st.subheader("➕ Add Income/Expense")
    etype = st.radio("Type", ["income", "expense"])
    category = st.selectbox("Category", categories)
    amount = st.number_input("Amount", min_value=0.0, step=100.0)
    date = st.date_input("Date", today)

    if st.button("Add Entry"):
        add_entry(uid, etype, category, amount, str(date))
        st.success("Entry added successfully!")
        # 🔔 Instant budget check
        alerts = check_budget_notifications(uid, today.year, today.month)
        if alerts:
            for alert in alerts:
                st.toast(alert)

    # Set Budget
    st.subheader("💰 Set Monthly Budget")
    b_category = st.selectbox("Budget Category", categories, key="budget_cat")
    b_amount = st.number_input("Budget Amount", min_value=0.0, step=100.0)
    if st.button("Set Budget"):
        set_budget(uid, b_category, b_amount, today.month, today.year)
        st.success("Budget set successfully!")

    # Data
    df = get_entries_df(uid)
    st.subheader("📒 All Entries")
    st.dataframe(df)

    # Analytics
    if not df.empty:
        st.subheader("📈 Expense Analytics")
        exp_df = df[df['type'] == 'expense']
        if not exp_df.empty:
            col1, col2 = st.columns(2)
            with col1:
                pie = px.pie(exp_df, values='amount', names='category', title="Expenses by Category")
                st.plotly_chart(pie, use_container_width=True)
            with col2:
                bar = px.bar(exp_df.groupby('category')['amount'].sum().reset_index(),
                             x='category', y='amount', title="Expenses by Category (Bar Chart)")
                st.plotly_chart(bar, use_container_width=True)

    # Budget Overview
    st.subheader("📊 Budget Overview")
    budgets = get_budgets(uid, today.year, today.month)
    if not budgets.empty:
        exp_df = df[df['type'] == 'expense']
        spent = exp_df.groupby('category')['amount'].sum() if not exp_df.empty else {}
        for _, row in budgets.iterrows():
            used = spent.get(row['category'], 0)
            progress = min(used / row['amount'], 1.0) if row['amount'] > 0 else 0
            st.progress(progress)
            st.write(f"{row['category']}: ₹{used:.2f}/₹{row['amount']:.2f}")

    # Show Budget Notifications
    notifications = check_budget_notifications(uid, today.year, today.month)
    if notifications:
        st.subheader("🔔 Budget Notifications")
        for note in notifications:
            st.warning(note)
