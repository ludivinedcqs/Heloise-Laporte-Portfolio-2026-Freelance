import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect("database.db")
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
