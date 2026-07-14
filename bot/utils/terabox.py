import os
import uuid
import re
import time
import random
import asyncio
from urllib.parse import urlparse
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

def _origin_from_url(url: str, fallback: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return fallback

def _share_list_request(session, origin: str, short: str, js_token: str, timeout: int):
    parsed = urlparse(origin)
    host = parsed.netloc
    api_url = f"{origin}/share/list"
    params = {
        "app_id": "250528",
        "jsToken": js_token,
        "site_referer": "https://www.terabox.app/",
        "shorturl": short,
        "root": "1"
    }
    api_headers = {
        "Host": host,
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{origin}/sharing/link?surl={short}&clearCache=1",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": origin
    }
    print(f"Fetching share list from {api_url} ...")
    return session.get(api_url, params=params, headers=api_headers, timeout=timeout)

def _item_from_share_list_response(api_response) -> dict | None:
    try:
        data = api_response.json()
    except Exception as err:
        print(f"Share list JSON parse failed: HTTP {api_response.status_code}: {err}")
        return None

    if data.get("errno") != 0 or not data.get("list"):
        print(f"Share list failed: HTTP {api_response.status_code}, errno={data.get('errno')}, errmsg={data.get('errmsg')}")
        return None

    item = data["list"][0]
    dlink = item.get("dlink")
    if not dlink:
        print("Share list returned an item but no dlink.")
        return None

    return {
        "filename": item.get("server_filename", "video.mp4"),
        "size": int(item.get("size", 0)),
        "dlink": dlink,
    }

def check_ndus_cookie() -> bool:
    """
    Verifies if the configured NDUS_COOKIE is valid and active.
    Returns True if valid, False otherwise.
    """
    if not NDUS_COOKIE:
        print("❌ Error: NDUS_COOKIE is not configured in your .env file!")
        return False

    session = curl_requests.Session(impersonate="chrome110")
    session.cookies.update({"ndus": NDUS_COOKIE})
    
    # Try calling the account space API first
    try:
        api_url = "https://www.1024tera.com/api/box/space"
        resp = session.get(api_url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("errno") == 0:
                print("✅ NDUS_COOKIE is VALID (Space info retrieved successfully).")
                return True
    except Exception:
        pass

    # Fallback check: Request the main sharing link page and verify if we get redirected to a verify/login page
    try:
        test_url = "https://www.1024tera.com/sharing/link?surl=tKDPsB5RNnjdWLwoLcCFyg"
        resp = session.get(test_url, headers=HEADERS, timeout=8, allow_redirects=False)
        if resp.status_code in [301, 302]:
            redirect_target = resp.headers.get("Location", "").lower()
            if "verify" in redirect_target or "login" in redirect_target:
                print("❌ NDUS_COOKIE is INVALID/EXPIRED (Redirected to login/verify page).")
                return False
        if "need verify" in resp.text.lower() or '"errno":400141' in resp.text:
            print("❌ NDUS_COOKIE is INVALID/EXPIRED (Hit verify wall).")
            return False
            
        print("✅ NDUS_COOKIE appears VALID (Sharing page accessed without login/verify redirect).")
        return True
    except Exception as e:
        print(f"⚠️ NDUS_COOKIE validation connection failed: {e}")
        return False

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
        response = session.get(first_url, headers=HEADERS, timeout=12)
        
        # Check if we were redirected to a login/verify page or hit verify wall
        if "verify" in response.url.lower() or "login" in response.url.lower() or "need verify" in response.text.lower() or '"errno":400141' in response.text:
            print("Direct connection hit verification/login wall.")
        else:
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
            response = session.get(first_url, headers=HEADERS, timeout=10)
            
            if "verify" in response.url.lower() or "login" in response.url.lower() or "need verify" in response.text.lower() or '"errno":400141' in response.text:
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
            
            api_response = session.get(api_url, params=params, headers=api_headers, timeout=10)
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

    print(f"Connecting to download link: {dlink} ...")
    req = await asyncio.to_thread(
        session.get, dlink, headers=headers, stream=True, timeout=20
    )
    if req.status_code != 200:
        raise Exception(f"TeraBox server error: HTTP {req.status_code}")

    print("Connection established. Beginning file download stream...")
    start_time = time.time()
    downloaded = 0

    iterator = req.iter_content(chunk_size=1024 * 1024)

    def get_next_chunk(it):
        try:
            return next(it)
        except StopIteration:
            return None
        except Exception as err:
            print(f"Error reading chunk: {err}")
            raise err

    with open(filepath, "wb") as f:
        while True:
            chunk = await asyncio.to_thread(get_next_chunk, iterator)
            if chunk is None:
                break
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

    print(f"File download completed successfully: {filepath}")
    return filepath
