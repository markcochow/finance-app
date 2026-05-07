from flask import Flask, render_template, request, redirect, url_for, send_file
import sqlite3
import os
import json
from datetime import datetime

app = Flask(__name__)

DB_NAME = "finance.db"   # For Render; change to "/data/finance.db" on Railway


# --------------------------------------------------
# Initialize database and create tables if missing
# --------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Transactions table
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            notes TEXT
        )
    """)

    # Account history table
    c.execute("""
        CREATE TABLE IF NOT EXISTS account_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            change REAL NOT NULL,
            source TEXT NOT NULL
        )
    """)

    # Categories table
    c.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)

    # Insert default categories if empty
    default_categories = [
        "Food", "Transport", "Groceries", "Shopping", "Bills",
        "Rent", "Medical", "Entertainment", "Salary", "Others"
    ]

    for cat in default_categories:
        c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))

    conn.commit()
    conn.close()


# Ensure DB exists when app starts
init_db()


# --------------------------------------------------
# Helper: DB connection
# --------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------
# Helper: Get all months since first transaction
# --------------------------------------------------
def get_all_months():
    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT strftime('%Y-%m', date) AS month
        FROM transactions
        ORDER BY month DESC
    """).fetchall()
    conn.close()
    return [r["month"] for r in rows]


# --------------------------------------------------
# Helper: Current month
# --------------------------------------------------
def current_month():
    return datetime.now().strftime("%Y-%m")


# --------------------------------------------------
# Helper: Account balance from account_history
# --------------------------------------------------
def get_account_balance():
    conn = get_db()
    row = conn.execute("SELECT SUM(change) FROM account_history").fetchone()
    conn.close()
    return row[0] or 0


# --------------------------------------------------
# Helper: Record account change
# --------------------------------------------------
def record_account_change(date, type_, amount, notes):
    conn = get_db()

    change = amount if type_ == "income" else -amount

    conn.execute("""
        INSERT INTO account_history (date, change, source)
        VALUES (?, ?, ?)
    """, (date, change, notes))

    conn.commit()
    conn.close()


# --------------------------------------------------
# HOME PAGE Monthly Dashboard
# --------------------------------------------------
@app.route("/")
def index():
    selected_month = request.args.get("month", current_month())
    search = request.args.get("search", "")
    category_filter = request.args.get("category", "")
    type_filter = request.args.get("type", "")
    sort = request.args.get("sort", "date_desc")

    query = "SELECT * FROM transactions WHERE strftime('%Y-%m', date)=?"
    params = [selected_month]

    if search:
        query += " AND (notes LIKE ? OR category LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]

    if category_filter:
        query += " AND category=?"
        params.append(category_filter)

    if type_filter:
        query += " AND type=?"
        params.append(type_filter)

    if sort == "date_asc":
        query += " ORDER BY date ASC"
    elif sort == "amount_asc":
        query += " ORDER BY amount ASC"
    elif sort == "amount_desc":
        query += " ORDER BY amount DESC"
    else:
        query += " ORDER BY date DESC"

    conn = get_db()
    transactions = conn.execute(query, params).fetchall()

    summary = conn.execute("""
        SELECT 
            SUM(CASE WHEN type='income' THEN amount ELSE 0 END) AS income,
            SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) AS expense
        FROM transactions
        WHERE strftime('%Y-%m', date)=?
    """, (selected_month,)).fetchone()

    income = summary["income"] or 0
    expense = summary["expense"] or 0
    balance = income - expense

    income_chart = conn.execute("""
        SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE type='income' AND strftime('%Y-%m', date)=?
        GROUP BY category
    """, (selected_month,)).fetchall()

    expense_chart = conn.execute("""
        SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE type='expense' AND strftime('%Y-%m', date)=?
        GROUP BY category
    """, (selected_month,)).fetchall()

    conn.close()

    months = get_all_months()

    return render_template(
        "index.html",
        transactions=transactions,
        selected_month=selected_month,
        months=months,
        income=income,
        expense=expense,
        balance=balance,
        income_chart=json.dumps([dict(r) for r in income_chart]),
        expense_chart=json.dumps([dict(r) for r in expense_chart]),
        search=search,
        category_filter=category_filter,
        type_filter=type_filter,
        sort=sort
    )


# --------------------------------------------------
# OTHER TRANSACTIONS PAGE
# --------------------------------------------------
@app.route("/other")
def other_transactions():
    end_month = request.args.get("end", current_month())
    start_month = request.args.get("start")

    if not start_month:
        y, m = map(int, end_month.split("-"))
        m -= 2
        if m <= 0:
            m += 12
            y -= 1
        start_month = f"{y}-{m:02d}"

    conn = get_db()

    transactions = conn.execute("""
        SELECT * FROM transactions
        WHERE strftime('%Y-%m', date) BETWEEN ? AND ?
        ORDER BY date DESC
    """, (start_month, end_month)).fetchall()

    summary = conn.execute("""
        SELECT 
            SUM(CASE WHEN type='income' THEN amount ELSE 0 END) AS income,
            SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) AS expense
        FROM transactions
        WHERE strftime('%Y-%m', date) BETWEEN ? AND ?
    """, (start_month, end_month)).fetchone()

    income = summary["income"] or 0
    expense = summary["expense"] or 0
    balance = income - expense

    line_data = conn.execute("""
        SELECT 
            strftime('%Y-%m', date) AS month,
            SUM(CASE WHEN type='income' THEN amount ELSE 0 END) AS income,
            SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) AS expense
        FROM transactions
        WHERE strftime('%Y-%m', date) BETWEEN ? AND ?
        GROUP BY month
        ORDER BY month ASC
    """, (start_month, end_month)).fetchall()

    conn.close()

    return render_template(
        "other_transactions.html",
        transactions=transactions,
        start_month=start_month,
        end_month=end_month,
        income=income,
        expense=expense,
        balance=balance,
        line_data=json.dumps([dict(r) for r in line_data])
    )


# --------------------------------------------------
# ACCOUNT PAGE
# --------------------------------------------------
@app.route("/account")
def account():
    balance = get_account_balance()
    return render_template(
        "account.html",
        balance=balance,
        current_date=datetime.now().strftime("%Y-%m-%d")
    )


# --------------------------------------------------
# CATEGORIES PAGE
# --------------------------------------------------
@app.route("/categories")
def categories():
    conn = get_db()
    rows = conn.execute("""
        SELECT c.name AS category,
               SUM(CASE WHEN t.type='income' THEN t.amount ELSE 0 END) AS income,
               SUM(CASE WHEN t.type='expense' THEN t.amount ELSE 0 END) AS expense
        FROM categories c
        LEFT JOIN transactions t ON c.name = t.category
        GROUP BY c.name
        ORDER BY c.name
    """).fetchall()
    conn.close()
    return render_template("categories.html", rows=rows)


# --------------------------------------------------
# ADD TRANSACTION
# --------------------------------------------------
@app.route("/add", methods=["GET", "POST"])
def add():
    conn = get_db()
    categories = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
    conn.close()

    if request.method == "POST":
        date = request.form["date"]
        category = request.form["category"]
        type_ = request.form["type"]
        amount = float(request.form["amount"])
        notes = request.form["notes"]

        conn = get_db()
        conn.execute("""
            INSERT INTO transactions (date, category, type, amount, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (date, category, type_, amount, notes))
        conn.commit()
        conn.close()

        record_account_change(date, type_, amount, notes)

        return redirect(url_for("index"))

    return render_template("add.html", categories=categories)


# --------------------------------------------------
# EDIT TRANSACTION
# --------------------------------------------------
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    conn = get_db()
    categories = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()

    if request.method == "POST":
        date = request.form["date"]
        category = request.form["category"]
        type_ = request.form["type"]
        amount = float(request.form["amount"])
        notes = request.form["notes"]

        old = conn.execute("SELECT * FROM transactions WHERE id=?", (id,)).fetchone()

        # Reverse old entry
        record_account_change(old["date"], "income" if old["type"] == "expense" else "expense", old["amount"], "Edit reversal")

        # Update
        conn.execute("""
            UPDATE transactions
            SET date=?, category=?, type=?, amount=?, notes=?
            WHERE id=?
        """, (date, category, type_, amount, notes, id))
        conn.commit()

        # Apply new entry
        record_account_change(date, type_, amount, notes)

        conn.close()
        return redirect(url_for("index"))

    transaction = conn.execute("SELECT * FROM transactions WHERE id=?", (id,)).fetchone()
    conn.close()

    return render_template("edit.html", transaction=transaction, categories=categories)


# --------------------------------------------------
# DELETE TRANSACTION
# --------------------------------------------------
@app.route("/delete/<int:id>")
def delete(id):
    conn = get_db()

    old = conn.execute("SELECT * FROM transactions WHERE id=?", (id,)).fetchone()

    record_account_change(old["date"], "income" if old["type"] == "expense" else "expense", old["amount"], "Delete reversal")

    conn.execute("DELETE FROM transactions WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("index"))


# --------------------------------------------------
# EXPORT / IMPORT DB
# --------------------------------------------------
@app.route("/export_db")
def export_db():
    return send_file(DB_NAME, as_attachment=True)


@app.route("/import_db", methods=["POST"])
def import_db():
    file = request.files["file"]
    file.save(DB_NAME)
    return redirect(url_for("index"))


# --------------------------------------------------
# RUN APP
# --------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
