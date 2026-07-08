import sqlite3
conn = sqlite3.connect('liplab.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print("Tables:", tables)
for (table,) in tables:
    c.execute(f"PRAGMA table_info({table})")
    cols = c.fetchall()
    print(f"\n{table}:", [col[1] for col in cols])
conn.close()
