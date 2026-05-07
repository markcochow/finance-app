from flask import Flask, render_template, request, redirect, url_for, send_file
import sqlite3
import os
from datetime import datetime
import json

app = Flask(__name__)

DB_NAME = "finance.db"   # For Render development. Later change to /data/finance.db on Railway.


# -----------------------------
# Helper: Get DB connection
# -----------------------------
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# -----------------------------
# Helper: Get all months since first transaction
# -----------------------------
def get_all_months():
    conn = get_db()
    months = conn.execute("""
        SELECT DISTINCT strftime('%Y-%m', date) AS month
        FROM transactions
        ORDER BY month DESC
    """).fetchall()
    conn.close()
    return [m["month"] for m in months]


# -----------------------------
# Helper: Get current month (YYYY-MM)
# -----------------------------
def current_month():
    return datetime.now().strftime("%Y-%m")


# -----------------------------
# HOME PAGE  Monthly Dashboard
# -----------------------------
@app.route("/")
def index():
    # 1. Determine selected month
    selected_month = request.args.get("month", current_month())

    # 2. Filters
    search = request.args.get("search", "")
    category_filter = request.args.get("category", "")
    type_filter = request.args.get("type", "")
    sort = request.args.get("sort", "date_desc")

    # 3. Build SQL query
    query = """
        SELECT * FROM transactions
        WHERE strftime('%Y-%m', date) = ?
    """
    params = [selected_month]

    if search:
        query += " AND (notes LIKE ? OR category LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]

    if category_filter:
        query += " AND category = ?"
        params.append(category_filter)

    if type_filter:
        query += " AND type = ?"
        params.append(type_filter)

    # Sorting
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

    # 4. Monthly summary totals
    summary = conn.execute("""
        SELECT 
            SUM(CASE WHEN type='income' THEN amount ELSE 0 END) AS income,
            SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) AS expense
        FROM transactions
        WHERE strftime('%Y-%m', date) = ?
    """, (selected_month,)).fetchone()

    income = summary["income"] or 0
    expense = summary["expense"] or 0
    balance = income - expense

    # 5. Mini chart data (category breakdown)
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

    # 6. Month selector list
    months = get_all_months()

    return render_template(
        "index.html",
        transactions=transactions,
        selected_month=selected_month,
        months=months,
        income=income,
        expense=expense,
        balance=balance,
        income_chart=json.dumps([dict(row) for row in income_chart]),
        expense_chart=json.dumps([dict(row) for row in expense_chart]),
        search=search,
        category_filter=category_filter,
        type_filter=type_filter,
        sort=sort
    )


# -----------------------------
# OTHER TRANSACTIONS PAGE
# -----------------------------
@app.route("/other")
def other_transactions():
    # Default: last 3 months
    end_month = request.args.get("end", current_month())
    start_month = request.args.get("start")

    if not start_month:
        # Compute 3 months before end_month
        y, m = map(int, end_month.split("-"))
        m -= 2
        if m <= 0:
            m += 12
            y -= 1
        start_month = f"{y}-{m:02d}"

    conn = get_db()

    # 1. Fetch transactions in range
    transactions = conn.execute("""
        SELECT * FROM transactions
        WHERE strftime('%Y-%m', date) BETWEEN ? AND ?
        ORDER BY date DESC
    """, (start_month, end_month)).fetchall()

    # 2. Summary for selected period
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

    # 3. Line chart data (monthly totals)
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
        line_data=json.dumps([dict(row) for row in line_data])
    )


# -----------------------------
# ACCOUNT PAGE (Simplified)
# -----------------------------
@app.route("/account")
def account():
    conn = get_db()
    total_income = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='income'").fetchone()[0] or 0
    total_expense = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='expense'").fetchone()[0] or 0
    balance = total_income - total_expense
    conn.close()

    return render_template("account.html", balance=balance)


# -----------------------------
# ADD, EDIT, DELETE (unchanged)
# -----------------------------
@app.route("/add", methods=["GET", "POST"])
def add():
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

        return redirect(url_for("index"))

    return render_template("add.html")


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    conn = get_db()

    if request.method == "POST":
        date = request.form["date"]
        category = request.form["category"]
        type_ = request.form["type"]
        amount = float(request.form["amount"])
        notes = request.form["notes"]

        conn.execute("""
            UPDATE transactions
            SET date=?, category=?, type=?, amount=?, notes=?
            WHERE id=?
        """, (date, category, type_, amount, notes, id))
        conn.commit()
        conn.close()

        return redirect(url_for("index"))

    transaction = conn.execute("SELECT * FROM transactions WHERE id=?", (id,)).fetchone()
    conn.close()
    return render_template("edit.html", transaction=transaction)


@app.route("/delete/<int:id>")
def delete(id):
    conn = get_db()
    conn.execute("DELETE FROM transactions WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

# -----------------------------
# CATEGORIES (unchanged)
# -----------------------------

@app.route("/categories")
def categories():
    conn = get_db()
    rows = conn.execute("""
        SELECT category,
               SUM(CASE WHEN type='income' THEN amount ELSE 0 END) AS income,
               SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) AS expense
        FROM transactions
        GROUP BY category
        ORDER BY category
    """).fetchall()
    conn.close()
    return render_template("categories.html", rows=rows)


# -----------------------------
# EXPORT / IMPORT DB (unchanged)
# -----------------------------
@app.route("/export_db")
def export_db():
    return send_file(DB_NAME, as_attachment=True)


@app.route("/import_db", methods=["POST"])
def import_db():
    file = request.files["file"]
    file.save(DB_NAME)
    return redirect(url_for("index"))


# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)
