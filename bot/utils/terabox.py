import os
import uuid
import re
import time
import asyncio
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests

import config
from bot.utils.progress import progress_callback


def _auth_cookie_header() -> str:
    # Check relative to file directory and current working directory
    file_dir = os.path.dirname(os.path.abspath(__file__)) # bot/utils
    project_root = os.path.dirname(os.path.dirname(file_dir)) # bot/utils -> bot -> root
    paths = [
        os.path.join(project_root, "terabox_cookie_header.txt"),
        "terabox_cookie_header.txt"
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        return content
            except Exception:
                pass
    if config.NDUS_COOKIE:
        return f"ndus={config.NDUS_COOKIE}"
    return ""


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def _origin_from_url(url: str, fallback: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return fallback


def format_curl_proxy(proxy_str: str) -> dict:
    if not proxy_str:
        return {}
    proxy_str = proxy_str.strip()
    # Handle Proxy Cheap format (ip:port:username:password)
    parts = proxy_str.split(":")
    if len(parts) == 4:
        ip, port, user, pwd = parts
        formatted = f"http://{user}:{pwd}@{ip}:{port}"
    else:
        if not proxy_str.startswith("http://") and not proxy_str.startswith("https://"):
            formatted = f"http://{proxy_str}"
        else:
            formatted = proxy_str
            
    return {
        "http": formatted,
        "https": formatted
    }


def _share_list_request(session, origin: str, short: str, js_token: str, timeout: int):
    parsed = urlparse(origin)
    host = parsed.netloc
    api_url = f"{origin}/share/list"
    params = {
        "app_id": "250528",
        "jsToken": js_token,
        "site_referer": "https://www.terabox.app/",
        "shorturl": short,
        "root": "1",
    }
    api_headers = {
        "Host": host,
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{origin}/sharing/link?surl={short}&clearCache=1",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": origin,
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
        print(
            f"Share list failed: HTTP {api_response.status_code}, "
            f"errno={data.get('errno')}, errmsg={data.get('errmsg')}"
        )
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
        res = subprocess.run(
            [sys.executable, script_path, "--headless"],
            capture_output=True,
            text=True,
            timeout=120,
        )
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
    Verifies if the configured NDUS_COOKIE is present.
    If not, runs refresh_cookies.py to perform automated login.
    """
    if not config.NDUS_COOKIE:
        print("NDUS_COOKIE is missing. Triggering auto-cookie-refresh...")
        return trigger_cookie_refresh()
        
    print("NDUS_COOKIE is present. Allowing bot startup. Runtime check will auto-refresh if it is actually expired.")
    return True


def _extract_info_via_session(session, first_url: str, short: str, first_origin: str, cookie_header: str) -> dict | None:
    page_origin = first_origin
    try:
        page_headers = dict(HEADERS)
        if cookie_header:
            page_headers["Cookie"] = cookie_header
        response = session.get(first_url, headers=page_headers, timeout=12, allow_redirects=False)

        if response.status_code in [301, 302]:
            redirect_target = response.headers.get("Location", "")
            print(f"Connection got redirect: {response.status_code} -> {redirect_target}")
            if "verify" not in redirect_target.lower():
                page_origin = _origin_from_url(redirect_target, page_origin)
                response = session.get(redirect_target, headers=page_headers, timeout=12, allow_redirects=False)

        blocked = (
            "verify" in getattr(response, "url", "").lower()
            or "login" in getattr(response, "url", "").lower()
            or "need verify" in response.text.lower()
            or '"errno":400141' in response.text
        )
        if blocked:
            print(f"Connection hit verification/login wall. Final URL: {getattr(response, 'url', '')}, Status Code: {response.status_code}")
            return None

        match = re.search(r'fn%28%22(.*?)%22%29', response.text)
        if not match:
            print("Connection did not return jsToken.")
            return None

        js_token = match.group(1)
        print("Page token extraction successful.")

        api_response = _share_list_request(session, page_origin, short, js_token, timeout=12)
        item = _item_from_share_list_response(api_response)
        if item:
            item["referer"] = f"{page_origin}/sharing/link?surl={short}&clearCache=1"
            item["origin"] = page_origin
            print("Extraction successful.")
            return item
    except Exception as e:
        print(f"Extraction attempt failed: {e}")
    return None


def get_terabox_info(surl: str) -> dict | None:
    """
    Fetches file metadata from TeraBox using static proxy, falling back to direct VPS connection.
    """
    short = surl[1:] if surl.startswith("1") else surl

    session = curl_requests.Session(impersonate="chrome110")
    session.cookies.update({"ndus": config.NDUS_COOKIE})
    cookie_header = _auth_cookie_header()

    first_origin = "https://dm.1024tera.com"
    first_url = f"{first_origin}/sharing/link?surl={short}"

    # Try static proxy first if set
    if config.STATIC_PROXY:
        print("Attempting extraction via configured STATIC_PROXY...")
        session.proxies = format_curl_proxy(config.STATIC_PROXY)
        res = _extract_info_via_session(session, first_url, short, first_origin, cookie_header)
        if res:
            return res
        print("STATIC_PROXY extraction was blocked or failed. Falling back to direct VPS IP...")

    # Fallback to direct VPS connection
    print("Attempting direct connection from VPS IP...")
    session = curl_requests.Session(impersonate="chrome110")
    session.cookies.update({"ndus": config.NDUS_COOKIE})
    return _extract_info_via_session(session, first_url, short, first_origin, cookie_header)


async def download_file(
    dlink: str,
    filename: str,
    message,
    total_size: int,
    referer: str | None = None,
    origin: str | None = None,
) -> str:
    """Downloads directly using VPS IP to preserve full network bandwidth."""
    os.makedirs("downloads", exist_ok=True)
    filepath = f"downloads/{uuid.uuid4().hex[:8]}_{filename}"

    session = curl_requests.Session(impersonate="chrome110")
    session.cookies.update({"ndus": config.NDUS_COOKIE})

    headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }
    if referer:
        headers["Referer"] = referer
    if origin:
        headers["Origin"] = origin
    if config.NDUS_COOKIE:
        headers["Cookie"] = _auth_cookie_header()

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
