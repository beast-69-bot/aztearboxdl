import json
import os

DB_FILE = "database.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": [], "stats": {"downloads": 0, "uploads": 0}}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"users": [], "stats": {"downloads": 0, "uploads": 0}}

def save_db(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving database: {e}")

def add_user(user_id):
    db = load_db()
    if user_id not in db["users"]:
        db["users"].append(user_id)
        save_db(db)

def increment_stat(stat_name):
    db = load_db()
    if "stats" not in db:
        db["stats"] = {"downloads": 0, "uploads": 0}
    db["stats"][stat_name] = db["stats"].get(stat_name, 0) + 1
    save_db(db)

def get_stats():
    db = load_db()
    active_users = len(db.get("users", []))
    stats = db.get("stats", {"downloads": 0, "uploads": 0})
    return active_users, stats.get("downloads", 0), stats.get("uploads", 0)

def get_all_users():
    db = load_db()
    return db.get("users", [])
