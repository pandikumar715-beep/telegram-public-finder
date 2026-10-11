
import os
import sqlite3
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

DB_PATH = os.environ.get("DB_PATH", "/tmp/groups.db")


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS groups_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                link TEXT NOT NULL UNIQUE,
                keywords TEXT DEFAULT '',
                approved INTEGER DEFAULT 0
            )
        """)


def send_message(chat_id, text, keyboard=None):
    if not BOT_TOKEN:
        return
    data = {"chat_id": chat_id, "text": text}
    if keyboard:
        data["reply_markup"] = keyboard
    try:
        requests.post(
            f"{API}/sendMessage",
            json=data,
            timeout=15
        )
    except requests.RequestException:
        pass


def search_groups(query):
    words = query.lower().split()
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute("""
            SELECT name, link, keywords
            FROM groups_list
            WHERE approved = 1
            ORDER BY name
            LIMIT 100
        """).fetchall()

    results = []
    for name, link, keywords in rows:
        searchable = f"{name} {keywords}".lower()
        if all(word in searchable for word in words):
            results.append((name, link))
    return results[:10]


def handle_message(message):
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "").strip()

    if text.startswith("/start"):
        send_message(
            chat_id,
            "🔎 Welcome to Public Group Finder!\n\n"
            "Search public Telegram groups by keyword.\n"
            "Example: tamil, jobs, gaming\n\n"
            "Use /submit to suggest a group."
        )
        return

    if text.startswith("/help"):
        send_message(
            chat_id,
            "Commands:\n"
            "/start - Start bot\n"
            "/search keyword - Search groups\n"
            "/submit - Submit a public group\n"
            "/pending - Admin: view submissions\n"
            "/approve ID - Admin: approve submission"
        )
        return

    if text.startswith("/submit"):
        send_message(
            chat_id,
            "Submit a public group in this format:\n\n"
            "Name | https://t.me/groupusername | keywords\n\n"
            "Example:\n"
            "Tamil Friends | https://t.me/examplegroup | tamil friends chat\n\n"
            "Only submit groups you have permission to share."
        )
        return

    if text.startswith("/pending"):
        if user_id != ADMIN_ID:
            send_message(chat_id, "This command is for the admin only.")
            return

        with sqlite3.connect(DB_PATH) as db:
            rows = db.execute("""
                SELECT id, name, link, keywords
                FROM groups_list
                WHERE approved = 0
                ORDER BY id
                LIMIT 20
            """).fetchall()

        if not rows:
            send_message(chat_id, "No pending submissions.")
            return

        output = []
        for item_id, name, link, keywords in rows:
            output.append(
                f"ID: {item_id}\nName: {name}\n"
                f"Link: {link}\nKeywords: {keywords}\n"
                f"Approve with /approve {item_id}"
            )
        send_message(chat_id, "\n\n".join(output))
        return

    if text.startswith("/approve"):
        if user_id != ADMIN_ID:
            send_message(chat_id, "This command is for the admin only.")
            return

        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            send_message(chat_id, "Use: /approve ID")
            return

        with sqlite3.connect(DB_PATH) as db:
            result = db.execute(
                "UPDATE groups_list SET approved=1 WHERE id=?",
                (int(parts[1]),)
            )
            changed = result.rowcount
            db.commit()

        send_message(
            chat_id,
            "✅ Group approved!" if changed else "Group ID not found."
        )
        return

    if text.startswith("/search"):
        query = text[len("/search"):].strip()
        if not query:
            send_message(chat_id, "Usage: /search tamil")
            return

        results = search_groups(query)
        if not results:
            send_message(
                chat_id,
                "No matching groups yet.\n"
                "Try another keyword or use /submit to suggest a group."
            )
            return

        output = ["🔎 Search results:"]
        for name, link in results:
            output.append(f"\n• {name}\n{link}")
        send_message(chat_id, "\n".join(output))
        return

    # Accept group submissions in the requested format.
    parts = [part.strip() for part in text.split("|")]
    if len(parts) == 3 and parts[1].startswith("https://t.me/"):
        name, link, keywords = parts

        if not name or not keywords:
            send_message(chat_id, "Please provide name, link and keywords.")
            return

        try:
            with sqlite3.connect(DB_PATH) as db:
                db.execute("""
                    INSERT INTO groups_list
                    (name, link, keywords, approved)
                    VALUES (?, ?, ?, 0)
                """, (name[:100], link, keywords[:300]))
                db.commit()
            send_message(
                chat_id,
                "✅ Submission received! It will appear after admin approval."
            )
        except sqlite3.IntegrityError:
            send_message(chat_id, "That group link has already been submitted.")
        return

    send_message(
        chat_id,
        "Try /search tamil\n"
        "To suggest a group, use /submit first."
    )


@app.route("/", methods=["GET"])
def home():
    return "Telegram Public Group Finder is running!"


@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != os.environ.get(
        "WEBHOOK_SECRET", ""
    ):
        return "Forbidden", 403

    update = request.get_json(silent=True) or {}
    message = update.get("message")

    if message and message.get("text"):
        handle_message(message)

    return "OK", 200


init_db()
