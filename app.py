import sqlite3, re, os, json, uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, session, g, request, redirect, url_for, flash, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta, date
from PIL import Image, ImageOps, ImageDraw

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback-secret")

# Profile Pictures
UPLOAD_FOLDER = "/var/data/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

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


def resolve_category_key(raw_cat):
    """Resolve a raw category string (from client/DB) to a key present in
    CATEGORY_SIZES. Handles variants like 'colors', 'a1_colors', 'A1_colors',
    and is case-insensitive. Returns the matching key from CATEGORY_SIZES or
    None if no match found.
    """
    if not raw_cat:
        return None

    # direct match
    if raw_cat in CATEGORY_SIZES:
        return raw_cat

    # case-insensitive direct match
    lower_raw = raw_cat.lower()
    for k in CATEGORY_SIZES:
        if k.lower() == lower_raw:
            return k

    # suffix match: e.g., 'A1_colors' endswith '_colors'
    for k in CATEGORY_SIZES:
        if k.lower().endswith("_" + lower_raw):
            return k

    # try common prefix 'A1_'
    candidate = f"A1_{raw_cat}"
    for k in CATEGORY_SIZES:
        if k.lower() == candidate.lower():
            return k

    return None

def calculate_level(xp):
    level = int((xp / 100) ** 0.7) + 1
    return max(level, 1)

def xp_for_next_level(level):
    return int((level ** 1.4) * 120)


def update_streak(user_id):
    db = get_db()

    user = execute(db,
        "SELECT streak, last_active FROM users WHERE id = %s",
        (user_id,)
    ).fetchone()

    today = date.today()

    # If no last_active yet → first login/play ever
    if not user["last_active"]:
        execute(db,
            "UPDATE users SET streak = 1, last_active = %s WHERE id = %s",
            (today, user_id)
        )
        return

    last = datetime.strptime(str(user["last_active"]), "%Y-%m-%d").date()

    # If already played today do nothing
    if last == today:
        return

    # If played yesterday streak continues
    if last == today - timedelta(days=1):
        new_streak = user["streak"] + 1
    else:
        # Missed a day = streak resets
        new_streak = 1

    execute(db,
        "UPDATE users SET streak = %s, last_active = %s WHERE id = %s",
        (new_streak, today, user_id)
    )

def iso_to_emoji(code):
    if not code:
        return ""
    return "".join(chr(127397 + ord(c)) for c in code.upper())

app.jinja_env.filters["country_flag"] = iso_to_emoji

@app.route("/")
def root():
    return redirect("/a1")

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()

@app.route("/a1")
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

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.route("/a1/basics")
def a1_basics():
    return render_template("a1_basics.html", category="basics")

@app.route("/a1/grammar_basics")
def a1_grammar_basics():
    return render_template("a1_grammar_basics.html", category="grammar_basics")

@app.route("/a1/people_daily_life")
def a1_people_daily_life():
    return render_template("a1_people_daily_life.html", category="people_daily_life")

@app.route("/a1/objects_things")
def a1_objects_things():
    return render_template("a1_objects_things.html", category="objects_things")

@app.route("/a1/environment")
def a1_environment():
    return render_template("a1_environment.html", category="environment")

@app.route("/a1/verbs")
def a1_verbs():
    return render_template("a1_verbs.html", category="verbs")

@app.route("/a1/adjectives")
def a1_adjectives():
    return render_template("a1_adjectives.html", category="adjectives")

@app.route("/a1/marathon")
def marathon():
    return render_template("a1_marathon.html")

@app.route("/api/progress")
def api_progress():
    if "user_id" not in session:
        return jsonify({})

    db = get_db()

    rows = execute(db, """
        SELECT category, best_score
        FROM scores
        WHERE user_id = %s
    """, (session["user_id"],)).fetchall()

    result = {}

    for row in rows:
        raw_cat = row["category"]
        if not raw_cat:
            continue

        # Resolve to canonical key like A1_colors, A1_marathon
        key = resolve_category_key(raw_cat)
        if not key:
            continue

        # How many words total
        total_words = CATEGORY_SIZES.get(key, 0)
        best_score = row["best_score"] or 0

        percent = int((best_score / total_words) * 100) if total_words else 0

        # Use canonical lowercase key → a1_colors, a1_marathon
        result[key.lower()] = percent

    return jsonify(result)


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect("/")

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        confirm = request.form["confirm_password"]

        if not valid_username(username):
            return redirect("/register")

        if password != confirm:
            flash("Passwords do not match")
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
    category = data.get("category", "").strip()
    score = data["score"]
    time = data["time"]

    if not category or score is None or time is None:
        return jsonify({"error": "missing_data"}), 400

    if "marathon" in category:
        category = "a1_marathon"

    # Prevent saving failed_words as score
    if category == "failed_words":
        return jsonify({"status": "ignored"})

    db = get_db()

    update_streak(session["user_id"])

    existing = execute(db,
        "SELECT * FROM scores WHERE user_id = %s AND category = %s",
        (session["user_id"], category)
    ).fetchone()

    earned_new_record = False

    if existing:
        if score > existing["best_score"] or (score == existing["best_score"] and time < existing["best_time"]):
            earned_new_record = True
            execute(db, """
                UPDATE scores
                SET best_score = %s, best_time = %s
                WHERE id = %s
            """, (score, time, existing["id"]))
    else:
        earned_new_record = True
        execute(db, """
            INSERT INTO scores (user_id, category, best_score, best_time)
            VALUES (%s, %s, %s, %s)
        """, (session["user_id"], category, score, time))

    if not earned_new_record:
        db.commit()
        return jsonify({"status": "no_xp"})

    # XP system

    # category size from preloaded dictionary
    # resolve category to canonical key (e.g., 'colors' -> 'A1_colors')
    resolved_key = resolve_category_key(category) or category
    total_words = CATEGORY_SIZES.get(resolved_key, 1)
    percent = int((score / total_words) * 100)

    # speed bonus
    speed_bonus = 0
    if time < 40:
        speed_bonus = 20
    elif time < 70:
        speed_bonus = 10

    xp_gain = percent + speed_bonus

    # fetch current XP/Level
    user = execute(db,
        "SELECT xp, level, next_level_xp, streak FROM users WHERE id = %s",
        (session["user_id"],)
    ).fetchone()

    current_xp = user["xp"]
    level = user["level"]
    next_req = user["next_level_xp"]
    streak = user["streak"]

    # GIVE XP
    current_xp += xp_gain

    # HANDLE LEVEL UPS
    while current_xp >= next_req:
        current_xp -= next_req
        level += 1
        next_req = int(next_req * 1.25)  # increasing curve

    # update user XP and level
    execute(db, """
        UPDATE users
        SET xp = %s, level = %s, next_level_xp = %s
        WHERE id = %s
    """, (current_xp, level, next_req, session["user_id"]))

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
    plural = data.get("plural")       # plural form or None

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
                plural = %s,
                category = %s
            WHERE id = %s
        """, (english, gender, plural, category, existing["id"]))
    else:
        # Insert new entry
        execute(db, """
            INSERT INTO failed_words (user_id, category, word, english, gender, plural, failures)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (session["user_id"], category, word, english, gender, plural, 1))

    db.commit()
    return jsonify({"status": "ok"})

@app.route("/api/failed_words")
def get_failed_words():
    if "user_id" not in session:
        return jsonify([])

    db = get_db()
    rows = execute(db, """
        SELECT word, english, gender, plural, category, failures
        FROM failed_words
        WHERE user_id = %s
        ORDER BY failures DESC
    """, (session["user_id"],)).fetchall()

    words = []
    for row in rows:
        words.append({
            "german": row["word"],
            "english": row["english"] or "",
            "gender": row["gender"] or None,
            "plural": row["plural"] or None
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

@app.route("/change_username", methods=["POST"])
def change_username():
    if "user_id" not in session:
        return redirect("/login")

    new_username = request.form.get("new_username", "").strip()

    if not valid_username(new_username):
        flash("Invalid username. Use 3–20 letters, numbers, or underscores.")
        return redirect("/account")

    db = get_db()

    # Check if username is taken
    existing = execute(db,
        "SELECT id FROM users WHERE username = %s",
        (new_username,)
    ).fetchone()

    if existing:
        flash("That username is already taken.")
        return redirect("/account")

    # Update username
    execute(db,
        "UPDATE users SET username = %s WHERE id = %s",
        (new_username, session["user_id"])
    )
    db.commit()

    # Update session
    session["username"] = new_username

    flash("Username updated!")
    return redirect("/account")

@app.route("/change_bio", methods=["POST"])
def change_bio():
    if "user_id" not in session:
        return redirect("/login")

    new_bio = request.form.get("bio", "").strip()

    # Optional: limit length
    if len(new_bio) > 150:
        flash("Bio must be 150 characters or less.")
        return redirect("/account")

    db = get_db()
    execute(db,
        "UPDATE users SET bio = %s WHERE id = %s",
        (new_bio, session["user_id"])
    )
    db.commit()

    flash("Bio updated!")
    return redirect("/account")

@app.route("/delete_account", methods=["POST"])
def delete_account():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    db = get_db()

    # 1. Remove avatar file if exists
    user = execute(db, "SELECT avatar FROM users WHERE id = %s", (user_id,)).fetchone()
    if user and user["avatar"]:
        avatar_path = os.path.join(UPLOAD_FOLDER, user["avatar"])
        if os.path.exists(avatar_path):
            try:
                os.remove(avatar_path)
            except:
                pass  # safe fallback

    # 2. Delete related database entries
    execute(db, "DELETE FROM failed_words WHERE user_id = %s", (user_id,))
    execute(db, "DELETE FROM scores WHERE user_id = %s", (user_id,))
    execute(db, "DELETE FROM leaderboard WHERE user_id = %s", (user_id,))

    # 3. Delete user
    execute(db, "DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()

    # 4. Log out
    session.clear()

    # 5. Flash message
    flash("Your account has been permanently deleted.")

    return redirect("/login")

@app.route("/update_country", methods=["POST"])
def update_country():
    if "user_id" not in session:
        return redirect("/login")

    country = request.form.get("country") or None

    if country and len(country) == 2:
        pass
    else:
        country = None

    db = get_db()
    execute(db, "UPDATE users SET country=%s WHERE id=%s",
            (country, session["user_id"]))
    db.commit()

    flash("Country updated!")
    return redirect("/account")

@app.route("/account")
def account():
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()

    # Load user data
    user = execute(db,
        "SELECT id, username, avatar, xp, level, next_level_xp, streak, bio FROM users WHERE id = %s",
        (session["user_id"],)
    ).fetchone()

    # Fetch all stats for this user
    raw_stats = execute(db, """
        SELECT category, best_score, best_time
        FROM scores
        WHERE user_id = %s
        AND category != 'failed_words'
        ORDER BY category
    """, (session["user_id"],)).fetchall()

    processed_stats = []
    for row in raw_stats:
        raw_cat = row["category"]                         # "colors"
        resolved = resolve_category_key(raw_cat) or raw_cat  # "A1_colors"

        total_words = CATEGORY_SIZES.get(resolved, 0)

        processed_stats.append({
            "raw": raw_cat,
            "category": resolved,                         # proper normalized key
            "best_score": row["best_score"],
            "best_time": row["best_time"],
            "total_words": total_words
        })

    # Fetch the user's failed words
    failed = execute(db, """
        SELECT word, failures, category
        FROM failed_words
        WHERE user_id = %s
        ORDER BY failures DESC, word ASC
    """, (session["user_id"],)).fetchall()

    return render_template("account.html",
                           profile=user,
                           stats=processed_stats,
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
        show_examples = bool(request.form.get("show_examples"))
        plurals = bool(request.form.get("plurals"))

        # only keep custom_color when theme = custom
        if theme != "custom":
            custom_color = None

        # INSERT or UPDATE
        execute(db, """
            INSERT INTO user_settings (user_id, theme, sound_enabled, custom_color, speedrun_enabled, strict_articles, show_examples, plurals)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET
                theme = EXCLUDED.theme,
                sound_enabled = EXCLUDED.sound_enabled,
                custom_color = EXCLUDED.custom_color,
                speedrun_enabled = EXCLUDED.speedrun_enabled,
                strict_articles = EXCLUDED.strict_articles,
                show_examples = EXCLUDED.show_examples,
                plurals = EXCLUDED.plurals
        """, (session["user_id"], theme, sound, custom_color, speedrun, strict, show_examples, plurals))

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
                speedrun_enabled, strict_articles, show_examples, plurals
            ) VALUES (%s, 'german', TRUE, NULL, FALSE, FALSE, TRUE, FALSE)
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
            "custom_color": None,
            "show_examples": True,
            "plurals": False
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
            "custom_color": None,
            "show_examples": True,
            "plurals": False
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
    resolved_key = resolve_category_key(category) or category
    total = CATEGORY_SIZES.get(resolved_key, 0)

    if score != total:
        return jsonify({"status": "ignored"})

    db = get_db()

    execute(db, """
        INSERT INTO leaderboard (user_id, username, category, score, time)
        VALUES (%s, %s, %s, %s, %s)
    """, (session["user_id"], session["username"], resolved_key, score, time))

    db.commit()
    return jsonify({"status": "ok"})

@app.route("/api/leaderboard/<category>")
def api_leaderboard(category):
    db = get_db()

    resolved_key = resolve_category_key(category) or category
    total = CATEGORY_SIZES.get(resolved_key, 0)

    rows = execute(db, """
        SELECT username, MIN(time) AS time
        FROM leaderboard
        WHERE category = %s
        AND score = %s
        GROUP BY username
        ORDER BY time ASC
        LIMIT 10;
    """, (resolved_key, total)).fetchall()

    return jsonify([dict(r) for r in rows])

def load_category_sizes():
    base_path = "static/data"
    sizes = {}

    for level in os.listdir(base_path):
        level_path = os.path.join(base_path, level)

        if not os.path.isdir(level_path):
            continue

        for file in os.listdir(level_path):
            if file.endswith(".json"):
                category_name = f"{level}_{file[:-5]}"
                full_path = os.path.join(level_path, file)

                with open(full_path, "r", encoding="utf8") as f:
                    data = json.load(f)
                    sizes[category_name] = len(data)

    return sizes

CATEGORY_SIZES = load_category_sizes()
CATEGORY_SIZES["a1_marathon"] = 200

@app.route("/api/a1_files")
def api_a1_files():
    base = "static/data/A1"
    files = []

    for file in os.listdir(base):
        if file.endswith(".json"):
            files.append(file[:-5])  # remove .json

    return jsonify(files)

@app.route("/u/<username>")
def public_profile(username):
    db = get_db()

    # Check user exists
    user = execute(db,
        """SELECT id, username, xp, level, next_level_xp, streak, bio, avatar, country
        FROM users
        WHERE username = %s""",
        (username,)
    ).fetchone()


    if not user:
        return render_template("404.html"), 404

    # Load raw stats
    raw_stats = execute(db, """
        SELECT category, best_score, best_time
        FROM scores
        WHERE user_id = %s
        AND category != 'failed_words'
        ORDER BY category
    """, (user["id"],)).fetchall()

    # Process stats
    processed_stats = []
    for row in raw_stats:
        raw_cat = row["category"]                       # e.g. "colors"
        resolved = resolve_category_key(raw_cat) or raw_cat  # e.g. "A1_colors"

        total_words = CATEGORY_SIZES.get(resolved, 0)

        processed_stats.append({
            "raw": raw_cat,             # what user answered in
            "category": resolved,       # normalized for lookup
            "best_score": row["best_score"],
            "best_time": row["best_time"],
            "total_words": total_words
        })

    # XP progress bar
    xp = user["xp"]
    next_xp = user["next_level_xp"]
    xp_percent = min(int((xp / next_xp) * 100), 100) if next_xp > 0 else 0

    # Determine global rank
    ranked_users = execute(db, """
        SELECT id
        FROM users
        ORDER BY level DESC, xp DESC, streak DESC, created_at ASC
    """).fetchall()

    rank = 1
    for row in ranked_users:
        if row["id"] == user["id"]:
            break
        rank += 1

    return render_template("public_profile.html",
                           profile=user,
                           stats=processed_stats,
                           xp_percent=xp_percent,
                           rank=rank,
                           category_sizes=CATEGORY_SIZES)

@app.route("/rankings")
def global_rankings():
    db = get_db()

    # Fetch all users
    users = execute(db, """
        SELECT id, username, level, xp, streak, country, created_at
        FROM users
        ORDER BY level DESC, xp DESC, streak DESC, created_at ASC
        LIMIT 100
    """).fetchall()

    # Compute rank numbers (1-based)
    ranked = []
    rank = 1
    for u in users:
        ranked.append({
            "rank": rank,
            "username": u["username"],
            "level": u["level"],
            "xp": u["xp"],
            "streak": u["streak"],
            "country": u["country"],
        })
        rank += 1

    return render_template("rankings.html", users=ranked)

@app.route("/upload_avatar", methods=["POST"])
def upload_avatar():
    if "user_id" not in session:
        return redirect(url_for("login"))

    file = request.files.get("avatar")
    if not file or file.filename == "":
        flash("No file selected.")
        return redirect(request.referrer or url_for("account"))

    if not allowed_file(file.filename):
        flash("Unsupported file type.")
        return redirect(request.referrer or url_for("account"))

    # Generate *.png filename
    filename = secure_filename(f"{session['user_id']}_{uuid.uuid4().hex}.png")
    save_path = os.path.join(UPLOAD_FOLDER, filename)

    try:
        img = Image.open(file.stream).convert("RGBA")

        size = 256
        img = ImageOps.fit(img, (size, size), Image.LANCZOS)

        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size, size), fill=255)
        img.putalpha(mask)

        img.save(save_path, format="PNG")

    except Exception as e:
        print("Avatar processing error:", e)
        flash("There was a problem processing your image.")
        return redirect(request.referrer or url_for("account"))

    # Store only the filename
    db = get_db()
    execute(db, "UPDATE users SET avatar = %s WHERE id = %s",
            (filename, session["user_id"]))
    db.commit()

    flash("Profile picture updated!")
    return redirect(url_for("account"))

@app.route("/api/failed_words_count")
def api_failed_words_count():
    if "user_id" not in session:
        return jsonify({"count": 0})

    db = get_db()
    row = execute(db, """
        SELECT COUNT(*) AS c
        FROM failed_words
        WHERE user_id = %s
    """, (session["user_id"],)).fetchone()

    count = row["c"] if row else 0
    return jsonify({"count": count})

if __name__ == "__main__":
    app.run(debug=True)