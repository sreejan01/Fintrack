import sqlite3
conn = sqlite3.connect('database.db')
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    month TEXT,
    amount REAL,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
''')
conn.commit()
conn.close()
print("Migration done.")