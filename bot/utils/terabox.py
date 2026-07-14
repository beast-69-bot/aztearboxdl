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
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

vps_cached_proxies = []

def get_terabox_info(surl: str) -> dict | None:
    """
    Fetches file metadata from TeraBox using the public share URL ID.
    First tries directly from VPS (since VPS is clean and unblocked).
    If a verification wall is hit, falls back to rotating proxies.
    """
    global vps_cached_proxies
    short = surl[1:] if surl.startswith("1") else surl
    
    # ── FIRST TRY: Direct VPS IP ─────────────────────────────────────
    print("Attempting direct connection from VPS IP...")
    session = curl_requests.Session(impersonate="chrome110")
    session.cookies.update({"ndus": NDUS_COOKIE})
    
    first_url = f"https://www.1024tera.com/sharing/link?surl={short}"
    try:
        # Disable redirects to avoid redirection loop (Max 30 redirects exceeded)
        response = session.get(first_url, headers=HEADERS, timeout=12, allow_redirects=False)
        
        # Check if we were redirected to a login/verify page manually or if it blocks us
        if response.status_code in [301, 302]:
            redirect_target = response.headers.get("Location", "")
            print(f"Direct connection got redirect: {response.status_code} -> {redirect_target}")
            # If not sending to verify page, follow it once
            if "verify" not in redirect_target.lower():
                response = session.get(redirect_target, headers=HEADERS, timeout=12, allow_redirects=False)
        
        if "need verify" not in response.text.lower() and '"errno":400141' not in response.text:
            match = re.search(r'fn%28%22(.*?)%22%29', response.text)
            if match:
                jsToken = match.group(1)
                print("Direct VPS IP extraction successful!")
                
                # Fetch share list
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
                
                api_response = session.get(api_url, params=params, headers=api_headers, timeout=12)
                data = api_response.json()
                if data.get("errno") == 0 and data.get("list"):
                    item = data["list"][0]
                    return {
                        "filename": item.get("server_filename", "video.mp4"),
                        "size": int(item.get("size", 0)),
                        "dlink": item.get("dlink"),
                    }
    except Exception as e:
        print(f"Direct VPS IP extraction failed due to error: {e}. Moving to proxy fallback...")

    # ── SECOND TRY: Fallback to rotating proxies if block occurs ──────
    print("Direct connection failed or blocked. Trying rotating proxies...")
    max_retries = 10
    
    for attempt in range(max_retries):
        session = curl_requests.Session(impersonate="chrome110")
        session.cookies.update({"ndus": NDUS_COOKIE})
        
        # Load or refresh proxies
        if not vps_cached_proxies:
            try:
                vps_cached_proxies = fetch_fresh_proxies()
            except Exception:
                pass
                
        if not vps_cached_proxies:
            time.sleep(1)
            continue
            
        selected_proxy = random.choice(vps_cached_proxies)
        session.proxies = get_proxy_dict(selected_proxy)
        print(f"[Attempt {attempt+1}] Using proxy: {selected_proxy}")
        
        try:
            # Disable redirect loop on proxy queries too
            response = session.get(first_url, headers=HEADERS, timeout=8, allow_redirects=False)
            if response.status_code in [301, 302]:
                redirect_target = response.headers.get("Location", "")
                if "verify" not in redirect_target.lower():
                    response = session.get(redirect_target, headers=HEADERS, timeout=8, allow_redirects=False)
                    
            if "need verify" in response.text.lower() or '"errno":400141' in response.text:
                vps_cached_proxies.remove(selected_proxy)
                continue
                
            match = re.search(r'fn%28%22(.*?)%22%29', response.text)
            if not match:
                continue
            jsToken = match.group(1)
            
            # API Call
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
            
            api_response = session.get(api_url, params=params, headers=api_headers, timeout=8)
            data = api_response.json()
            if data.get("errno") == 0 and data.get("list"):
                item = data["list"][0]
                return {
                    "filename": item.get("server_filename", "video.mp4"),
                    "size": int(item.get("size", 0)),
                    "dlink": item.get("dlink"),
                }
        except Exception:
            if selected_proxy in vps_cached_proxies:
                vps_cached_proxies.remove(selected_proxy)
            continue
            
    return None

async def download_file(dlink: str, filename: str, message, total_size: int) -> str:
    """Downloads directly using VPS IP to preserve full network bandwidth."""
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
