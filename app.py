from flask import Flask, render_template, request, redirect
import sqlite3
import os
from datetime import datetime
import json

app = Flask(__name__)

# Force DB to always be in the same directory
DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "finance.db")
os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)


# ------------------------------------------------
# Initialize DB
# ------------------------------------------------
def init_db():
    # Prevent Render from silently creating a new DB
    if not os.path.exists(DB_NAME):
        raise RuntimeError("Database file missing - Render created a new working directory.")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Transactions table
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT,
            date TEXT,
            notes TEXT
        );
    """)

    # Categories table
    c.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
    """)

    # Account history table
    c.execute("""
        CREATE TABLE IF NOT EXISTS account_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            note TEXT
        );
    """)

    # Insert default categories
    default_categories = [
        "Food", "Transport", "Groceries", "Shopping", "Bills",
        "Rent", "Medical", "Entertainment", "Salary", "Others"
    ]

    for cat in default_categories:
        try:
            c.execute("INSERT INTO categories (name) VALUES (?)", (cat,))
        except:
            pass

    # Insert starting balance = 0 only if empty
    count = c.execute("SELECT COUNT(*) FROM account_history").fetchone()[0]
    if count == 0:
        c.execute("INSERT INTO account_history (amount, date, note) VALUES (?, ?, ?)",
                  (0, datetime.now().strftime("%Y-%m-%d"), "Initial balance"))

    conn.commit()
    conn.close()


init_db()


# ------------------------------------------------
# Helper
# ------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def get_account_balance():
    conn = get_db()
    total = conn.execute("SELECT SUM(amount) FROM account_history").fetchone()[0]
    conn.close()
    return total if total else 0


# ------------------------------------------------
# Home
# ------------------------------------------------
@app.route("/")
def index():
    conn = get_db()
    rows = conn.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC").fetchall()
    conn.close()

    total_income = sum(r["amount"] for r in rows if r["type"] == "income")
    total_expense = sum(r["amount"] for r in rows if r["type"] == "expense")
    balance = total_income - total_expense

    account_balance = get_account_balance()

    return render_template(
        "index.html",
        transactions=rows,
        total_income=total_income,
        total_expense=total_expense,
        balance=balance,
        account_balance=account_balance
    )


# ------------------------------------------------
# Add transaction
# ------------------------------------------------
@app.route("/add", methods=["GET", "POST"])
def add():
    conn = get_db()
    categories = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()

    if request.method == "POST":
        t_type = request.form["type"]
        amount = float(request.form["amount"])
        category = request.form["category"]
        date = request.form["date"]
        notes = request.form["notes"]

        # Insert transaction
        conn.execute("""
            INSERT INTO transactions (type, amount, category, date, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (t_type, amount, category, date, notes))

        # Update account balance
        if t_type == "income":
            conn.execute("INSERT INTO account_history (amount, date, note) VALUES (?, ?, ?)",
                         (amount, date, f"Income: {category}"))
        else:
            conn.execute("INSERT INTO account_history (amount, date, note) VALUES (?, ?, ?)",
                         (-amount, date, f"Expense: {category}"))

        conn.commit()
        conn.close()
        return redirect("/")

    conn.close()
    return render_template("add.html", categories=categories)


# ------------------------------------------------
# Edit transaction
# ------------------------------------------------
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    conn = get_db()
    categories = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
    transaction = conn.execute("SELECT * FROM transactions WHERE id = ?", (id,)).fetchone()

    if request.method == "POST":
        old_amount = transaction["amount"]
        old_type = transaction["type"]

        t_type = request.form["type"]
        amount = float(request.form["amount"])
        category = request.form["category"]
        date = request.form["date"]
        notes = request.form["notes"]

        # Update transaction
        conn.execute("""
            UPDATE transactions
            SET type=?, amount=?, category=?, date=?, notes=?
            WHERE id=?
        """, (t_type, amount, category, date, notes, id))

        # Reverse old entry
        if old_type == "income":
            conn.execute("INSERT INTO account_history (amount, date, note) VALUES (?, ?, ?)",
                         (-old_amount, date, "Edit reversal"))
        else:
            conn.execute("INSERT INTO account_history (amount, date, note) VALUES (?, ?, ?)",
                         (old_amount, date, "Edit reversal"))

        # Add new entry
        if t_type == "income":
            conn.execute("INSERT INTO account_history (amount, date, note) VALUES (?, ?, ?)",
                         (amount, date, f"Edited income: {category}"))
        else:
            conn.execute("INSERT INTO account_history (amount, date, note) VALUES (?, ?, ?)",
                         (-amount, date, f"Edited expense: {category}"))

        conn.commit()
        conn.close()
        return redirect("/")

    conn.close()
    return render_template("edit.html", transaction=transaction, categories=categories)


# ------------------------------------------------
# Delete transaction
# ------------------------------------------------
@app.route("/delete/<int:id>")
def delete(id):
    conn = get_db()
    t = conn.execute("SELECT * FROM transactions WHERE id = ?", (id,)).fetchone()

    # Reverse effect on account
    if t["type"] == "income":
        conn.execute("INSERT INTO account_history (amount, date, note) VALUES (?, ?, ?)",
                     (-t["amount"], t["date"], "Delete income"))
    else:
        conn.execute("INSERT INTO account_history (amount, date, note) VALUES (?, ?, ?)",
                     (t["amount"], t["date"], "Delete expense"))

    conn.execute("DELETE FROM transactions WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/")


# ------------------------------------------------
# Monthly summary with pie charts
# ------------------------------------------------
@app.route("/monthly")
def monthly():
    now = datetime.now()
    month_str = now.strftime("%Y-%m")

    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM transactions
        WHERE date LIKE ?
        ORDER BY date DESC
    """, (month_str + "%",)).fetchall()

    # Totals
    income_totals = {}
    expense_totals = {}

    for r in rows:
        cat = r["category"]
        amt = r["amount"]

        if r["type"] == "income":
            income_totals[cat] = income_totals.get(cat, 0) + amt
        else:
            expense_totals[cat] = expense_totals.get(cat, 0) + amt

    conn.close()

    return render_template(
        "monthly.html",
        transactions=rows,
        month=month_str,
        income_totals=json.dumps(income_totals),
        expense_totals=json.dumps(expense_totals)
    )


# ------------------------------------------------
# Account page
# ------------------------------------------------
@app.route("/account", methods=["GET", "POST"])
def account():
    conn = get_db()

    if request.method == "POST":
        amount = float(request.form["amount"])
        date = request.form["date"]
        note = request.form["note"]

        conn.execute("INSERT INTO account_history (amount, date, note) VALUES (?, ?, ?)",
                     (amount, date, note))
        conn.commit()

    history = conn.execute("SELECT * FROM account_history ORDER BY date DESC, id DESC").fetchall()
    balance = get_account_balance()

    conn.close()

    return render_template("account.html", history=history, balance=balance)


# ------------------------------------------------
# Run
# ------------------------------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
