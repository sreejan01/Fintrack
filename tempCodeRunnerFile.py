from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ----------------------
# Initialize Database
# ----------------------
def init_db():
    if not os.path.exists('database.db'):
        conn = sqlite3.connect('database.db')
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
        conn.commit()
        conn.close()

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
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            return redirect(url_for('login'))
        except:
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
        conn = sqlite3.connect('database.db')
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
# Dashboard
# ----------------------
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    if request.method == 'POST':
        selected_month = request.form['month']
    else:
        selected_month = datetime.now().strftime('%Y-%m')

    if selected_month == "lifetime":
        # 🔹 Fetch all expenses
        c.execute('SELECT id, title, amount, category, date FROM expenses WHERE user_id=?', (session['user_id'],))
        expenses = c.fetchall()

        # Category totals (lifetime)
        c.execute('''
            SELECT category, SUM(amount) 
            FROM expenses 
            WHERE user_id=?
            GROUP BY category
        ''', (session['user_id'],))
        category_data = c.fetchall()
        category_totals = {row[0]: row[1] for row in category_data}

        total_spent = sum([float(row[2]) for row in expenses])

    else:
        # 🔹 Fetch monthly expenses
        c.execute('''
            SELECT id, title, amount, category, date 
            FROM expenses 
            WHERE user_id=? AND strftime('%Y-%m', date)=?
        ''', (session['user_id'], selected_month))
        expenses = c.fetchall()

        # Category totals (monthly)
        c.execute('''
            SELECT category, SUM(amount) 
            FROM expenses 
            WHERE user_id=? AND strftime('%Y-%m', date)=?
            GROUP BY category
        ''', (session['user_id'], selected_month))
        category_data = c.fetchall()
        category_totals = {row[0]: row[1] for row in category_data}

        total_spent = sum([float(row[2]) for row in expenses])

    conn.close()
    return render_template('dashboard.html', 
                       expenses=expenses, 
                       category_totals=category_totals,
                       total_spent=total_spent,
                       selected_month=selected_month,
                       datetime=datetime)  # ✅ this line fixes it



# ----------------------
# Edit Expense
# ----------------------
@app.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    if request.method == 'POST':
        title = request.form['title']
        amount = request.form['amount']
        category = request.form['category']
        date = request.form['date']
        c.execute('''
            UPDATE expenses
            SET title=?, amount=?, category=?, date=?
            WHERE id=? AND user_id=?
        ''', (title, amount, category, date, expense_id, session['user_id']))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    # GET request – fetch existing expense
    c.execute('SELECT title, amount, category, date FROM expenses WHERE id=? AND user_id=?', 
              (expense_id, session['user_id']))
    expense = c.fetchone()
    conn.close()
    if expense:
        return render_template('edit_expense.html', expense_id=expense_id, expense=expense)
    else:
        return "Expense not found"

# ----------------------
# Delete Expense
# ----------------------
@app.route('/delete_expense/<int:expense_id>')
@login_required
def delete_expense(expense_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('DELETE FROM expenses WHERE id=? AND user_id=?', (expense_id, session['user_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

# ----------------------
# Add Expense
# ----------------------
@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        title = request.form['title']
        amount = request.form['amount']
        category = request.form['category']
        date = request.form['date']
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO expenses (user_id, title, amount, category, date)
            VALUES (?, ?, ?, ?, ?)
        ''', (session['user_id'], title, amount, category, date))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    return render_template('add_expense.html')

# ----------------------
# Run the App
# ----------------------
if __name__ == '__main__':
    app.run(debug=True)
