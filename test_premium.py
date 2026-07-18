#!/usr/bin/env python3
"""
Quick diagnostic script — run on VPS to test FapHouse MongoDB connection.
Usage: venv/bin/python test_premium.py <USER_ID>
"""
import asyncio
import sys
import datetime

async def main():
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 8615007714
    print(f"\n🔍 Testing FapHouse premium check for user_id: {user_id}\n")

    # ── Step 1: Import motor ──────────────────────────────────────────
    try:
        import motor.motor_asyncio
        print("✅ motor imported OK")
    except ImportError as e:
        print(f"❌ motor import FAILED: {e}")
        print("   Fix: venv/bin/pip install motor==2.5.1 pymongo[srv]==3.12.3 dnspython")
        return

    # ── Step 2: Load config ───────────────────────────────────────────
    try:
        import config
        print(f"✅ config loaded | MONGO_DB={config.MONGO_DB[:40]}... | DB_NAME={config.DB_NAME}")
    except Exception as e:
        print(f"❌ config load FAILED: {e}")
        return

    if not config.MONGO_DB:
        print("❌ MONGO_DB is EMPTY — set it in .env!")
        return

    # ── Step 3: Connect to MongoDB ───────────────────────────────────
    try:
        client = motor.motor_asyncio.AsyncIOMotorClient(
            config.MONGO_DB,
            serverSelectionTimeoutMS=8000
        )
        db = client[config.DB_NAME]
        # Ping to confirm connection
        await client.admin.command("ping")
        print(f"✅ MongoDB connected! DB: {config.DB_NAME}")
    except Exception as e:
        print(f"❌ MongoDB connection FAILED: {e}")
        print("\n👉 MOST LIKELY FIX: Whitelist your VPS IP in MongoDB Atlas!")
        print("   1. Go to: https://cloud.mongodb.com")
        print("   2. Security → Network Access → Add IP Address")
        print("   3. Add your VPS IP (or 0.0.0.0/0 for all IPs)")
        return

    # ── Step 4: List all collections ─────────────────────────────────
    try:
        collections = await db.list_collection_names()
        print(f"✅ Collections found: {collections}")
    except Exception as e:
        print(f"⚠️ Could not list collections: {e}")

    # ── Step 5: Check faphouse_users collection ───────────────────────
    print(f"\n🔍 Checking faphouse_users collection for user_id={user_id}...")
    try:
        col = db["faphouse_users"]
        now = datetime.datetime.now(datetime.timezone.utc)

        # Find ANY doc for this user (ignore expiry)
        any_doc = await col.find_one({
            "$or": [{"user_id": int(user_id)}, {"user_id": str(user_id)}]
        })
        if any_doc:
            sub_end = any_doc.get("subscription_end")
            print(f"✅ Found faphouse doc!")
            print(f"   user_id: {any_doc.get('user_id')} (type={type(any_doc.get('user_id')).__name__})")
            print(f"   bot_username: {any_doc.get('bot_username')}")
            print(f"   subscription_end: {sub_end} (type={type(sub_end).__name__})")
            print(f"   Now UTC: {now}")
            if sub_end:
                # Make both comparable
                if sub_end.tzinfo is None:
                    sub_end_aware = sub_end.replace(tzinfo=datetime.timezone.utc)
                else:
                    sub_end_aware = sub_end
                is_active = sub_end_aware > now
                print(f"   Plan ACTIVE: {'✅ YES' if is_active else '❌ NO (expired)'}")
            print(f"\n   Full doc: {any_doc}")
        else:
            print(f"❌ No faphouse doc found for user_id={user_id}")
            print(f"   Checking ALL docs in faphouse_users...")
            async for doc in col.find({}):
                print(f"   Found doc: user_id={doc.get('user_id')}, bot={doc.get('bot_username')}, end={doc.get('subscription_end')}")
    except Exception as e:
        print(f"❌ faphouse_users query FAILED: {e}")

    # ── Step 6: Check premium_users collection ────────────────────────
    print(f"\n🔍 Checking premium_users collection for user_id={user_id}...")
    try:
        col2 = db["premium_users"]
        prem_doc = await col2.find_one({
            "$or": [{"user_id": int(user_id)}, {"user_id": str(user_id)}]
        })
        if prem_doc:
            print(f"✅ Found premium_users doc: {prem_doc}")
        else:
            print(f"❌ No premium_users doc for user_id={user_id}")
    except Exception as e:
        print(f"❌ premium_users query FAILED: {e}")

    client.close()
    print("\n✅ Diagnostic complete!")

asyncio.run(main())
