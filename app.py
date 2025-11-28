import sqlite3, re, os, json
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, session, g, request, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback-secret")

# Secure session cookies
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = True

def execute(db, query, params=()):
    """Automatically choose placeholder style depending on DB engine."""
    cur = db.cursor()

    if isinstance(db, sqlite3.Connection):
        # PostgreSQL uses "%s"
        q = query.replace("%s", "?")
        cur.execute(q, params)
    else:
        # SQLite uses "?"
        cur.execute(query, params)
    return cur

def valid_username(username):
    """Allow A-Z, a-z, 0-9, underscore, length 3–20."""
    return re.fullmatch(r"[A-Za-z0-9_]{3,20}", username) is not None

def get_db():
    if "db" not in g:

        # On Render -> use PostgreSQL
        if "DATABASE_URL" in os.environ:
            g.db = psycopg2.connect(
                os.environ["DATABASE_URL"],
                cursor_factory=RealDictCursor
            )
        else:
            # Local development -> SQLite
            g.db = sqlite3.connect("database/users.db", check_same_thread=False)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()

@app.route("/")
def index():
    db = get_db()

    if "user_id" in session:
        failed = execute(db, """
            SELECT COUNT(*) AS c FROM failed_words
            WHERE user_id = %s
        """, (session["user_id"],)).fetchone()
        
        failed_count = failed["c"] if failed else 0
    else:
        failed_count = 0

    return render_template("index.html", failed_count=failed_count)

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect("/")

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        confirm = request.form["confirm_password"]

        if not valid_username(username):
            flash("Invalid username. Use 3–20 letters, numbers, or underscores only.")
            return redirect("/register")


        if password != confirm:
            flash("Passwords do not match!")
            return redirect("/register")

        db = get_db()

        existing = execute(db,
            "SELECT * FROM users WHERE username = %s", (username,)
        ).fetchone()

        if existing:
            flash("Username already taken")
            return redirect("/register")

        hash_pw = generate_password_hash(password)

        execute(db,
            "INSERT INTO users (username, hash) VALUES (%s, %s)",
            (username, hash_pw)
        )
        db.commit()

        flash("Registration successful! Please log in.")
        return redirect("/login")

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect("/")

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()

        user = execute(db,"SELECT * FROM users WHERE username = %s", (username,)).fetchone()
        if not user or not check_password_hash(user["hash"], password):
            flash("Invalid username or password")
            return redirect("/login")

        session["user_id"] = user["id"]
        session["username"] = user["username"]

        return redirect("/")
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

    
@app.route("/save_score", methods=["POST"])
def save_score():
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "not_logged_in"})

    data = request.get_json()
    category = data["category"]
    score = data["score"]
    time = data["time"]

    # Prevent saving failed_words as score
    if category == "failed_words":
        return jsonify({"status": "ignored"})

    db = get_db()

    existing = execute(db,
        "SELECT * FROM scores WHERE user_id = %s AND category = %s",
        (session["user_id"], category)
    ).fetchone()

    if existing:
        if score > existing["best_score"] or (score == existing["best_score"] and time < existing["best_time"]):
            execute(db, """
                UPDATE scores
                SET best_score = %s, best_time = %s
                WHERE id = %s
            """, (score, time, existing["id"]))
    else:
        execute(db, """
            INSERT INTO scores (user_id, category, best_score, best_time)
            VALUES (%s, %s, %s, %s)
        """, (session["user_id"], category, score, time))

    db.commit()
    return jsonify({"status": "ok"})


@app.route("/save_failure", methods=["POST"])
def save_failure():
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "not_logged_in"})

    data = request.get_json()

    category = data["category"]
    word = data["word"]               # German word
    english = data.get("english")     # English meaning
    gender = data.get("gender")       # m/f/n or None

    db = get_db()

    existing = execute(db,
        "SELECT * FROM failed_words WHERE user_id = %s AND word = %s",
        (session["user_id"], word)
    ).fetchone()

    if existing:
        # Update failure count + overwrite metadata in case it's new/updated
        execute(db, """
            UPDATE failed_words
            SET failures = failures + 1,
                english = %s,
                gender = %s,
                category = %s
            WHERE id = %s
        """, (english, gender, category, existing["id"]))
    else:
        # Insert new entry
        execute(db, """
            INSERT INTO failed_words (user_id, category, word, english, gender, failures)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (session["user_id"], category, word, english, gender, 1))

    db.commit()
    return jsonify({"status": "ok"})

@app.route("/api/failed_words")
def get_failed_words():
    if "user_id" not in session:
        return jsonify([])

    db = get_db()
    rows = execute(db, """
        SELECT word, english, gender, category, failures
        FROM failed_words
        WHERE user_id = %s
        ORDER BY failures DESC
    """, (session["user_id"],)).fetchall()

    words = []
    for row in rows:
        words.append({
            "german": row["word"],
            "english": row["english"] or "",
            "gender": row["gender"] or None
        })

    return jsonify(words)

@app.route("/clear_failed_words", methods=["POST"])
def clear_failed_words():
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    execute(db, "DELETE FROM failed_words WHERE user_id = %s", (session["user_id"],))
    db.commit()

    flash("Failed words cleared!")
    return redirect("/account")

@app.route("/clear_best_scores", methods=["POST"])
def clear_best_scores():
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    execute(db, "DELETE FROM scores WHERE user_id = %s", (session["user_id"],))
    db.commit()

    flash("Best Scores cleared!")
    return redirect("/account")

@app.route("/account")
def account():
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()

    # Fetch all stats for this user
    stats = execute(db, """
        SELECT category, best_score, best_time
        FROM scores
        WHERE user_id = %s
        AND category != 'failed_words'
        ORDER BY category
    """, (session["user_id"],)).fetchall()

    # Fetch the user's failed words
    failed = execute(db, """
        SELECT word, failures, category
        FROM failed_words
        WHERE user_id = %s
        ORDER BY failures DESC, word ASC
    """, (session["user_id"],)).fetchall()

    return render_template("account.html",
                           username=session["username"],
                           stats=stats,
                           failed=failed,
                           category_sizes=CATEGORY_SIZES)

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()

    if request.method == "POST":
        sound = bool(request.form.get("sound"))
        theme = request.form.get("theme", "dark")
        custom_color = request.form.get("custom_color")
        speedrun = bool(request.form.get("speedrun"))
        strict = bool(request.form.get("strict_articles"))

        # only keep custom_color when theme = custom
        if theme != "custom":
            custom_color = None

        # INSERT or UPDATE
        execute(db, """
            INSERT INTO user_settings (user_id, theme, sound_enabled, custom_color, speedrun_enabled, strict_articles)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET
                theme = EXCLUDED.theme,
                sound_enabled = EXCLUDED.sound_enabled,
                custom_color = EXCLUDED.custom_color,
                speedrun_enabled = EXCLUDED.speedrun_enabled,
                strict_articles = EXCLUDED.strict_articles
        """, (session["user_id"], theme, sound, custom_color, speedrun, strict))

        db.commit()
        flash("Settings updated!")
        return redirect("/settings")

    # GET
    settings_data = execute(db,
        "SELECT * FROM user_settings WHERE user_id = %s",
        (session["user_id"],)
    ).fetchone()

    if not settings_data:
        execute(db, """
            INSERT INTO user_settings (
                user_id, theme, sound_enabled, custom_color,
                speedrun_enabled, strict_articles
            ) VALUES (%s, 'german', TRUE, NULL, FALSE, FALSE)
        """, (session["user_id"],))
        db.commit()

        # Re-fetch to get the row as dict
        settings_data = execute(db,
            "SELECT * FROM user_settings WHERE user_id = %s",
            (session["user_id"],)
        ).fetchone()

    return render_template("settings.html", settings=settings_data)

@app.route("/api/settings")
def api_settings():
    if "user_id" not in session:
        return jsonify({})
    db = get_db()
    s = execute(db,
        "SELECT * FROM user_settings WHERE user_id = %s",
        (session["user_id"],)
    ).fetchone()
    return jsonify(dict(s) if s else {})

@app.context_processor
def inject_settings():
    if "user_id" not in session:
        # DEFAULTS when logged out
        return {"settings": {
            "theme": "german",
            "sound_enabled": True,
            "strict_articles": False,
            "speedrun_enabled": False,
            "custom_color": None
        }}

    db = get_db()
    s = execute(db,
        "SELECT * FROM user_settings WHERE user_id = %s",
        (session["user_id"],)
    ).fetchone()

    # If user exists but has no settings row yet → return defaults
    if not s:
        return {"settings": {
            "theme": "german",
            "sound_enabled": True,
            "strict_articles": False,
            "speedrun_enabled": False,
            "custom_color": None
        }}

    return {"settings": s}

@app.route("/save_leaderboard", methods=["POST"])
def save_leaderboard():
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "not_logged_in"})

    data = request.get_json()
    category = data["category"]
    score = data["score"]
    time = data["time"]

    db = get_db()

    execute(db, """
        INSERT INTO leaderboard (user_id, username, category, score, time)
        VALUES (%s, %s, %s, %s, %s)
    """, (session["user_id"], session["username"], category, score, time))

    db.commit()
    return jsonify({"status": "ok"})

@app.route("/api/leaderboard/<category>")
def api_leaderboard(category):
    db = get_db()

    rows = execute(db, """
        SELECT username, score, time
        FROM leaderboard
        WHERE category = %s
        AND (user_id, score, time) IN (
            SELECT user_id,
                   MAX(score) AS best_score,
                   MIN(time)  AS best_time
            FROM leaderboard
            WHERE category = %s
            GROUP BY user_id
        )
        ORDER BY score DESC, time ASC
        LIMIT 10
    """, (category, category)).fetchall()

    return jsonify([dict(r) for r in rows])

def load_category_sizes():
    sizes = {}
    data_folder = os.path.join("static", "data")

    for filename in os.listdir(data_folder):
        if filename.endswith(".json"):
            category = filename.replace(".json", "")
            with open(os.path.join(data_folder, filename), "r", encoding="utf-8") as f:
                words = json.load(f)
                sizes[category] = len(words)

    return sizes

CATEGORY_SIZES = load_category_sizes()

if __name__ == "__main__":
    app.run(debug=True)