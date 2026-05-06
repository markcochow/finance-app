from flask import Flask, render_template, request, redirect
import sqlite3
import os

app = Flask(__name__)
DB_NAME = "finance.db"


# ------------------------------------------------
# 1. Ensure database + table always exist
# ------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
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
    conn.commit()
    conn.close()


# Run DB initialization immediately (important for Render)
init_db()


# ------------------------------------------------
# 2. Helper: get DB connection
# ------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# ------------------------------------------------
# 3. Home page (list + totals)
# ------------------------------------------------
@app.route("/")
def index():
    conn = get_db()
    rows = conn.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC").fetchall()
    conn.close()

    total_income = sum(r["amount"] for r in rows if r["type"] == "income")
    total_expense = sum(r["amount"] for r in rows if r["type"] == "expense")
    balance = total_income - total_expense

    return render_template(
        "index.html",
        transactions=rows,
        total_income=total_income,
        total_expense=total_expense,
        balance=balance
    )


# ------------------------------------------------
# 4. Add transaction (GET + POST)
# ------------------------------------------------
@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        t_type = request.form["type"]
        amount = float(request.form["amount"])
        category = request.form.get("category", "")
        date = request.form.get("date", "")
        notes = request.form.get("notes", "")

        conn = get_db()
        conn.execute(
            "INSERT INTO transactions (type, amount, category, date, notes) VALUES (?, ?, ?, ?, ?)",
            (t_type, amount, category, date, notes)
        )
        conn.commit()
        conn.close()

        return redirect("/")

    return render_template("add.html")


# ------------------------------------------------
# 5. Dashboard (pie chart)
# ------------------------------------------------
@app.route("/dashboard")
def dashboard():
    conn = get_db()
    rows = conn.execute("SELECT * FROM transactions").fetchall()
    conn.close()

    categories = {}
    for r in rows:
        if r["type"] == "expense":
            categories[r["category"]] = categories.get(r["category"], 0) + r["amount"]

    labels = list(categories.keys())
    values = list(categories.values())

    return render_template(
        "dashboard.html",
        labels=labels,
        values=values
    )


# ------------------------------------------------
# 6. Local run
# ------------------------------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)