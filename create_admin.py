import os
import sqlite3
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

email = "heloise.laporte@yahoo.fr"
password = "MotDePasseSecur123"
hashed = generate_password_hash(password)

cur.execute(
    "INSERT INTO users (email, hash, role, name) VALUES (?, ?, ?, ?)",
    (email, hashed, "admin", "Héloïse Laporte")
)
conn.commit()
conn.close()

print("Admin créé :", email)
