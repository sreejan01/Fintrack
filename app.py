from flask import Flask, render_template, request, redirect, url_for, session, Response, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from datetime import datetime
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os
import io
import csv

# ----------------------
# Flask App Setup
# ----------------------
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# ----------------------
# Database Configuration (Neon PostgreSQL)
# ----------------------
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://neondb_owner:npg_zT52yOZkwiRg@ep-shiny-shape-a1d993og-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ----------------------
# Database Models
# ----------------------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    expenses = db.relationship('Expense', backref='user', lazy=True)
    goals = db.relationship('Goal', backref='user', lazy=True)


class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(100))
    amount = db.Column(db.Float)
    category = db.Column(db.String(100))
    date = db.Column(db.String(20))


class Goal(db.Model):
    __tablename__ = 'goals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    month = db.Column(db.String(20))
    amount = db.Column(db.Float)


# Create tables if they don't exist
with app.app_context():
    db.create_all()


# ----------------------
# Login Required Decorator
# ----------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ----------------------
# Routes
# ----------------------

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


# Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return "Username already exists"

        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('register.html')


# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['user_id'] = user.id
            return redirect(url_for('dashboard'))
        else:
            return "Invalid credentials"
    return render_template('login.html')


# Logout
@app.route('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('home'))


# ----------------------
# Add / Edit / Delete Expense
# ----------------------
@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        title = request.form.get('title', '')
        category = request.form.get('category', '')
        amount = float(request.form.get('amount', 0) or 0)
        date = request.form.get('date', datetime.now().strftime('%Y-%m-%d'))

        new_expense = Expense(
            user_id=session['user_id'],
            title=title,
            category=category,
            amount=amount,
            date=date
        )
        db.session.add(new_expense)
        db.session.commit()

        return redirect(url_for('dashboard'))

    return render_template('add_expense.html')


@app.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=session['user_id']).first()
    if not expense:
        return "Expense not found"

    if request.method == 'POST':
        expense.title = request.form.get('title', '')
        expense.category = request.form.get('category', '')
        expense.amount = float(request.form.get('amount', 0) or 0)
        expense.date = request.form.get('date', datetime.now().strftime('%Y-%m-%d'))
        db.session.commit()
        return redirect(url_for('dashboard'))

    return render_template('edit_expense.html', expense=expense)


@app.route('/delete_expense/<int:expense_id>')
@login_required
def delete_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=session['user_id']).first()
    if expense:
        db.session.delete(expense)
        db.session.commit()
    return redirect(url_for('dashboard'))


@app.route('/delete_multiple_expenses', methods=['POST'])
@login_required
def delete_multiple_expenses():
    ids = request.form.getlist('expense_ids')
    if ids:
        Expense.query.filter(Expense.id.in_(ids), Expense.user_id == session['user_id']).delete(synchronize_session=False)
        db.session.commit()
        flash(f'Deleted {len(ids)} expenses successfully!', 'success')
    else:
        flash('No expenses selected!', 'warning')
    return redirect(url_for('dashboard'))


# ----------------------
# Goals
# ----------------------
@app.route('/set_goal', methods=['POST'])
@login_required
def set_goal():
    month = request.form.get('month') or datetime.now().strftime('%Y-%m')
    goal_amount = float(request.form.get('goal_amount', 0) or 0)

    goal = Goal.query.filter_by(user_id=session['user_id'], month=month).first()
    if goal:
        goal.amount = goal_amount
    else:
        db.session.add(Goal(user_id=session['user_id'], month=month, amount=goal_amount))
    db.session.commit()

    return redirect(url_for('dashboard'))


# ----------------------
# Export Routes
# ----------------------
@app.route('/export/csv')
@login_required
def export_csv():
    expenses = Expense.query.filter_by(user_id=session['user_id']).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Title', 'Category', 'Amount', 'Date'])
    for e in expenses:
        writer.writerow([e.title, e.category, e.amount, e.date])

    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=expenses.csv'
    return response


@app.route('/export/excel')
@login_required
def export_excel():
    wb = Workbook()
    ws = wb.active
    ws.title = "Expenses"
    ws.append(['Title', 'Category', 'Amount', 'Date'])

    expenses = Expense.query.filter_by(user_id=session['user_id']).all()
    for e in expenses:
        ws.append([e.title, e.category, e.amount, e.date])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="expenses.xlsx")


@app.route('/export/pdf')
@login_required
def export_pdf():
    expenses = Expense.query.filter_by(user_id=session['user_id']).all()
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter)
    pdf.setTitle("Expense Report")

    y = 750
    pdf.drawString(50, y, "Title          Category          Amount          Date")
    y -= 20
    for e in expenses:
        line = f"{e.title}   {e.category}   ₹{e.amount}   {e.date}"
        pdf.drawString(50, y, line)
        y -= 20
        if y < 50:
            pdf.showPage()
            y = 750
    pdf.save()
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="expenses.pdf")


# ----------------------
# Import Excel (Fixed Mapping)
# ----------------------
@app.route('/import_excel', methods=['POST'])
@login_required
def import_excel():
    # Debug/log the incoming file keys to help track client-side issues
    app.logger.debug(f"import_excel called, request.files keys: {list(request.files.keys())}")

    # Accept both 'excel_file' (used in the template) and fallback to 'file'
    file = request.files.get('excel_file') or request.files.get('file')
    if not file:
        flash('No file part. Please choose a file before uploading.', 'danger')
        return redirect(url_for('dashboard'))

    if file.filename == '':
        flash('No selected file. Please choose a valid Excel file.', 'warning')
        return redirect(url_for('dashboard'))

    try:
        import pandas as pd
        df = pd.read_excel(file)
        df.columns = [c.strip().lower() for c in df.columns]

        # Handle swapped columns
        if 'title' in df.columns and 'date' in df.columns:
            title_col, date_col = 'title', 'date'
        elif 'date (yyyy-mm-dd)' in df.columns:
            title_col, date_col = 'title', 'date (yyyy-mm-dd)'
        elif 'date' in df.columns and 'title' not in df.columns:
            title_col, date_col = 'date', 'title'
        else:
            flash('Invalid Excel format. Please use the provided template.', 'danger')
            return redirect(url_for('dashboard'))

        for _, row in df.iterrows():
            title = str(row.get(title_col, '')).strip()
            category = str(row.get('category', '')).strip()
            amount = float(row.get('amount', 0) or 0)
            date = str(row.get(date_col, '')).strip()

            if not date or date.lower() in ['nan', 'none']:
                date = datetime.now().strftime('%Y-%m-%d')

            new_expense = Expense(
                user_id=session['user_id'],
                title=title,
                category=category,
                amount=amount,
                date=date
            )
            db.session.add(new_expense)

        db.session.commit()
        flash('Expenses imported successfully!', 'success')

    except Exception as e:
        flash(f'Error importing file: {e}', 'danger')

    return redirect(url_for('dashboard'))


# ----------------------
# Download Excel Template
# ----------------------
@app.route('/download_template')
@login_required
def download_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "Expense Template"
    ws.append(["Title", "Category", "Amount", "Date (YYYY-MM-DD)"])
    ws.append(["Lunch", "Food", "150.00", "2025-10-27"])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        download_name="expense_template.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ----------------------
# Dashboard
# ----------------------
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    selected_month = request.form.get('month', datetime.now().strftime('%Y-%m')) if request.method == 'POST' else datetime.now().strftime('%Y-%m')

    if selected_month == "lifetime":
        expenses = Expense.query.filter_by(user_id=session['user_id']).all()
    else:
        expenses = Expense.query.filter(Expense.user_id == session['user_id'], Expense.date.like(f"{selected_month}%")).all()

    category_totals = {}
    for e in expenses:
        category_totals[e.category] = category_totals.get(e.category, 0) + e.amount

    total_spent = sum(e.amount for e in expenses)
    goal = Goal.query.filter_by(user_id=session['user_id'], month=selected_month).first()
    goal_amount = goal.amount if goal else None

    insights = []
    if goal_amount:
        if total_spent <= goal_amount:
            remaining = goal_amount - total_spent
            insights.append(f"✅ Within goal. You can still spend ₹{round(remaining, 2)} this month.")
        else:
            over = total_spent - goal_amount
            insights.append(f"⚠️ Goal exceeded by ₹{round(over, 2)}.")

    return render_template('dashboard.html',
                           expenses=expenses,
                           category_totals=category_totals,
                           total_spent=total_spent,
                           goal_amount=goal_amount,
                           insights=insights,
                           selected_month=selected_month,
                           datetime=datetime)


# ----------------------
# Run App
# ----------------------
if __name__ == '__main__':
    app.run(debug=True)
