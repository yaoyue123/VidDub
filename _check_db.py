"""Check what videos are in the database."""
import sqlite3, os

db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', 'data')
db_path = os.path.join(db_dir, 'you2bili.db')

if not os.path.isfile(db_path):
    print(f'DB not found: {db_path}')
    # try app.db
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', 'app.db')

print(f'Using DB: {db_path}')
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f'Tables: {tables}')

for table in tables:
    cur.execute(f'SELECT * FROM "{table}" LIMIT 5')
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    print(f'\n--- {table} ({len(rows)} rows) ---')
    print(f'  Columns: {cols}')
    for row in rows:
        for i, col in enumerate(cols):
            val = row[i]
            if isinstance(val, str) and len(val) > 60:
                val = val[:60] + '...'
            print(f'  {col}: {val}')
        print()
conn.close()
