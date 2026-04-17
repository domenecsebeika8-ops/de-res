import os as _os
if _os.environ.get("DATABASE_URL"):
    try:
        import eventlet
        eventlet.monkey_patch()
    except ImportError:
        pass

from flask import (Flask, render_template, request, jsonify,
                   send_from_directory, redirect, url_for)
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import (LoginManager, UserMixin, login_user,
                         logout_user, login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
try:
    from flask_compress import Compress as _Compress
    _has_compress = True
except ImportError:
    _has_compress = False
from werkzeug.utils import secure_filename
import os, sys, uuid, threading, webbrowser, sqlite3
from datetime import datetime
from functools import wraps

if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
    DATA_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)

DB_PATH    = os.path.join(DATA_DIR, "deures.db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

DATABASE_URL  = os.environ.get("DATABASE_URL")
VAPID_PUBLIC  = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS  = {"sub": "mailto:admin@deures.app"}

if DATABASE_URL:
    import psycopg2, psycopg2.extras
    from psycopg2 import pool as pg_pool

    # Connection pool: reuse connections instead of open/close per request
    _pg_pool = pg_pool.ThreadedConnectionPool(1, 10, DATABASE_URL)

    class _PooledConn:
        """Wrapper that returns connection to pool on .close()"""
        def __init__(self):
            self._conn = _pg_pool.getconn()
            self._conn.autocommit = False
        def cursor(self, **kw):     return self._conn.cursor(**kw)
        def commit(self):           self._conn.commit()
        def rollback(self):         self._conn.rollback()
        def close(self):            _pg_pool.putconn(self._conn)

    def get_db():
        return _PooledConn()
    def dbq(db, sql, p=()):
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql.replace("?","%s"), p); return cur
    def dbscalar(db, sql, p=()):
        cur = db.cursor(); cur.execute(sql.replace("?","%s"), p)
        row = cur.fetchone(); return row[0] if row else None
    def dbmany(db, sql, rows):
        db.cursor().executemany(sql.replace("?","%s"), rows)
    ID_COL = "id SERIAL PRIMARY KEY"
    TSTAMP = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
else:
    def get_db():
        c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row; return c
    def dbq(db, sql, p=()):
        return db.execute(sql, p)
    def dbscalar(db, sql, p=()):
        row = db.execute(sql, p).fetchone(); return row[0] if row else None
    def dbmany(db, sql, rows):
        db.executemany(sql, rows)
    ID_COL = "id INTEGER PRIMARY KEY AUTOINCREMENT"
    TSTAMP = "TEXT DEFAULT CURRENT_TIMESTAMP"

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))
app.config["SECRET_KEY"]         = "deures_2025_secret"
app.config["UPLOAD_FOLDER"]      = UPLOAD_DIR
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.config["COMPRESS_MIMETYPES"] = [
    "text/html","text/css","application/javascript","application/json","image/svg+xml"]
app.config["COMPRESS_LEVEL"]     = 6
app.config["COMPRESS_MIN_SIZE"]  = 500

if _has_compress:
    _Compress(app)

async_mode    = "eventlet" if DATABASE_URL else "threading"
socketio      = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)
login_manager = LoginManager(app)
login_manager.login_view    = "login"
login_manager.login_message = "Debes iniciar sesion."

DEFAULT_ROOMS = [
    ("general",    "General",      "\U0001f4ac"),
    ("catala",     "Catala",       "\U0001f434"),
    ("mates",      "Matematicas",  "\U0001f4d0"),
    ("lengua",     "Lengua",       "\U0001f4d6"),
    ("ingles",     "Ingles",       "\U0001f30d"),
    ("ciencias",   "Ciencias",     "\U0001f52c"),
    ("historia",   "Historia",     "\U0001f3db"),
    ("geo",        "Geografia",    "\U0001f5fa"),
    ("fisica",     "Fisica",       "\u269b"),
    ("quimica",    "Quimica",      "\U0001f9ea"),
    ("tecnologia", "Tecnologia",   "\U0001f4bb"),
]

def init_db():
    db = get_db()
    dbq(db, f"""CREATE TABLE IF NOT EXISTS users (
        {ID_COL},
        email         TEXT UNIQUE NOT NULL,
        nickname      TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role          TEXT DEFAULT 'user',
        banned        INTEGER DEFAULT 0,
        created_at    {TSTAMP}
    )""")
    dbq(db, f"""CREATE TABLE IF NOT EXISTS rooms (
        id         TEXT PRIMARY KEY,
        name       TEXT NOT NULL,
        emoji      TEXT DEFAULT '\U0001f4ac',
        created_at {TSTAMP}
    )""")
    dbq(db, f"""CREATE TABLE IF NOT EXISTS friendships (
        {ID_COL},
        requester_id INTEGER NOT NULL,
        addressee_id INTEGER NOT NULL,
        status       TEXT DEFAULT 'pending',
        created_at   {TSTAMP},
        UNIQUE(requester_id, addressee_id)
    )""")
    dbq(db, f"""CREATE TABLE IF NOT EXISTS push_subs (
        {ID_COL},
        user_id   INTEGER NOT NULL,
        endpoint  TEXT NOT NULL UNIQUE,
        p256dh    TEXT NOT NULL,
        auth      TEXT NOT NULL,
        created_at {TSTAMP}
    )""")
    dbq(db, f"""CREATE TABLE IF NOT EXISTS tasks (
        {ID_COL},
        room_id    TEXT NOT NULL,
        title      TEXT NOT NULL,
        done       INTEGER DEFAULT 0,
        created_by INTEGER,
        created_at {TSTAMP}
    )""")
    dbq(db, f"""CREATE TABLE IF NOT EXISTS groups_tbl (
        {ID_COL},
        name       TEXT NOT NULL,
        emoji      TEXT DEFAULT '\U0001f465',
        created_by INTEGER,
        created_at {TSTAMP}
    )""")
    dbq(db, f"""CREATE TABLE IF NOT EXISTS group_members (
        group_id   INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        PRIMARY KEY (group_id, user_id)
    )""")
    # Indexes — safe to run on every startup (IF NOT EXISTS)
    dbq(db, "CREATE INDEX IF NOT EXISTS idx_friends_req  ON friendships(requester_id)")
    dbq(db, "CREATE INDEX IF NOT EXISTS idx_friends_addr ON friendships(addressee_id)")
    dbq(db, "CREATE INDEX IF NOT EXISTS idx_tasks_room   ON tasks(room_id)")
    dbq(db, "CREATE INDEX IF NOT EXISTS idx_push_user    ON push_subs(user_id)")
    db.commit()
    try:
        dbq(db, "ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT ''")
        db.commit()
    except Exception:
        db.rollback()
    try:
        dbq(db, "ALTER TABLE tasks ADD COLUMN due_date TEXT DEFAULT NULL")
        db.commit()
    except Exception:
        db.rollback()
    if dbscalar(db, "SELECT COUNT(*) FROM rooms") == 0:
        dbmany(db, "INSERT INTO rooms (id,name,emoji) VALUES (?,?,?)", DEFAULT_ROOMS)
    db.commit(); db.close()

init_db()

# ── Periodic in-memory cleanup ────────────────────────────────────────────────
def _cleanup_rooms():
    """Remove empty entries from tracking dicts every hour to prevent RAM leak."""
    for d in (room_users, room_sids):
        for k in [k for k, v in d.items() if not v]:
            d.pop(k, None)
    active = set(room_sids)
    for k in [k for k in list(room_host) if k not in active]:
        room_host.pop(k, None)
    threading.Timer(3600, _cleanup_rooms).start()

threading.Timer(3600, _cleanup_rooms).start()

_rooms_cache = None  # rooms rarely change — cache in memory
def get_rooms(invalidate=False):
    global _rooms_cache
    if _rooms_cache is None or invalidate:
        db   = get_db()
        _rooms_cache = [dict(r) for r in dbq(db, "SELECT * FROM rooms ORDER BY created_at").fetchall()]
        db.close()
    return _rooms_cache

def get_friends(user_id):
    db = get_db()
    rows = dbq(db, """
        SELECT u.id, u.nickname FROM friendships f
        JOIN users u ON (
            CASE WHEN f.requester_id=? THEN f.addressee_id ELSE f.requester_id END = u.id
        )
        WHERE (f.requester_id=? OR f.addressee_id=?) AND f.status='accepted'
    """, (user_id, user_id, user_id)).fetchall()
    db.close()
    return [dict(r) for r in rows]

def get_groups(user_id):
    db = get_db()
    rows = dbq(db, """
        SELECT g.id, g.name, g.emoji, g.created_by FROM groups_tbl g
        JOIN group_members gm ON g.id = gm.group_id
        WHERE gm.user_id=?
        ORDER BY g.created_at
    """, (user_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

def get_group_members(group_id):
    db = get_db()
    rows = dbq(db, """
        SELECT u.id, u.nickname, u.avatar FROM users u
        JOIN group_members gm ON u.id = gm.user_id
        WHERE gm.group_id=?
    """, (group_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

def send_push(user_id, title, body, url="/"):
    if not VAPID_PUBLIC or not VAPID_PRIVATE:
        print("[PUSH] VAPID keys not configured", flush=True)
        return
    try:
        from pywebpush import webpush, WebPushException
        import json as _json
        db   = get_db()
        subs = dbq(db, "SELECT endpoint, p256dh, auth FROM push_subs WHERE user_id=?",
                   (user_id,)).fetchall()
        db.close()
        print(f"[PUSH] Sending to user {user_id}, {len(subs)} subscription(s)", flush=True)
        for s in subs:
            try:
                webpush(
                    subscription_info={"endpoint": s["endpoint"],
                                       "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}},
                    data=_json.dumps({"title": title, "body": body, "url": url}),
                    vapid_private_key=VAPID_PRIVATE,
                    vapid_claims=VAPID_CLAIMS
                )
                print(f"[PUSH] Sent OK to {s['endpoint'][:60]}", flush=True)
            except Exception as e:
                err_str = str(e)
                print(f"[PUSH] Error sending: {err_str}", flush=True)
                if "410" in err_str or "unsubscribed" in err_str.lower():
                    try:
                        db2 = get_db()
                        dbq(db2, "DELETE FROM push_subs WHERE endpoint=?", (s["endpoint"],))
                        db2.commit(); db2.close()
                        print(f"[PUSH] Removed expired subscription", flush=True)
                    except Exception:
                        pass
    except Exception as e:
        print(f"[PUSH] Fatal error: {e}", flush=True)

class User(UserMixin):
    def __init__(self, row):
        self.id       = row["id"]
        self.email    = row["email"]
        self.nickname = row["nickname"]
        self.role     = row["role"]
        self.banned   = row["banned"]
        self.avatar   = row["avatar"] if "avatar" in row.keys() else ""
    @property
    def is_admin(self):  return self.role == "admin"
    @property
    def is_active(self): return not bool(self.banned)

@login_manager.user_loader
def load_user(uid):
    db  = get_db()
    row = dbq(db, "SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    db.close()
    return User(row) if row else None

def admin_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for("index"))
        return f(*a, **kw)
    return dec

@app.context_processor
def inject_vapid():
    av = current_user.avatar if current_user.is_authenticated and hasattr(current_user, "avatar") else ""
    return {"vapid_public_key": VAPID_PUBLIC, "current_avatar": av}

ALLOWED = {"png","jpg","jpeg","gif","webp","pdf","doc","docx","txt"}
def allowed(fn):  return "." in fn and fn.rsplit(".",1)[1].lower() in ALLOWED
def is_img(fn):   return fn.rsplit(".",1)[-1].lower() in {"png","jpg","jpeg","gif","webp"}

MSG_LIMIT    = 60
room_msgs    = {}
room_users   = {}
sid_rooms    = {}
online_users = {}
room_sids    = {}   # room → {sid: {uid, nickname, join_order}}
room_host    = {}   # room → host_sid
_join_counter = 0   # global counter for join order

def make_msg(kind, uid=None, nick="", text="", furl="", fname="", img=False, reply_to=None, avatar="", time=None):
    # Only include non-empty/non-default fields to minimize payload size (saves egress)
    # time comes from the client so it always shows the user's local timezone
    m = {"id": str(uuid.uuid4()), "kind": kind, "user_id": uid,
         "nickname": nick, "time": time if time else datetime.now().strftime("%H:%M")}
    if text:      m["text"]      = text
    if furl:      m["file_url"]  = furl
    if fname:     m["file_name"] = fname
    if img:       m["is_img"]    = True
    if avatar:    m["avatar"]    = avatar
    if reply_to:  m["reply_to"]  = reply_to
    return m

def dm_room(a, b):
    return "dm_{}_{}".format(min(a,b), max(a,b))

@app.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        pw    = request.form.get("password","")
        db    = get_db()
        row   = dbq(db, "SELECT * FROM users WHERE email=?", (email,)).fetchone()
        db.close()
        if row and check_password_hash(row["password_hash"], pw):
            if row["banned"]:
                error = "Tu cuenta ha sido suspendida por un administrador."
            else:
                login_user(User(row), remember=True)
                return redirect(url_for("index"))
        else:
            error = "Correo o contrasena incorrectos."
    return render_template("login.html", error=error)

@app.route("/register", methods=["GET","POST"])
def register():
    if current_user.is_authenticated: return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        nick = request.form.get("nickname","").strip()[:24]
        mail = request.form.get("email","").strip().lower()
        pw   = request.form.get("password","")
        pw2  = request.form.get("confirm","")
        if not nick or not mail or not pw:
            error = "Rellena todos los campos."
        elif pw != pw2:
            error = "Las contrasenas no coinciden."
        elif len(pw) < 6:
            error = "La contrasena debe tener al menos 6 caracteres."
        else:
            db  = get_db()
            dup = dbq(db, "SELECT id FROM users WHERE email=?", (mail,)).fetchone()
            if dup:
                error = "Este correo ya esta registrado."
                db.close()
            else:
                cnt  = dbscalar(db, "SELECT COUNT(*) FROM users")
                role = "admin" if cnt == 0 else "user"
                dbq(db, "INSERT INTO users (email,nickname,password_hash,role) VALUES (?,?,?,?)",
                    (mail, nick, generate_password_hash(pw), role))
                db.commit()
                row = dbq(db, "SELECT * FROM users WHERE email=?", (mail,)).fetchone()
                db.close()
                login_user(User(row), remember=True)
                return redirect(url_for("index"))
    return render_template("register.html", error=error)

@app.route("/logout")
@login_required
def logout():
    logout_user(); return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    return render_template("chat.html", rooms=get_rooms(), user=current_user,
                           groups=get_groups(current_user.id))

@app.route("/api/push/subscribe", methods=["POST"])
@login_required
def push_subscribe():
    data   = request.get_json()
    ep     = data.get("endpoint","")
    p256dh = data.get("keys",{}).get("p256dh","")
    auth   = data.get("keys",{}).get("auth","")
    if not ep or not p256dh or not auth:
        return jsonify({"error":"datos incompletos"}), 400
    db = get_db()
    try:
        dbq(db, "INSERT INTO push_subs (user_id,endpoint,p256dh,auth) VALUES (?,?,?,?)",
            (current_user.id, ep, p256dh, auth))
    except Exception:
        dbq(db, "UPDATE push_subs SET p256dh=?,auth=? WHERE endpoint=?",
            (p256dh, auth, ep))
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/notificaciones")
@login_required
def notif_page():
    return render_template("notificaciones.html")

@app.route("/api/push/test")
@login_required
def push_test():
    try:
        from pywebpush import webpush, WebPushException
        import json as _json
        db = get_db()
        subs = dbq(db, "SELECT endpoint, p256dh, auth FROM push_subs WHERE user_id=?",
                   (current_user.id,)).fetchall()
        db.close()
        if not subs:
            return jsonify({"error": "No hay suscripciones guardadas"})
        results = []
        for s in subs:
            try:
                webpush(
                    subscription_info={"endpoint": s["endpoint"],
                                       "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}},
                    data=_json.dumps({"title": "Prueba deúres", "body": "Notificaciones funcionando!", "url": "/"}),
                    vapid_private_key=VAPID_PRIVATE,
                    vapid_claims=VAPID_CLAIMS
                )
                results.append({"ok": True, "endpoint": s["endpoint"][:60]})
            except Exception as e:
                results.append({"ok": False, "error": str(e), "endpoint": s["endpoint"][:60]})
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"fatal": str(e)})

@app.route("/api/push/debug")
@login_required
def push_debug():
    db = get_db()
    subs = dbq(db, "SELECT id, endpoint, created_at FROM push_subs WHERE user_id=?",
               (current_user.id,)).fetchall()
    db.close()
    return jsonify({
        "user_id": current_user.id,
        "vapid_configured": bool(VAPID_PUBLIC and VAPID_PRIVATE),
        "subscriptions": [{"id": s["id"], "endpoint": s["endpoint"][:60]+"..."} for s in subs]
    })

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    if "file" not in request.files: return jsonify({"error":"Sin archivo"}), 400
    f = request.files["file"]
    if not f or not f.filename: return jsonify({"error":"Nombre vacio"}), 400
    if not allowed(f.filename): return jsonify({"error":"Tipo no permitido"}), 400
    ext = f.filename.rsplit(".",1)[1].lower()
    saved = str(uuid.uuid4()) + "." + ext
    f.save(os.path.join(UPLOAD_DIR, saved))
    return jsonify({"url": "/uploads/" + saved,
                    "name": secure_filename(f.filename),
                    "is_image": is_img(saved)})

@app.route("/uploads/<path:fn>")
@login_required
def serve_upload(fn):
    resp = send_from_directory(UPLOAD_DIR, fn)
    resp.headers["Cache-Control"] = "private, max-age=2592000"  # 30 days
    return resp

@app.after_request
def add_cache_headers(resp):
    path = request.path
    # Static assets: cache 7 days in browser — biggest egress saver
    if path.startswith("/static/") or path in ("/sw.js", "/manifest.json"):
        resp.headers["Cache-Control"] = "public, max-age=604800, immutable"
    # Friends list rarely changes — cache 30s client-side to avoid hammering
    elif path == "/api/friends/list":
        resp.headers["Cache-Control"] = "private, max-age=30"
    return resp

@app.route("/api/friends/search")
@login_required
def friends_search():
    q = request.args.get("q","").strip()
    if len(q) < 2: return jsonify([])
    db   = get_db()
    rows = dbq(db, "SELECT id, nickname FROM users WHERE nickname LIKE ? AND id != ? LIMIT 10",
               (f"%{q}%", current_user.id)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/friends/request/<int:uid>", methods=["POST"])
@login_required
def friend_request(uid):
    if uid == current_user.id:
        return jsonify({"error": "No puedes anadirte a ti mismo"}), 400
    db  = get_db()
    ex  = dbq(db,
        "SELECT id FROM friendships WHERE (requester_id=? AND addressee_id=?) OR (requester_id=? AND addressee_id=?)",
        (current_user.id, uid, uid, current_user.id)).fetchone()
    if ex:
        db.close(); return jsonify({"error": "Solicitud ya existe"}), 400
    dbq(db, "INSERT INTO friendships (requester_id, addressee_id) VALUES (?,?)",
        (current_user.id, uid))
    db.commit(); db.close()
    socketio.emit("friend_request", {"from_id": current_user.id, "from_nick": current_user.nickname},
                  room=f"user_{uid}")
    return jsonify({"ok": True})

@app.route("/api/friends/accept/<int:uid>", methods=["POST"])
@login_required
def friend_accept(uid):
    db = get_db()
    dbq(db, "UPDATE friendships SET status='accepted' WHERE requester_id=? AND addressee_id=? AND status='pending'",
        (uid, current_user.id))
    db.commit(); db.close()
    socketio.emit("friend_accepted", {"from_id": current_user.id, "from_nick": current_user.nickname},
                  room=f"user_{uid}")
    return jsonify({"ok": True})

@app.route("/api/friends/decline/<int:uid>", methods=["POST"])
@login_required
def friend_decline(uid):
    db = get_db()
    dbq(db, "DELETE FROM friendships WHERE requester_id=? AND addressee_id=? AND status='pending'",
        (uid, current_user.id))
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/api/friends/remove/<int:uid>", methods=["POST"])
@login_required
def friend_remove(uid):
    db = get_db()
    dbq(db, "DELETE FROM friendships WHERE (requester_id=? AND addressee_id=?) OR (requester_id=? AND addressee_id=?)",
        (current_user.id, uid, uid, current_user.id))
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/api/friends/list")
@login_required
def friends_list():
    friends = get_friends(current_user.id)
    for f in friends:
        f["online"] = f["id"] in online_users and len(online_users[f["id"]]) > 0
    return jsonify(friends)

@app.route("/api/friends/pending")
@login_required
def friends_pending():
    db   = get_db()
    rows = dbq(db, """
        SELECT f.requester_id as from_id, u.nickname as from_nick
        FROM friendships f JOIN users u ON f.requester_id=u.id
        WHERE f.addressee_id=? AND f.status='pending'
    """, (current_user.id,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/admin")
@login_required
@admin_required
def admin():
    db    = get_db()
    users = [dict(r) for r in dbq(db, "SELECT * FROM users ORDER BY created_at").fetchall()]
    db.close()
    return render_template("admin.html", users=users, rooms=get_rooms(), user=current_user)

@app.route("/admin/user/<int:uid>/<action>", methods=["POST"])
@login_required
@admin_required
def admin_user_action(uid, action):
    if uid == current_user.id:
        return jsonify({"error": "No puedes modificarte a ti mismo"}), 400
    db = get_db()
    if action == "ban":
        dbq(db, "UPDATE users SET banned=1 WHERE id=?", (uid,))
    elif action == "unban":
        dbq(db, "UPDATE users SET banned=0 WHERE id=?", (uid,))
    elif action == "promote":
        dbq(db, "UPDATE users SET role='admin' WHERE id=?", (uid,))
    elif action == "delete":
        dbq(db, "DELETE FROM users WHERE id=?", (uid,))
    else:
        db.close(); return jsonify({"error": "Accion desconocida"}), 400
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/admin/room/create", methods=["POST"])
@login_required
@admin_required
def admin_room_create():
    data  = request.get_json()
    name  = (data.get("name") or "").strip()[:40]
    emoji = (data.get("emoji") or "\U0001f4ac").strip()[:2]
    if not name: return jsonify({"error": "Nombre vacio"}), 400
    rid = name.lower().replace(" ","_")[:20] + "_" + str(uuid.uuid4())[:4]
    db  = get_db()
    dbq(db, "INSERT INTO rooms (id,name,emoji) VALUES (?,?,?)", (rid, name, emoji))
    db.commit(); db.close()
    socketio.emit("room_created", {"id": rid, "name": name, "emoji": emoji})
    return jsonify({"ok": True, "id": rid, "name": name, "emoji": emoji})

@app.route("/admin/room/<rid>/rename", methods=["POST"])
@login_required
@admin_required
def admin_room_rename(rid):
    data  = request.get_json()
    name  = (data.get("name") or "").strip()[:40]
    emoji = (data.get("emoji") or "\U0001f4ac").strip()[:2]
    if not name: return jsonify({"error": "Nombre vacio"}), 400
    db = get_db()
    dbq(db, "UPDATE rooms SET name=?, emoji=? WHERE id=?", (name, emoji, rid))
    db.commit(); db.close()
    socketio.emit("room_renamed", {"id": rid, "name": name, "emoji": emoji})
    return jsonify({"ok": True})

@app.route("/admin/room/<rid>/delete", methods=["POST"])
@login_required
@admin_required
def admin_room_delete(rid):
    db = get_db()
    dbq(db, "DELETE FROM rooms WHERE id=?", (rid,))
    db.commit(); db.close()
    if rid in room_msgs: del room_msgs[rid]
    socketio.emit("room_deleted", {"id": rid})
    return jsonify({"ok": True})

# ── Avatar ──
@app.route("/api/avatar", methods=["POST"])
@login_required
def set_avatar():
    data   = request.get_json()
    avatar = (data.get("avatar") or "")[:8]
    db = get_db()
    dbq(db, "UPDATE users SET avatar=? WHERE id=?", (avatar, current_user.id))
    db.commit(); db.close()
    current_user.avatar = avatar
    return jsonify({"ok": True})

# ── Groups ──
@app.route("/api/groups")
@login_required
def api_groups():
    return jsonify(get_groups(current_user.id))

@app.route("/api/groups/create", methods=["POST"])
@login_required
def api_group_create():
    data  = request.get_json()
    name  = (data.get("name") or "").strip()[:40]
    emoji = (data.get("emoji") or "👥").strip()[:4]
    friends = data.get("members", [])
    if not name: return jsonify({"error": "Nombre vacio"}), 400
    db = get_db()
    dbq(db, "INSERT INTO groups_tbl (name, emoji, created_by) VALUES (?,?,?)",
        (name, emoji, current_user.id))
    db.commit()
    gid = dbscalar(db, "SELECT id FROM groups_tbl WHERE created_by=? ORDER BY created_at DESC LIMIT 1",
                   (current_user.id,))
    dbq(db, "INSERT INTO group_members (group_id, user_id) VALUES (?,?)", (gid, current_user.id))
    for fid in friends:
        try:
            dbq(db, "INSERT INTO group_members (group_id, user_id) VALUES (?,?)", (gid, int(fid)))
        except Exception:
            pass
    db.commit(); db.close()
    group = {"id": gid, "name": name, "emoji": emoji, "created_by": current_user.id}
    members = get_group_members(gid)
    for m in members:
        socketio.emit("group_created", {"group": group, "members": members}, room=f"user_{m['id']}")
    return jsonify({"ok": True, "group": group})

@app.route("/api/groups/<int:gid>/invite", methods=["POST"])
@login_required
def api_group_invite(gid):
    data = request.get_json()
    uid  = data.get("user_id")
    db   = get_db()
    owner = dbscalar(db, "SELECT created_by FROM groups_tbl WHERE id=?", (gid,))
    if owner != current_user.id:
        db.close(); return jsonify({"error": "Sin permiso"}), 403
    try:
        dbq(db, "INSERT INTO group_members (group_id, user_id) VALUES (?,?)", (gid, int(uid)))
        db.commit()
    except Exception:
        db.close(); return jsonify({"error": "Ya es miembro"}), 400
    db.close()
    group = next((g for g in get_groups(current_user.id) if g["id"] == gid), None)
    members = get_group_members(gid)
    if group:
        socketio.emit("group_created", {"group": group, "members": members}, room=f"user_{uid}")
    return jsonify({"ok": True})

@app.route("/api/groups/<int:gid>/leave", methods=["POST"])
@login_required
def api_group_leave(gid):
    db = get_db()
    dbq(db, "DELETE FROM group_members WHERE group_id=? AND user_id=?", (gid, current_user.id))
    db.commit()
    remaining = dbscalar(db, "SELECT COUNT(*) FROM group_members WHERE group_id=?", (gid,))
    if remaining == 0:
        dbq(db, "DELETE FROM groups_tbl WHERE id=?", (gid,))
        db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/api/groups/<int:gid>/members")
@login_required
def api_group_members(gid):
    return jsonify(get_group_members(gid))

# ── Tasks ──
@app.route("/api/tasks/<room_id>")
@login_required
def api_tasks(room_id):
    db   = get_db()
    rows = dbq(db, "SELECT * FROM tasks WHERE room_id=? ORDER BY done, created_at", (room_id,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/tasks/<room_id>/add", methods=["POST"])
@login_required
def api_task_add(room_id):
    data     = request.get_json()
    title    = (data.get("title") or "").strip()[:200]
    due_date = (data.get("due_date") or "").strip()[:10] or None  # YYYY-MM-DD
    if not title: return jsonify({"error": "Titulo vacio"}), 400
    db = get_db()
    dbq(db, "INSERT INTO tasks (room_id, title, due_date, created_by) VALUES (?,?,?,?)",
        (room_id, title, due_date, current_user.id))
    db.commit()
    tid = dbscalar(db, "SELECT id FROM tasks WHERE room_id=? AND created_by=? ORDER BY created_at DESC LIMIT 1",
                   (room_id, current_user.id))
    db.close()
    task = {"id": tid, "room_id": room_id, "title": title, "done": 0,
            "due_date": due_date, "created_by": current_user.id}
    socketio.emit("task_added", {"room_id": room_id, "task": task}, room=room_id)
    return jsonify({"ok": True, "task": task})

@app.route("/api/tasks/<int:tid>/toggle", methods=["POST"])
@login_required
def api_task_toggle(tid):
    db   = get_db()
    task = dbq(db, "SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not task:
        db.close(); return jsonify({"error": "No existe"}), 404
    new_done = 0 if task["done"] else 1
    dbq(db, "UPDATE tasks SET done=? WHERE id=?", (new_done, tid))
    db.commit(); db.close()
    socketio.emit("task_updated", {"id": tid, "done": new_done}, room=task["room_id"])
    return jsonify({"ok": True, "done": new_done})

@app.route("/api/tasks/<int:tid>/delete", methods=["POST"])
@login_required
def api_task_delete(tid):
    db   = get_db()
    task = dbq(db, "SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not task:
        db.close(); return jsonify({"error": "No existe"}), 404
    if task["created_by"] != current_user.id and not current_user.is_admin:
        db.close(); return jsonify({"error": "Sin permiso"}), 403
    dbq(db, "DELETE FROM tasks WHERE id=?", (tid,))
    db.commit(); db.close()
    socketio.emit("task_deleted", {"id": tid, "room_id": task["room_id"]}, room=task["room_id"])
    return jsonify({"ok": True})

@socketio.on("connect")
def on_connect():
    if not current_user.is_authenticated: return False
    uid = current_user.id
    sid = request.sid
    join_room(f"user_{uid}")
    # Only notify friends on the *first* session — avoids N×M emits on tab reload
    was_offline = uid not in online_users or len(online_users[uid]) == 0
    online_users.setdefault(uid, set()).add(sid)
    sid_rooms[sid] = set()
    if was_offline:
        for f in get_friends(uid):
            socketio.emit("friend_online", {"id": uid, "nickname": current_user.nickname},
                          room=f"user_{f['id']}")

@socketio.on("disconnect")
def on_disconnect():
    if not current_user.is_authenticated: return
    uid = current_user.id
    sid = request.sid
    if uid in online_users:
        online_users[uid].discard(sid)
        if not online_users[uid]:
            del online_users[uid]
            for f in get_friends(uid):
                socketio.emit("friend_offline", {"id": uid}, room=f"user_{f['id']}")
    for room in sid_rooms.pop(sid, set()):
        if room in room_users:
            room_users[room].discard(uid)
            emit("user_left", {"user_id": uid, "nickname": current_user.nickname,
                               "count": len(room_users[room])}, room=room)
        # P2P cleanup
        if room in room_sids:
            room_sids[room].pop(sid, None)
        if room_host.get(room) == sid:
            del room_host[room]
        socketio.emit("peer_left", {"sid": sid}, room=room)

@socketio.on("join")
def on_join(data):
    global _join_counter
    room = data.get("room","")
    if not room: return
    sid = request.sid; uid = current_user.id
    join_room(room)
    sid_rooms.setdefault(sid, set()).add(room)
    room_users.setdefault(room, set()).add(uid)

    # P2P: track sid and assign join order
    _join_counter += 1
    existing = room_sids.get(room, {})
    is_first = len(existing) == 0
    room_sids.setdefault(room, {})[sid] = {
        "uid": uid, "nickname": current_user.nickname, "join_order": _join_counter
    }
    current_host = room_host.get(room)
    if is_first:
        room_host[room] = sid
        current_host = sid

    # Tell new joiner who's already in the room (for WebRTC)
    emit("room_peers", {
        "room": room,
        "peers": [{"sid": s, **info} for s, info in existing.items()],
        "host_sid": current_host,
        "is_temp_host": is_first
    })
    # Tell existing peers about the new joiner
    emit("peer_joined", {"sid": sid, "uid": uid,
                         "nickname": current_user.nickname,
                         "join_order": _join_counter},
         room=room, include_self=False)

    emit("history", {"room": room, "messages": room_msgs.get(room, [])[-50:]})
    emit("user_joined", {"user_id": uid, "nickname": current_user.nickname,
                         "count": len(room_users[room])}, room=room)

@socketio.on("leave")
def on_leave(data):
    room = data.get("room","")
    if not room: return
    sid = request.sid; uid = current_user.id
    leave_room(room)
    sid_rooms.get(sid, set()).discard(room)
    if room in room_users: room_users[room].discard(uid)
    emit("user_left", {"user_id": uid, "nickname": current_user.nickname,
                       "count": len(room_users.get(room, set()))}, room=room)

@socketio.on("send_message")
def on_send_message(data):
    room        = data.get("room","")
    text        = (data.get("text") or "").strip()[:2000]
    furl        = data.get("file_url","")
    fname       = data.get("file_name","")
    img         = bool(data.get("is_image", False))
    reply_to    = data.get("reply_to", None)
    client_time = (data.get("time") or "")[:5]  # "HH:MM" from client's local clock
    if not room or (not text and not furl): return
    av  = current_user.avatar if hasattr(current_user, "avatar") else ""
    msg = make_msg("chat", current_user.id, current_user.nickname, text, furl, fname, img, reply_to=reply_to, avatar=av, time=client_time or None)
    room_msgs.setdefault(room, []).append(msg)
    if len(room_msgs[room]) > MSG_LIMIT: room_msgs[room] = room_msgs[room][-MSG_LIMIT:]
    emit("new_message", {"room": room, "message": msg}, room=room)
    body = (text or "Archivo adjunto")[:80]
    online_in_room = room_users.get(room, set())
    db = get_db()
    others = [dict(r) for r in dbq(db, "SELECT id FROM users WHERE id != ?", (current_user.id,)).fetchall()]
    db.close()
    for u in others:
        if u["id"] not in online_in_room:
            threading.Thread(target=send_push, args=(
                u["id"], f"{current_user.nickname} en #{room}", body, "/"
            ), daemon=True).start()

@socketio.on("delete_message")
def on_delete_message(data):
    room = data.get("room",""); mid = data.get("message_id","")
    if not room or not mid: return
    msgs   = room_msgs.get(room, [])
    target = next((m for m in msgs if m["id"] == mid), None)
    if not target: return
    if target["user_id"] != current_user.id and not current_user.is_admin: return
    room_msgs[room] = [m for m in msgs if m["id"] != mid]
    emit("message_deleted", {"room": room, "message_id": mid}, room=room)

@socketio.on("react_message")
def on_react_message(data):
    room   = data.get("room","")
    mid    = data.get("message_id","")
    emoji  = (data.get("emoji") or "")[:4]
    if not room or not mid or not emoji: return
    msgs = room_msgs.get(room, [])
    msg  = next((m for m in msgs if m["id"] == mid), None)
    if not msg: return
    reactions = msg.setdefault("reactions", {})
    users = reactions.setdefault(emoji, [])
    uid   = current_user.id
    if uid in users:
        users.remove(uid)
        if not users: del reactions[emoji]
    else:
        users.append(uid)
    emit("reaction_updated", {"room": room, "message_id": mid, "reactions": msg["reactions"]}, room=room)

@socketio.on("send_group_message")
def on_send_group_message(data):
    gid         = data.get("group_id")
    text        = (data.get("text") or "").strip()[:2000]
    furl        = data.get("file_url",""); fname = data.get("file_name","")
    img         = bool(data.get("is_image", False))
    reply_to    = data.get("reply_to", None)
    client_time = (data.get("time") or "")[:5]
    if not gid or (not text and not furl): return
    room = f"group_{gid}"
    av   = current_user.avatar if hasattr(current_user, "avatar") else ""
    msg  = make_msg("group", current_user.id, current_user.nickname, text, furl, fname, img, reply_to=reply_to, avatar=av, time=client_time or None)
    room_msgs.setdefault(room, []).append(msg)
    if len(room_msgs[room]) > MSG_LIMIT: room_msgs[room] = room_msgs[room][-MSG_LIMIT:]
    emit("group_message", {"group_id": gid, "room": room, "message": msg}, room=room)

@socketio.on("join_group")
def on_join_group(data):
    gid = data.get("group_id")
    if not gid: return
    room = f"group_{gid}"
    join_room(room)
    emit("group_history", {"group_id": gid, "room": room, "messages": room_msgs.get(room, [])[-50:]})

@socketio.on("send_dm")
def on_send_dm(data):
    to_id       = data.get("to_id")
    text        = (data.get("text") or "").strip()[:2000]
    furl        = data.get("file_url",""); fname = data.get("file_name","")
    img         = bool(data.get("is_image", False))
    reply_to    = data.get("reply_to", None)
    client_time = (data.get("time") or "")[:5]
    if not to_id or (not text and not furl): return
    room = dm_room(current_user.id, to_id)
    av   = current_user.avatar if hasattr(current_user, "avatar") else ""
    msg  = make_msg("dm", current_user.id, current_user.nickname, text, furl, fname, img, reply_to=reply_to, avatar=av, time=client_time or None)
    room_msgs.setdefault(room, []).append(msg)
    if len(room_msgs[room]) > MSG_LIMIT: room_msgs[room] = room_msgs[room][-MSG_LIMIT:]
    join_room(room)
    emit("dm_message", {"room": room, "to_id": to_id, "message": msg}, room=room)
    # Only notify via user_X if recipient hasn't got the DM open (avoids duplicates)
    if to_id not in room_users.get(room, set()):
        socketio.emit("dm_message", {"room": room, "to_id": to_id, "message": msg},
                      room="user_{}".format(to_id))
    body = (text or "Archivo adjunto")[:80]
    threading.Thread(target=send_push, args=(
        to_id, "Mensaje de {}".format(current_user.nickname), body, "/"
    ), daemon=True).start()

@socketio.on("get_dm_history")
def on_get_dm_history(data):
    to_id = data.get("to_id")
    if not to_id: return
    room = dm_room(current_user.id, to_id)
    join_room(room)
    emit("dm_history", {"room": room, "to_id": to_id, "messages": room_msgs.get(room, [])[-50:]})

@socketio.on("rtc_signal")
def on_rtc_signal(data):
    target = data.get("to")
    if not target: return
    emit("rtc_signal", {"from": request.sid, "type": data.get("type"),
                        "sdp": data.get("sdp"), "candidate": data.get("candidate")},
         room=target)

@socketio.on("rtc_host_elected")
def on_rtc_host_elected(data):
    room = data.get("room")
    host_sid = data.get("host_sid")
    if room and host_sid:
        room_host[room] = host_sid
        emit("rtc_host_elected", {"host_sid": host_sid}, room=room)

@socketio.on("rtc_benchmark_result")
def on_rtc_benchmark_result(data):
    room = data.get("room")
    host = room_host.get(room)
    if host:
        emit("rtc_benchmark_result", data, room=host)

def open_browser():
    import time; time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    if not DATABASE_URL:
        threading.Thread(target=open_browser, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
