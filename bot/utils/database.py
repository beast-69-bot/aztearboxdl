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


# ── MongoDB FapHouse / Premium Shared Database Check ───────────────────
_mongo_client = None

async def check_faphouse_premium(user_id: int) -> bool:
    """
    Checks if a user has an active FapHouse or Premium subscription in the shared MongoDB.
    Allows bypassing the 10 links daily limit as a bonus.
    """
    global _mongo_client
    try:
        import motor.motor_asyncio
        import datetime
        import config
    except ImportError:
        print("[DATABASE] motor or dependencies not installed. Skipping MongoDB check.")
        return False

    try:
        if _mongo_client is None:
            if not config.MONGO_DB:
                return False
            _mongo_client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGO_DB)
        
        db = _mongo_client[config.DB_NAME]
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # 1. Check faphouse_users collection
        faphouse_users_col = db["faphouse_users"]
        fap_doc = await faphouse_users_col.find_one({
            "$or": [
                {"user_id": int(user_id)},
                {"user_id": str(user_id)}
            ],
            "subscription_end": {"$gt": now}
        })
        if fap_doc:
            print(f"[PREMIUM] User {user_id} has active FapHouse plan (expires: {fap_doc.get('subscription_end')})")
            return True
            
        # 2. Check premium_users collection (general premium)
        premium_users_col = db["premium_users"]
        prem_doc = await premium_users_col.find_one({
            "$or": [
                {"user_id": int(user_id)},
                {"user_id": str(user_id)}
            ],
            "subscription_end": {"$gt": now}
        })
        if prem_doc:
            print(f"[PREMIUM] User {user_id} has active Premium plan (expires: {prem_doc.get('subscription_end')})")
            return True
            
    except Exception as e:
        print(f"[DATABASE] Error checking premium status in MongoDB: {e}")
        
    return False

