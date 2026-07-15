import os
import uuid
import re
import time
import asyncio
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests

import config
from bot.utils.progress import progress_callback


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36"
    ),
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
    Verifies if the configured NDUS_COOKIE is valid and active.
    If not, runs refresh_cookies.py and retries.
    """

    def _is_valid():
        if not config.NDUS_COOKIE:
            return False

        session = curl_requests.Session(impersonate="chrome110")
        session.cookies.update({"ndus": config.NDUS_COOKIE})
        api_url = "https://www.terabox.app/api/list?dir=%2F&num=10&page=1"

        try:
            resp = session.get(api_url, headers=HEADERS, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("errno") == 0:
                    return True
        except Exception:
            pass

        return False

    if _is_valid():
        print("NDUS_COOKIE is VALID.")
        return True

    print("NDUS_COOKIE is INVALID/EXPIRED. Triggering auto-cookie-refresh...")
    success = trigger_cookie_refresh()
    if success and _is_valid():
        print("NDUS_COOKIE is now VALID after auto-refresh.")
        return True
    if success:
        print("Auto-refresh script completed, but refreshed NDUS_COOKIE did not validate.")

    if _is_valid():
        print("NDUS_COOKIE verified valid after fallback check.")
        return True

    print("NDUS_COOKIE is still INVALID after auto-refresh.")
    return False


def get_terabox_info(surl: str) -> dict | None:
    """
    Fetches file metadata from TeraBox using direct VPS connection only.
    """
    short = surl[1:] if surl.startswith("1") else surl

    print("Attempting direct connection from VPS IP...")
    session = curl_requests.Session(impersonate="chrome110")
    session.cookies.update({"ndus": config.NDUS_COOKIE})

    first_origin = "https://dm.1024tera.com"
    first_url = f"{first_origin}/sharing/link?surl={short}"
    page_origin = first_origin

    try:
        response = session.get(first_url, headers=HEADERS, timeout=12, allow_redirects=False)

        if response.status_code in [301, 302]:
            redirect_target = response.headers.get("Location", "")
            print(f"Direct connection got redirect: {response.status_code} -> {redirect_target}")
            if "verify" not in redirect_target.lower():
                page_origin = _origin_from_url(redirect_target, page_origin)
                response = session.get(redirect_target, headers=HEADERS, timeout=12, allow_redirects=False)

        blocked = (
            "verify" in getattr(response, "url", "").lower()
            or "login" in getattr(response, "url", "").lower()
            or "need verify" in response.text.lower()
            or '"errno":400141' in response.text
        )
        if blocked:
            print(f"Direct connection hit verification/login wall. Final URL: {response.url}, Status Code: {response.status_code}")
            return None

        match = re.search(r'fn%28%22(.*?)%22%29', response.text)
        if not match:
            print("Direct connection did not return jsToken.")
            return None

        js_token = match.group(1)
        print("Direct VPS page token extraction successful.")

        api_response = _share_list_request(session, page_origin, short, js_token, timeout=12)
        item = _item_from_share_list_response(api_response)
        if item:
            item["referer"] = f"{page_origin}/sharing/link?surl={short}&clearCache=1"
            item["origin"] = page_origin
            print("Direct VPS IP extraction successful.")
            return item
    except Exception as e:
        print(f"Direct VPS IP extraction failed due to error: {e}.")

    return None


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
        headers["Cookie"] = f"ndus={config.NDUS_COOKIE}"

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
