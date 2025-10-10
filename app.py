from flask import Flask, render_template, request, redirect, url_for, session, Response, send_file, flash
import sqlite3
import os
from functools import wraps
from datetime import datetime
import csv
import io
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from flask import send_file

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'


# ----------------------
# Login required decorator
# ----------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ----------------------
# Database helper
# ----------------------
def get_db():
    conn = sqlite3.connect('database.db', timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ----------------------
# Initialize Database
# ----------------------
def init_db():
    if not os.path.exists('database.db'):
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT UNIQUE,
                            password TEXT
                        )''')
            c.execute('''CREATE TABLE expenses (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            title TEXT,
                            amount REAL,
                            category TEXT,
                            date TEXT,
                            FOREIGN KEY (user_id) REFERENCES users(id)
                        )''')
            c.execute('''CREATE TABLE goals (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            month TEXT,
                            amount REAL,
                            FOREIGN KEY (user_id) REFERENCES users(id)
                        )''')
            conn.commit()
init_db()


# ----------------------
# Home Page
# ----------------------
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


# ----------------------
# Register
# ----------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            with get_db() as conn:
                c = conn.cursor()
                c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                conn.commit()
            return redirect(url_for('login'))
        except Exception:
            return "Username already exists"
    return render_template('register.html')


# ----------------------
# Login
# ----------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
            user = c.fetchone()
        if user:
            session['user_id'] = user[0]
            return redirect(url_for('dashboard'))
        else:
            return "Invalid credentials"
    return render_template('login.html')


# ----------------------
# Logout
# ----------------------
@app.route('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('home'))


# ----------------------
# Add Expense
# ----------------------
@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        title = request.form.get('title', '')
        category = request.form.get('category', '')
        amount = request.form.get('amount', 0)
        date = request.form.get('date', datetime.now().strftime('%Y-%m-%d'))

        try:
            amount = float(amount)
        except ValueError:
            amount = 0.0

        with get_db() as conn:
            c = conn.cursor()
            c.execute('INSERT INTO expenses (user_id, title, amount, category, date) VALUES (?, ?, ?, ?, ?)',
                      (session['user_id'], title, amount, category, date))
            conn.commit()
        return redirect(url_for('dashboard'))

    return render_template('add_expense.html')


# ----------------------
# Edit Expense
# ----------------------
@app.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    with get_db() as conn:
        c = conn.cursor()
        if request.method == 'POST':
            title = request.form.get('title', '')
            category = request.form.get('category', '')
            amount = request.form.get('amount', 0)
            date = request.form.get('date', datetime.now().strftime('%Y-%m-%d'))

            try:
                amount = float(amount)
            except ValueError:
                amount = 0.0

            c.execute('UPDATE expenses SET title=?, category=?, amount=?, date=? WHERE id=? AND user_id=?',
                      (title, category, amount, date, expense_id, session['user_id']))
            conn.commit()
            return redirect(url_for('dashboard'))

        # Fetch by column names
        c.execute('SELECT * FROM expenses WHERE id=? AND user_id=?', (expense_id, session['user_id']))
        expense = c.fetchone()
    if not expense:
        return "Expense not found"
    # Pass as dictionary
    expense_dict = {key: expense[key] for key in expense.keys()}
    return render_template('edit_expense.html', expense=expense_dict)



# ----------------------
# Delete Expense
# ----------------------
@app.route('/delete_expense/<int:expense_id>')
@login_required
def delete_expense(expense_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM expenses WHERE id=? AND user_id=?', (expense_id, session['user_id']))
        conn.commit()
    return redirect(url_for('dashboard'))
# ----------------------
# Delete Multiple Expenses
# ----------------------
@app.route('/delete_multiple_expenses', methods=['POST'])
@login_required
def delete_multiple_expenses():
    ids = request.form.getlist('expense_ids')  # get selected expense IDs
    if ids:
        with get_db() as conn:
            cur = conn.cursor()
            placeholders = ','.join(['?'] * len(ids))
            query = f"DELETE FROM expenses WHERE id IN ({placeholders}) AND user_id=?"
            cur.execute(query, (*ids, session['user_id']))
            conn.commit()
        flash(f'Deleted {len(ids)} expenses successfully!', 'success')
    else:
        flash('No expenses selected!', 'warning')
    return redirect(url_for('dashboard'))


# ----------------------
# Set / update monthly goal
# ----------------------
@app.route('/set_goal', methods=['POST'])
@login_required
def set_goal():
    month = request.form.get('month') or datetime.now().strftime('%Y-%m')
    if month == "lifetime":
        return redirect(url_for('dashboard'))

    goal_amount_raw = request.form.get('goal_amount', '').strip()
    try:
        goal_amount = float(goal_amount_raw)
    except (ValueError, TypeError):
        return redirect(url_for('dashboard'))

    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM goals WHERE user_id=? AND month=?", (session['user_id'], month))
        row = c.fetchone()
        if row:
            c.execute("UPDATE goals SET amount=? WHERE id=?", (goal_amount, row[0]))
        else:
            c.execute("INSERT INTO goals (user_id, month, amount) VALUES (?, ?, ?)",
                      (session['user_id'], month, goal_amount))
        conn.commit()
    return redirect(url_for('dashboard'))


# ----------------------
# Export CSV
# ----------------------
@app.route('/export/csv')
@login_required
def export_csv():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT date, category, amount, title FROM expenses WHERE user_id = ?", (session['user_id'],))
        expenses = cur.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Category', 'Amount', 'Title'])
    for row in expenses:
        writer.writerow([row['date'], row['category'], row['amount'], row['title']])

    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=expenses.csv'
    return response


# ----------------------
# Export Excel
# ----------------------
@app.route('/export/excel')
@login_required
def export_excel():
    wb = Workbook()
    ws = wb.active
    ws.title = "Expenses"
    ws.append(['Date', 'Category', 'Amount', 'Title'])

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT date, category, amount, title FROM expenses WHERE user_id = ?", (session['user_id'],))
        for row in cur.fetchall():
            ws.append([row['date'], row['category'], row['amount'], row['title']])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(output, as_attachment=True,
                     download_name="expenses.xlsx",
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ----------------------
# Export PDF
# ----------------------
@app.route('/export/pdf')
@login_required
def export_pdf():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT date, category, amount, title FROM expenses WHERE user_id = ?", (session['user_id'],))
        expenses = cur.fetchall()

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter)
    pdf.setTitle("Expense Report")

    y = 750
    pdf.drawString(50, y, "Date          Category          Amount          Title")
    y -= 20
    for row in expenses:
        line = f"{row['date']}   {row['category']}   ₹{row['amount']}   {row['title']}"
        pdf.drawString(50, y, line)
        y -= 20
        if y < 50:
            pdf.showPage()
            y = 750
    pdf.save()
    output.seek(0)

    return send_file(output, as_attachment=True,
                     download_name="expenses.pdf",
                     mimetype='application/pdf')


# ----------------------
# Import excel
# ----------------------
@app.route('/import_excel', methods=['POST'])
@login_required
def import_excel():
    file = request.files.get('excel_file')

    if not file:
        flash('No file uploaded.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        from openpyxl import load_workbook
        wb = load_workbook(file)
        sheet = wb.active

        # Expecting columns: Date | Category | Description | Amount
        for row in sheet.iter_rows(min_row=2, values_only=True):  # skip header
            date, category, description, amount = row
            if not (date and category and amount):
                continue

            try:
                amount = float(amount)
            except (ValueError, TypeError):
                amount = 0.0

            with get_db() as conn:
                c = conn.cursor()
                c.execute(
                    'INSERT INTO expenses (user_id, date, category, title, amount) VALUES (?, ?, ?, ?, ?)',
                    (session['user_id'], date, category, description or '', amount)
                )
                conn.commit()

        flash('Excel file imported successfully!', 'success')

    except Exception as e:
        print(f"Error importing Excel: {e}")
        flash('Error importing Excel file. Please check format.', 'danger')

    return redirect(url_for('dashboard'))
@app.route('/download_template')
def download_template():
    path = 'static/templates/expense_template.xlsx'  # put your file in static/templates/
    return send_file(path, as_attachment=True)


# ----------------------
# Dashboard
# ----------------------
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    with get_db() as conn:
        c = conn.cursor()

        if request.method == 'POST':
            selected_month = request.form.get('month', datetime.now().strftime('%Y-%m'))
        else:
            selected_month = datetime.now().strftime('%Y-%m')

        if selected_month == "lifetime":
            c.execute('SELECT id, title, amount, category, date FROM expenses WHERE user_id=?',
                      (session['user_id'],))
            expenses = c.fetchall()

            c.execute('SELECT category, SUM(amount) FROM expenses WHERE user_id=? GROUP BY category',
                      (session['user_id'],))
            category_data = c.fetchall()
            category_totals = {row[0]: row[1] for row in category_data}

            total_spent = sum(float(row[2]) for row in expenses) if expenses else 0.0
            goal_amount = None
            insights = []

        else:
            c.execute('''SELECT id, title, amount, category, date
                         FROM expenses WHERE user_id=? AND strftime('%Y-%m', date)=?''',
                      (session['user_id'], selected_month))
            expenses = c.fetchall()

            c.execute('''SELECT category, SUM(amount)
                         FROM expenses WHERE user_id=? AND strftime('%Y-%m', date)=?
                         GROUP BY category''',
                      (session['user_id'], selected_month))
            category_data = c.fetchall()
            category_totals = {row[0]: row[1] for row in category_data}

            total_spent = sum(float(row[2]) for row in expenses) if expenses else 0.0

            # goal
            c.execute('SELECT amount FROM goals WHERE user_id=? AND month=?',
                      (session['user_id'], selected_month))
            goal_row = c.fetchone()
            goal_amount = float(goal_row[0]) if goal_row and goal_row[0] is not None else None

            insights = []
            try:
                last_m = prev_month(selected_month)
                c.execute("SELECT SUM(amount) FROM expenses WHERE user_id=? AND strftime('%Y-%m', date)=?",
                          (session['user_id'], last_m))
                last_total = c.fetchone()[0] or 0.0
                if last_total > 0:
                    change = ((total_spent - last_total) / last_total) * 100.0
                    if change > 0:
                        insights.append(f"📈 Your spending increased by {round(change, 1)}% compared to {last_m}.")
                    else:
                        insights.append(f"📉 Your spending decreased by {abs(round(change, 1))}% compared to {last_m}.")
            except Exception:
                pass

            if goal_amount is not None:
                if total_spent <= goal_amount:
                    remaining = goal_amount - total_spent
                    insights.insert(0, f"✅ Within goal. You can still spend ₹{round(remaining, 2)} this month.")
                else:
                    over = total_spent - goal_amount
                    insights.insert(0, f"⚠️ Goal exceeded by ₹{round(over, 2)}.")

    return render_template('dashboard.html',
                           expenses=expenses,
                           category_totals=category_totals,
                           total_spent=total_spent,
                           goal_amount=goal_amount,
                           insights=insights,
                           selected_month=selected_month,
                           datetime=datetime)


# ----------------------
# Helper: previous month
# ----------------------
def prev_month(yyyymm):
    dt = datetime.strptime(yyyymm, '%Y-%m')
    year = dt.year
    month = dt.month - 1
    if month == 0:
        month = 12
        year -= 1
    return f"{year:04d}-{month:02d}"


# ----------------------
# Run the App
# ----------------------
if __name__ == '__main__':
    app.run(debug=True)
