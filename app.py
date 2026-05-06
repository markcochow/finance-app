from flask import Flask, render_template, request, redirect
import sqlite3
import os
from datetime import datetime

app = Flask(name)
DB_NAME = "finance.db"


------------------------------------------------

1. Initialize DB (transactions + categories)

------------------------------------------------
def init_db():
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

    # Insert default categories if empty
    default_categories = [
        "Food", "Transport", "Groceries", "Shopping", "Bills",
        "Rent", "Medical", "Entertainment", "Salary", "Others"
    ]

    for cat in default_categories:
        try:
            c.execute("INSERT INTO categories (name) VALUES (?)", (cat,))
        except:
            pass  # Ignore duplicates

    conn.commit()
    conn.close()


Run DB initialization immediately (important for Render)
init_db()


------------------------------------------------

Helper: DB connection

------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


------------------------------------------------

Home page

------------------------------------------------
@app.route("/")
def index():
    conn = get_db()
    rows = conn.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC").fetchall()
    conn.close()

    total_income = sum(r["amount"] for r in rows if r["type"] == "income")
    total_expense = sum(r["amount"] for r in rows if r["type"] == "expense")
    balance = totalincome - totalexpense

    return render_template(
        "index.html",
        transactions=rows,
        totalincome=totalincome,
        totalexpense=totalexpense,
        balance=balance
    )


------------------------------------------------

Add transaction

------------------------------------------------
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

        conn.execute(
            "INSERT INTO transactions (type, amount, category, date, notes) VALUES (?, ?, ?, ?, ?)",
            (t_type, amount, category, date, notes)
        )
        conn.commit()
        conn.close()
        return redirect("/")

    conn.close()
    return render_template("add.html", categories=categories)


------------------------------------------------

Edit transaction

------------------------------------------------
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    conn = get_db()
    categories = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
    transaction = conn.execute("SELECT * FROM transactions WHERE id = ?", (id,)).fetchone()

    if request.method == "POST":
        t_type = request.form["type"]
        amount = float(request.form["amount"])
        category = request.form["category"]
        date = request.form["date"]
        notes = request.form["notes"]

        conn.execute("""
            UPDATE transactions
            SET type=?, amount=?, category=?, date=?, notes=?
            WHERE id=?
        """, (t_type, amount, category, date, notes, id))

        conn.commit()
        conn.close()
        return redirect("/")

    conn.close()
    return render_template("edit.html", transaction=transaction, categories=categories)


------------------------------------------------

Delete transaction

------------------------------------------------
@app.route("/delete/<int:id>")
def delete(id):
    conn = get_db()
    conn.execute("DELETE FROM transactions WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/")


------------------------------------------------

Monthly summary

------------------------------------------------
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
    conn.close()

    total_income = sum(r["amount"] for r in rows if r["type"] == "income")
    total_expense = sum(r["amount"] for r in rows if r["type"] == "expense")
    balance = totalincome - totalexpense

    return render_template(
        "monthly.html",
        transactions=rows,
        totalincome=totalincome,
        totalexpense=totalexpense,
        balance=balance,
        month=month_str
    )


------------------------------------------------

Category management

------------------------------------------------
@app.route("/categories", methods=["GET", "POST"])
def categories():
    conn = get_db()

    if request.method == "POST":
        new_cat = request.form["name"]
        try:
            conn.execute("INSERT INTO categories (name) VALUES (?)", (new_cat,))
            conn.commit()
        except:
            pass  # ignore duplicates

    cats = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    conn.close()

    return render_template("categories.html", categories=cats)


------------------------------------------------

Local run

------------------------------------------------
if name == "main":
    init_db()
    app.run(debug=True)
