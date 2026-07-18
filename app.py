from flask import Flask, request, jsonify, render_template, redirect, session, url_for, Response, make_response
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
from email.mime.text import MIMEText
import csv
from io import StringIO
from functools import wraps
from dotenv import load_dotenv
import os

# Load .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_secret_change_me")

# =================================================
# DATABASE POOL (PostgreSQL via Render)
# =================================================
DATABASE_URL = os.getenv("DATABASE_URL")

# Fix Render URL format
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

db_pool = None
try:
    db_pool = pool.SimpleConnectionPool(
        minconn=1,
        maxconn=5,
        dsn=DATABASE_URL + "?sslmode=require"
    )
    print("✅ Database connected successfully")
except Exception as e:
    print("❌ Database connection error:", e)


def get_db():
    return db_pool.getconn()


def release_db(conn):
    db_pool.putconn(conn)


# =================================================
# EMAIL CONFIG (from .env)
# =================================================
EMAIL        = os.getenv("EMAIL_SENDER")
APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
TO_EMAIL     = os.getenv("EMAIL_RECEIVER")

# =================================================
# ROLE-BASED SECURITY DECORATOR
# =================================================
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "admin" not in session:
                return redirect(url_for("admin_login"))
            if role and session.get("role") not in role:
                return "Permission Denied", 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


# =================================================
# HOME
# =================================================
@app.route("/")
def home():
    return render_template("index.html")


# =================================================
# CREATE DEFAULT ADMINS (protected — one-time setup only)
# =================================================
# This route used to be public with hardcoded passwords baked into the
# source code, which is a serious security risk on a public GitHub repo.
# It now requires a secret token (set as SETUP_TOKEN in your .env / Render
# environment variables) passed as a query string, e.g.:
#   /create-admin?token=YOUR_SECRET_TOKEN
# Once you've created your real admins, delete this route entirely or
# rotate SETUP_TOKEN so it can't be reused.
@app.route("/create-admin")
def create_admin():
    setup_token = os.getenv("SETUP_TOKEN")
    provided_token = request.args.get("token")

    if not setup_token or provided_token != setup_token:
        return "Not authorized", 403

    admins = [
        ("ceo",     os.getenv("DEFAULT_CEO_PASSWORD", ""),     "CEO"),
        ("manager", os.getenv("DEFAULT_MANAGER_PASSWORD", ""), "Manager"),
        ("sales",   os.getenv("DEFAULT_SALES_PASSWORD", ""),   "Sales"),
    ]

    conn = get_db()
    try:
        cursor = conn.cursor()
        for username, password, role in admins:
            if not password:
                continue
            cursor.execute("SELECT * FROM admins WHERE username=%s", (username,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO admins (username, password, role) VALUES (%s, %s, %s)",
                    (username, generate_password_hash(password), role),
                )
        conn.commit()
        cursor.close()
    finally:
        release_db(conn)
    return "Default admins created (only for accounts with a password set)."


# =================================================
# SUBMIT LEAD
# =================================================
@app.route("/submit", methods=["POST"])
def submit():
    try:
        data = request.get_json()
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO contacts (name, company, phone, email, address, service, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'New')
            """, (
                data["name"], data["company"], data["phone"],
                data["email"], data["address"], data["service"],
            ))
            conn.commit()
            cursor.close()
        finally:
            release_db(conn)

        # Email alert
        try:
            message = f"""
New Lead Received

Name:    {data['name']}
Company: {data['company']}
Phone:   {data['phone']}
Email:   {data['email']}
Service: {data['service']}
"""
            msg = MIMEText(message)
            msg["Subject"] = "New Lead - DDS CRM"
            msg["From"]    = EMAIL
            msg["To"]      = TO_EMAIL
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(EMAIL, APP_PASSWORD)
                server.send_message(msg)
        except Exception as e:
            print("Email error:", e)

        return jsonify({"status": "success"})
    except Exception as e:
        print("Submit error:", e)
        return jsonify({"status": "error"}), 500


# =================================================
# ADMIN LOGIN
# =================================================
@app.route("/admin", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            response = make_response(
                render_template(
                    "admin_login.html",
                    error="Username and password required"
                )
            )

            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

            return response

        conn = get_db()

        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute(
                "SELECT * FROM admins WHERE username=%s",
                (username,)
            )

            admin = cursor.fetchone()
            cursor.close()

        finally:
            release_db(conn)

        # Validate password safely
        valid_login = False

        if admin and admin.get("password"):
            try:
                valid_login = check_password_hash(
                    admin["password"],
                    password
                )

            except (ValueError, TypeError):
                valid_login = False

        if valid_login:

            session["admin"] = admin["username"]
            session["role"] = admin["role"]

            return redirect(url_for("dashboard"))

        response = make_response(
            render_template(
                "admin_login.html",
                error="Invalid credentials"
            )
        )

        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        return response

    # GET request
    response = make_response(
        render_template("admin_login.html")
    )

    # Prevent login page from being stored in browser cache
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response

# =================================================
# DASHBOARD
# =================================================
@app.route("/dashboard")
@login_required()
def dashboard():

    conn = get_db()

    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT * FROM contacts ORDER BY id DESC")
        leads = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) AS total FROM contacts")
        total = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS today
            FROM contacts
            WHERE DATE(created_at) = CURRENT_DATE
        """)
        today = cursor.fetchone()["today"]

        cursor.execute("""
            SELECT COUNT(*) AS new_leads
            FROM contacts
            WHERE status = 'New'
        """)
        new_leads = cursor.fetchone()["new_leads"]

        cursor.close()

    finally:
        release_db(conn)

    return render_template(
        "admin_dashboard.html",
        leads=leads,
        total_leads=total,
        today_leads=today,
        new_leads=new_leads
    )

# =================================================
# UPDATE STATUS
# =================================================
@app.route("/update-status/<int:lead_id>", methods=["POST"])
@login_required(role=["CEO", "Manager"])
def update_status(lead_id):
    status = request.json.get("status")
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE contacts SET status=%s WHERE id=%s", (status, lead_id))
        conn.commit()
        cursor.close()
    finally:
        release_db(conn)
    return jsonify({"success": True})


# =================================================
# DELETE LEAD
# =================================================
@app.route("/delete/<int:lead_id>", methods=["POST"])
@login_required(role=["CEO"])
def delete_lead(lead_id):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contacts WHERE id=%s", (lead_id,))
        conn.commit()
        cursor.close()
    finally:
        release_db(conn)
    return jsonify({"success": True})


# =================================================
# EXPORT CSV
# =================================================
@app.route("/export")
@login_required()
def export_csv():
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM contacts")
        leads = cursor.fetchall()
        cursor.close()
    finally:
        release_db(conn)
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["ID", "Name", "Company", "Phone", "Email", "Service", "Status"])
    for lead in leads:
        writer.writerow([lead["id"], lead["name"], lead["company"],
                         lead["phone"], lead["email"], lead["service"], lead["status"]])
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=crm_leads.csv"},
    )


# =================================================
# LOGOUT
# =================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin_login"))


# =================================================
# SERVICE PAGES
# =================================================
@app.route("/branding")
def branding():
    return render_template("branding.html")


@app.route("/seo")
def seo():
    return render_template("seo.html")


@app.route("/paid-marketing")
def paid_marketing():
    return render_template("paid_marketing.html")


@app.route("/social-media")
def social_media():
    return render_template("social_media.html")


@app.route("/web-development")
def web_development():
    return render_template("web_development.html")


@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/portfolio')
def portfolio():
    return render_template('portfolio.html')


# =================================================
if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1")
