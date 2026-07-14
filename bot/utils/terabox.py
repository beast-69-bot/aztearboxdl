import os
import uuid
import re
import time
import random
from curl_cffi import requests as curl_requests
from config import NDUS_COOKIE
from bot.utils.progress import progress_callback
from bot.utils.proxy_pool import fetch_fresh_proxies, get_proxy_dict

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36"
    )
}

# In-memory proxy list cache
vps_cached_proxies = []

def get_session_with_proxy():
    """Generates a session. Tries a cached proxy or fetches new ones if IP is blacklisted."""
    global vps_cached_proxies
    session = curl_requests.Session(impersonate="chrome110")
    session.cookies.update({"ndus": NDUS_COOKIE})
    
    # Try using a random proxy from the cache
    if not vps_cached_proxies:
        try:
            print("Fetching fresh rotating proxy list...")
            vps_cached_proxies = fetch_fresh_proxies()
        except Exception as e:
            print(f"Failed to fetch free proxies: {e}")
            
    if vps_cached_proxies:
        selected_proxy = random.choice(vps_cached_proxies)
        session.proxies = get_proxy_dict(selected_proxy)
        print(f"Using proxy: {selected_proxy}")
        
    return session, vps_cached_proxies

def get_terabox_info(surl: str) -> dict | None:
    """
    Fetches file metadata from TeraBox using the public share URL ID.
    Rotates proxy automatically if verification block 'need verify' is detected.
    """
    short = surl[1:] if surl.startswith("1") else surl
    max_retries = 8
    
    for attempt in range(max_retries):
        session, proxy_list = get_session_with_proxy()
        
        # Step 1: Request sharing/link page to extract jsToken
        first_url = f"https://www.1024tera.com/sharing/link?surl={short}"
        try:
            response = session.get(first_url, headers=HEADERS, timeout=12)
            
            # Check for Captcha Block/Need Verify
            if "need verify" in response.text.lower() or '"errno":400141' in response.text:
                print(f"[Attempt {attempt+1}] Captcha verification block triggered. Rotating proxy...")
                if session.proxies and proxy_list:
                    # Remove bad proxy
                    proxy_val = list(session.proxies.values())[0]
                    clean_p = proxy_val.replace("http://", "").replace("https://", "")
                    if clean_p in proxy_list:
                        proxy_list.remove(clean_p)
                continue
                
            match = re.search(r'fn%28%22(.*?)%22%29', response.text)
            if not match:
                print(f"[Attempt {attempt+1}] Could not find jsToken. Retrying...")
                continue
            jsToken = match.group(1)
        except Exception as e:
            print(f"[Attempt {attempt+1}] HTTP error: {e}. Retrying...")
            continue

        # Step 2: Query share/list API using the token
        api_url = "https://www.1024tera.com/share/list"
        params = {
            "app_id": "250528",
            "jsToken": jsToken,
            "site_referer": "https://www.terabox.app/",
            "shorturl": short,
            "root": "1"
        }

        api_headers = {
            "Host": "www.1024tera.com",
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://www.1024tera.com/sharing/link?surl={short}&clearCache=1",
            "Origin": "https://www.1024tera.com"
        }

        try:
            api_response = session.get(api_url, params=params, headers=api_headers, timeout=12)
            data = api_response.json()
            if data.get("errno") != 0 or not data.get("list"):
                # Check for verify in JSON error response
                if data.get("errno") == 400141 or "verify" in data.get("errmsg", "").lower():
                    print(f"[Attempt {attempt+1}] API captcha verification triggered. Rotating...")
                    continue
                return None
            item = data["list"][0]
            return {
                "filename": item.get("server_filename", "video.mp4"),
                "size": int(item.get("size", 0)),
                "dlink": item.get("dlink"),
            }
        except Exception as e:
            print(f"[Attempt {attempt+1}] API error: {e}. Retrying...")
            continue
            
    return None

async def download_file(dlink: str, filename: str, message, total_size: int) -> str:
    """
    Downloads a file from TeraBox to local VPS storage with live progress.
    Downloads directly from the dlink. (Proxies are NOT used for high bandwidth download
    to avoid speed throttling of public free proxies, since dlink itself bypasses verification).
    """
    os.makedirs("downloads", exist_ok=True)
    filepath = f"downloads/{uuid.uuid4().hex[:8]}_{filename}"

    session = curl_requests.Session(impersonate="chrome110")
    session.cookies.update({"ndus": NDUS_COOKIE})

    headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "*/*"
    }

    req = session.get(dlink, headers=headers, stream=True)
    if req.status_code != 200:
        raise Exception(f"TeraBox server error: HTTP {req.status_code}")

    start_time = time.time()
    downloaded = 0

    with open(filepath, "wb") as f:
        for chunk in req.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                await progress_callback(
                    current=downloaded,
                    total=total_size,
                    message=message,
                    action="Downloading to VPS",
                    filename=filename,
                    start_time=start_time,
                )

    return filepath
