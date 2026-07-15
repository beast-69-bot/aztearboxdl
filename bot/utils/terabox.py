import os
import uuid
import re
import time
import random
import asyncio
from urllib.parse import urlparse
from curl_cffi import requests as curl_requests
import config
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

def trigger_cookie_refresh() -> bool:
    import subprocess
    import sys
    print("[AUTO-REFRESH] Expired or invalid cookie detected. Running refresh_cookies.py...")
    
    # Locate refresh_cookies.py script dynamically
    current_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = None
    check_dir = current_dir
    for _ in range(5):
        temp_path = os.path.join(check_dir, "refresh_cookies.py")
        if os.path.exists(temp_path):
            script_path = temp_path
            break
        temp_path = os.path.join(check_dir, "aztearboxdl", "refresh_cookies.py")
        if os.path.exists(temp_path):
            script_path = temp_path
            break
        check_dir = os.path.dirname(check_dir)
        
    if not script_path:
        script_path = "/home/root2/aztearboxdl/refresh_cookies.py"
        
    print(f"[AUTO-REFRESH] Running: {script_path}")
    try:
        res = subprocess.run([sys.executable, script_path, "--headless"], capture_output=True, text=True, timeout=120)
        print(f"[AUTO-REFRESH] Output: {res.stdout.strip()}")
        if res.stderr:
            print(f"[AUTO-REFRESH] Error: {res.stderr.strip()}")
            
        if res.returncode == 0:
            config.reload_ndus()
            print(f"[AUTO-REFRESH] Reloaded config. New NDUS_COOKIE: {config.NDUS_COOKIE[:15]}...")
            return True
    except Exception as e:
        print(f"[AUTO-REFRESH ERROR] Failed to execute refresh script: {e}")
    return False

def check_ndus_cookie() -> bool:
    """
    Verifies if the configured NDUS_COOKIE is valid and active.
    If not, runs refresh_cookies.py and retries.
    """
    def _is_valid():
        global vps_cached_proxies
        if not config.NDUS_COOKIE:
            return False
            
        session = curl_requests.Session(impersonate="chrome110")
        session.cookies.update({"ndus": config.NDUS_COOKIE})
        api_url = "https://www.terabox.app/api/list?dir=%2F&num=10&page=1"
        
        # 1. Try direct connection
        try:
            resp = session.get(api_url, headers=HEADERS, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("errno") == 0:
                    return True
        except Exception:
            pass
            
        # 2. Try using proxies if direct connection was blocked/failed
        try:
            if not vps_cached_proxies:
                vps_cached_proxies = fetch_fresh_proxies()
            if vps_cached_proxies:
                # Try up to 5 different proxies
                sample_size = min(5, len(vps_cached_proxies))
                selected_proxies = random.sample(vps_cached_proxies, sample_size)
                for selected_proxy in selected_proxies:
                    proxy = get_proxy_dict(selected_proxy)
                    print(f"[INFO] Direct cookie check blocked. Retrying validation using proxy: {selected_proxy}")
                    try:
                        resp = session.get(api_url, headers=HEADERS, proxies=proxy, timeout=5)
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("errno") == 0:
                                return True
                    except Exception:
                        pass
        except Exception:
            pass
            
        return False

    if _is_valid():
        print("✅ NDUS_COOKIE is VALID.")
        return True
        
    print("❌ NDUS_COOKIE is INVALID/EXPIRED. Triggering auto-cookie-refresh...")
    success = trigger_cookie_refresh()
    if success:
        print("✅ NDUS_COOKIE is now VALID after auto-refresh.")
        return True
        
    if _is_valid():
        print("✅ NDUS_COOKIE verified valid after fallback check.")
        return True
        
    print("❌ NDUS_COOKIE is still INVALID after auto-refresh.")
    return False

def get_terabox_info(surl: str) -> dict | None:
    """
    Fetches file metadata from TeraBox using the public share URL ID.
    First tries directly from VPS. If cookie errors occur, triggers auto-refresh and retries.
    """
    global vps_cached_proxies
    short = surl[1:] if surl.startswith("1") else surl
    
    # ── FIRST TRY: Direct VPS IP ─────────────────────────────────────
    print("Attempting direct connection from VPS IP...")
    session = curl_requests.Session(impersonate="chrome110")
    session.cookies.update({"ndus": config.NDUS_COOKIE})
    
    first_url = f"https://dm.1024tera.com/sharing/link?surl={short}"
    try:
        response = session.get(first_url, headers=HEADERS, timeout=12)
        
        # Check if we were redirected to a login/verify page or hit verify wall
        if "verify" in response.url.lower() or "login" in response.url.lower() or "need verify" in response.text.lower() or '"errno":400141' in response.text:
            print(f"Direct connection hit verification/login wall. Triggering auto-cookie-refresh...")
            trigger_cookie_refresh()
            # Retry with new cookie
            session.cookies.update({"ndus": config.NDUS_COOKIE})
            response = session.get(first_url, headers=HEADERS, timeout=12)
        else:
            match = re.search(r'fn%28%22(.*?)%22%29', response.text)
            if match:
                jsToken = match.group(1)
                print("Direct VPS IP extraction successful!")
                
                # Fetch share list
                api_url = "https://dm.1024tera.com/share/list"
                params = {
                    "app_id": "250528",
                    "jsToken": jsToken,
                    "site_referer": "https://www.terabox.app/",
                    "shorturl": short,
                    "root": "1"
                }
                api_headers = {
                    "Host": "dm.1024tera.com",
                    "User-Agent": HEADERS["User-Agent"],
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"https://dm.1024tera.com/sharing/link?surl={short}&clearCache=1",
                    "Origin": "https://dm.1024tera.com"
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
        session.cookies.update({"ndus": config.NDUS_COOKIE})
        
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
            api_url = "https://dm.1024tera.com/share/list"
            params = {
                "app_id": "250528",
                "jsToken": jsToken,
                "site_referer": "https://www.terabox.app/",
                "shorturl": short,
                "root": "1"
            }
            api_headers = {
                "Host": "dm.1024tera.com",
                "User-Agent": HEADERS["User-Agent"],
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"https://dm.1024tera.com/sharing/link?surl={short}&clearCache=1",
                "Origin": "https://dm.1024tera.com"
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
    session.cookies.update({"ndus": config.NDUS_COOKIE})

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
