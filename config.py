import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
NDUS_COOKIE = os.getenv("NDUS_COOKIE")
TERABOX_COOKIE_HEADER = os.getenv("TERABOX_COOKIE_HEADER")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
STATIC_PROXY = os.getenv("STATIC_PROXY")

def reload_ndus():
    global NDUS_COOKIE, TERABOX_COOKIE_HEADER, STATIC_PROXY
    load_dotenv(override=True)
    NDUS_COOKIE = os.getenv("NDUS_COOKIE")
    TERABOX_COOKIE_HEADER = os.getenv("TERABOX_COOKIE_HEADER")
    STATIC_PROXY = os.getenv("STATIC_PROXY")

