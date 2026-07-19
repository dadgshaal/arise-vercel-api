import os
from pathlib import Path
import psycopg2

schema_file = Path(__file__).with_name("database_schema_v2.sql")
database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL belum di-set")

sql = schema_file.read_text(encoding="utf-8")
conn = psycopg2.connect(database_url, connect_timeout=10)
try:
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print("Database schema + seed ARISE berhasil dijalankan.")
finally:
    conn.close()
