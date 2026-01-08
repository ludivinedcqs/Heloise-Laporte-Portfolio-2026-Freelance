"""
app.py - Version ultra-complète pour le portfolio d'Héloïse

Fonctionnalités :
- Multilingue (fr/en/es) via JSON files in translations/
- Auth (register/login/logout/change password) avec hashing (werkzeug)
- CSRF minimal (token dans session)
- get_db() avec g, PRAGMA foreign_keys ON
- Auto-create admin user if not exists
- Dashboard client (quotes & invoices)
- Génération PDF des factures (reportlab)
- Messagerie interne client <-> admin (Héloïse)
- Interface admin protégé
- Context processor pour traductions et datetime
- Routes publiques : index, about, projects, contact
"""

import os
import sqlite3
import secrets
import json
import re
from datetime import datetime, timedelta
from io import BytesIO
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    session, g, send_file, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

# Optional: PDF generation lib
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

# -------------------------
# Configuration
# -------------------------
app = Flask(__name__)
app.secret_key = secrets.token_urlsafe(32)  # Change for production!
app.permanent_session_lifetime = timedelta(hours=4)

# File / path settings
DB = "database.db"
TRANSLATIONS_DIR = "translations"   # must contain fr.json, en.json, es.json
ADMIN_EMAIL = "heloise@example.com" # change to real email
ADMIN_PWD = "MotDePasseSecur123"    # change to secure password (used only for auto-create)
ADMIN_NAME = "Héloïse"

# -------------------------
# Utilities - Database
# -------------------------
def get_db():
    """Return a SQLite connection cached on flask.g for the current request."""
    if not getattr(g, "_db", None):
        conn = sqlite3.connect(DB, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        # ensure FK constraints
        conn.execute("PRAGMA foreign_keys = ON;")
        g._db = conn
    return g._db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()

# -------------------------
# Translations & language
# -------------------------
def load_translation(lang_code: str):
    """Load translation JSON for lang_code."""
    if lang_code not in ("fr", "en", "es"):
        lang_code = "fr"
    path = os.path.join(TRANSLATIONS_DIR, f"{lang_code}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # fallback to fr
        with open(os.path.join(TRANSLATIONS_DIR, "fr.json"), "r", encoding="utf-8") as f:
            return json.load(f)

@app.before_request
def detect_and_set_language():
    """Detect language from ?lang= or session or Accept-Language."""
    lang = request.args.get("lang")
    if lang and lang in ("fr","en","es"):
        session["lang"] = lang
    elif "lang" not in session:
        preferred = request.accept_languages.best_match(["fr","en","es"])
        session["lang"] = preferred if preferred else "fr"

@app.context_processor
def inject_globals():
    """Inject 't' (translation dict) and datetime into all templates."""
    lang = session.get("lang", "fr")
    t = load_translation(lang)
    return {"t": t, "datetime": datetime, "current_lang": lang}

# -------------------------
# CSRF (simple)
# -------------------------
def generate_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(16)
    return session["csrf_token"]

def validate_csrf(token):
    return token and session.get("csrf_token") == token

# Make csrf_token available in templates via function
app.jinja_env.globals["csrf_token"] = generate_csrf_token

# -------------------------
# Auth helpers
# -------------------------
EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")
def valid_email(email: str):
    return bool(EMAIL_RE.match(email))

def valid_password(password: str):
    # Minimum 8 characters, at least 1 letter and 1 digit
    if not password or len(password) < 8: return False
    if not re.search(r"[A-Za-z]", password): return False
    if not re.search(r"\d", password): return False
    return True

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        db = get_db()
        user = db.execute("SELECT role FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if not user or user["role"] != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper

# -------------------------
# Auto-create admin on startup (safe: only if not exists)
# -------------------------
def ensure_admin_exists():
    db = get_db()
    row = db.execute("SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,)).fetchone()
    if row:
        print("✔ Admin already exists")
        return
    hashed = generate_password_hash(ADMIN_PWD)
    db.execute(
        "INSERT INTO users (email, hash, role, name, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (ADMIN_EMAIL, hashed, "admin", ADMIN_NAME)
    )
    db.commit()
    print(f"🎉 Admin created: {ADMIN_EMAIL}")

# Run admin ensure on app startup
with app.app_context():
    # only run if DB exists and schema present; otherwise skip to avoid errors
    if os.path.exists(DB):
        try:
            ensure_admin_exists()
        except Exception as e:
            # print error but do not crash app startup
            print("Warning: could not ensure admin exists:", e)

# -------------------------
# Helper utilities
# -------------------------
def generate_number(prefix="INV"):
    """Simple invoice/quote number generator (timestamp-based)."""
    return f"{prefix}-{int(datetime.utcnow().timestamp())}"

# -------------------------
# ROUTES - Public pages
# -------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/projects")
def projects():
    db = get_db()
    projects = db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return render_template("projects.html", projects=projects)

@app.route("/contact", methods=["GET","POST"])
def contact():
    t = load_translation(session.get("lang","fr"))
    if request.method == "POST":
        # CSRF
        if not validate_csrf(request.form.get("csrf_token")):
            flash("CSRF token missing or invalid", "danger")
            return redirect(url_for("contact"))

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not message:
            flash(t.get("contact_error_empty", "Veuillez remplir tous les champs."), "danger")
            return render_template("contact.html")

        # store as a message to admin (receiver_id = admin)
        db = get_db()
        # find admin id (first admin)
        admin = db.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        admin_id = admin["id"] if admin else None
        db.execute(
            "INSERT INTO messages (sender_id, receiver_id, content, date) VALUES (?, ?, ?, ?)",
            (0, admin_id if admin_id else 0, f"{name} ({email}): {message}", datetime.utcnow().isoformat())
        )
        db.commit()
        flash(t.get("contact_success", "Merci, votre message a été envoyé."), "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")

@app.route("/tarifs")
def tarifs():
    return render_template("tarifs.html")

# -------------------------
# AUTH - register / login / logout / change_password
# -------------------------
@app.route("/register", methods=["GET","POST"])
def register():
    t = load_translation(session.get("lang","fr"))
    if request.method == "POST":
        if not validate_csrf(request.form.get("csrf_token")):
            flash("CSRF token missing or invalid", "danger")
            return redirect(url_for("register"))

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        name = request.form.get("name", "").strip()

        if not valid_email(email):
            flash(t.get("register_error_email", "Adresse email invalide."), "danger")
            return render_template("register.html")
        if password != password2:
            flash(t.get("register_error_password_mismatch", "Les mots de passe ne correspondent pas."), "danger")
            return render_template("register.html")
        if not valid_password(password):
            flash(t.get("register_error_password_strength", "Mot de passe trop faible."), "danger")
            return render_template("register.html")

        db = get_db()
        try:
            db.execute("INSERT INTO users (email, hash, role, name, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
                       (email, generate_password_hash(password), "client", name if name else None))
            db.commit()
            flash(t.get("register_success", "Compte créé ! Connectez-vous."), "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash(t.get("register_error_exists", "Adresse email déjà utilisée."), "danger")
            return render_template("register.html")
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    t = load_translation(session.get("lang","fr"))
    if request.method == "POST":
        if not validate_csrf(request.form.get("csrf_token")):
            flash("CSRF token missing or invalid", "danger")
            return redirect(url_for("login"))

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute("SELECT id, email, hash, role FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["hash"], password):
            lang = session.get("lang", "fr")
            session.clear()
            session.permanent = True
            session["lang"] = lang
            session["user_id"] = user["id"]
            session["user_email"] = user["email"]
            session["user_role"] = user["role"]
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        else:
            flash(t.get("login_error", "Email ou mot de passe incorrect."), "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    lang = session.get("lang", "fr")
    session.clear()
    session["lang"] = lang
    return redirect(url_for("index"))

@app.route("/change_password", methods=["GET","POST"])
@login_required
def change_password():
    t = load_translation(session.get("lang","fr"))
    if request.method == "POST":
        if not validate_csrf(request.form.get("csrf_token")):
            flash("CSRF token missing or invalid", "danger")
            return redirect(url_for("change_password"))

        current = request.form.get("current", "")
        new = request.form.get("new", "")
        new2 = request.form.get("new2", "")

        db = get_db()
        user = db.execute("SELECT hash FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if not user or not check_password_hash(user["hash"], current):
            flash(t.get("change_password_error_current", "Mot de passe actuel incorrect."), "danger")
            return render_template("change_password.html")
        if new != new2 or not valid_password(new):
            flash(t.get("change_password_error_new", "Nouveau mot de passe invalide."), "danger")
            return render_template("change_password.html")
        db.execute("UPDATE users SET hash = ? WHERE id = ?", (generate_password_hash(new), session["user_id"]))
        db.commit()
        flash(t.get("change_password_success", "Mot de passe changé."), "success")
        return redirect(url_for("dashboard"))
    return render_template("change_password.html")

# -------------------------
# Client dashboard (quotes + invoices)
# -------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    t = load_translation(session.get("lang","fr"))
    db = get_db()
    quotes = db.execute("SELECT * FROM quotes WHERE user_id = ? ORDER BY date DESC", (session["user_id"],)).fetchall()
    invoices = db.execute("SELECT * FROM invoices WHERE user_id = ? ORDER BY date DESC", (session["user_id"],)).fetchall()
    return render_template("dashboard.html", quotes=quotes, invoices=invoices)

# -------------------------
# Invoice PDF generation (download)
# -------------------------
@app.route("/invoice/<int:invoice_id>/pdf")
@login_required
def invoice_pdf(invoice_id):
    db = get_db()
    inv = db.execute("SELECT * FROM invoices WHERE id = ? AND user_id = ?", (invoice_id, session["user_id"])).fetchone()
    if not inv:
        flash("Facture introuvable.", "danger")
        return redirect(url_for("dashboard"))

    # Create PDF in memory
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, 800, f"Facture #{inv['number']}")
    p.setFont("Helvetica", 12)
    p.drawString(50, 770, f"Client ID: {inv['user_id']}")
    p.drawString(50, 750, f"Montant: {inv['amount']} €")
    p.drawString(50, 730, f"Date: {inv['date']}")
    p.drawString(50, 710, f"Statut: {inv['status']}")
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"invoice_{inv['number']}.pdf", mimetype="application/pdf")

# -------------------------
# Messaging (client <-> admin)
# -------------------------
@app.route("/messages", methods=["GET","POST"])
@login_required
def messages():
    t = load_translation(session.get("lang","fr"))
    db = get_db()
    user_id = session["user_id"]
    # find admin id (first admin)
    admin = db.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
    admin_id = admin["id"] if admin else None

    if request.method == "POST":
        if not validate_csrf(request.form.get("csrf_token")):
            flash("CSRF token missing or invalid", "danger")
            return redirect(url_for("messages"))
        content = request.form.get("message", "").strip()
        if content:
            db.execute("INSERT INTO messages (sender_id, receiver_id, content, date) VALUES (?, ?, ?, ?)",
                       (user_id, admin_id if admin_id else 0, content, datetime.utcnow().isoformat()))
            db.commit()
            flash(t.get("messages_sent", "Message envoyé."), "success")
        else:
            flash(t.get("messages_error_empty", "Message vide."), "danger")
        return redirect(url_for("messages"))

    # show conversation between user and admin (if admin exist)
    if admin_id:
        conv = db.execute("""
            SELECT * FROM messages
            WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)
            ORDER BY date ASC
        """, (user_id, admin_id, admin_id, user_id)).fetchall()
    else:
        conv = []
    return render_template("messages.html", conversation=conv)

# -------------------------
# Admin interface (very basic CRUD/listing)
# -------------------------
@app.route("/admin")
@admin_required
def admin_index():
    db = get_db()
    clients = db.execute("SELECT id, email, name, role, created_at FROM users ORDER BY created_at DESC").fetchall()
    quotes = db.execute("SELECT * FROM quotes ORDER BY date DESC").fetchall()
    invoices = db.execute("SELECT * FROM invoices ORDER BY date DESC").fetchall()
    messages = db.execute("SELECT * FROM messages ORDER BY date DESC").fetchall()
    projects = db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return render_template("admin_dashboard.html", clients=clients, quotes=quotes, invoices=invoices, messages=messages, projects=projects)

# Example admin action: mark invoice as paid
@app.route("/admin/invoice/<int:invoice_id>/set_paid")
@admin_required
def admin_invoice_set_paid(invoice_id):
    db = get_db()
    db.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (invoice_id,))
    db.commit()
    flash("Facture marquée comme payée.", "success")
    return redirect(url_for("admin_index"))

# Admin: create project (simple)
@app.route("/admin/project/create", methods=["GET","POST"])
@admin_required
def admin_project_create():
    if request.method == "POST":
        title_fr = request.form.get("title_fr", "").strip()
        title_en = request.form.get("title_en", "").strip()
        title_es = request.form.get("title_es", "").strip()
        desc_fr = request.form.get("description_fr", "").strip()
        desc_en = request.form.get("description_en", "").strip()
        desc_es = request.form.get("description_es", "").strip()
        link = request.form.get("link", "").strip() or None
        image = request.form.get("image", "").strip() or None
        db = get_db()
        db.execute("""
            INSERT INTO projects
            (title_fr, title_en, title_es, description_fr, description_en, description_es, image, link, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (title_fr, title_en, title_es, desc_fr, desc_en, desc_es, image, link))
        db.commit()
        flash("Projet créé.", "success")
        return redirect(url_for("admin_index"))
    return render_template("admin_create_project.html")

# -------------------------
# Error handlers
# -------------------------
@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, message="Accès refusé"), 403

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Page introuvable"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message="Erreur interne"), 500

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)
