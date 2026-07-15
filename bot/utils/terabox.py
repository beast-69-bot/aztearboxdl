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
    """Fetches share list ANONYMOUSLY (no cookie) to bypass errno 400141 block."""
    parsed = urlparse(origin)
    host = parsed.netloc
    api_url = f"{origin}/share/list"
    params = {
        "app_id": "250528",
        "jsToken": js_token,
        "shorturl": short,
        "root": "1",
    }
    # NOTE: No Cookie header here — anonymous call bypasses the 400141 verification block.
    api_headers = {
        "Host": host,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{origin}/sharing/link?surl={short}",
        "Origin": origin,
    }
    print(f"Fetching share list anonymously from {api_url} ...")
    return session.get(api_url, params=params, headers=api_headers, timeout=timeout)


def _item_from_share_list_response(api_response) -> dict | None:
    """Parses share list response. Returns item metadata even without dlink."""
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
    return {
        "filename": item.get("server_filename", "video.mp4"),
        "size": int(item.get("size", 0)),
        "dlink": item.get("dlink", ""),   # may be empty for anonymous calls
        "path": item.get("path", ""),
        "fs_id": item.get("fs_id", ""),
    }


def _get_dlink_via_filemetas(
    session, origin: str, path: str, js_token: str, cookie_header: str, timeout: int = 12
) -> str | None:
    """
    Fetches the premium download link (dlink) using /api/filemetas with auth cookie.
    This endpoint is separate from the sharing API and is NOT affected by the
    errno 400141 verification block that hits /sharing/link and /share/list.
    """
    import urllib.parse
    target = urllib.parse.quote(f'["{path}"]')
    api_url = f"{origin}/api/filemetas"
    params = {
        "app_id": "250528",
        "jsToken": js_token,
        "target": f'["{path}"]',
        "dlink": "1",
    }
    headers = {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{origin}/disk/home",
        "Cookie": cookie_header,
    }
    print(f"Fetching premium dlink via /api/filemetas for path: {path[:60]} ...")
    try:
        resp = session.get(api_url, params=params, headers=headers, timeout=timeout)
        data = resp.json()
        errno = data.get("errno", -1)
        if errno != 0:
            print(f"filemetas returned errno={errno}, errmsg={data.get('errmsg')}")
            return None
        info_list = data.get("info", [])
        if info_list and info_list[0].get("dlink"):
            dlink = info_list[0]["dlink"]
            print(f"Got premium dlink via filemetas: {dlink[:60]}...")
            return dlink
        print(f"filemetas response had no dlink. Keys: {list(data.keys())}")
    except Exception as e:
        print(f"filemetas request failed: {e}")
    return None


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
    """
    Two-phase extraction strategy to bypass errno 400141:
      Phase 1 — Anonymous: Fetch HTML page + call /share/list WITHOUT cookie.
                           TeraBox allows anonymous access; cookie triggers verification block.
      Phase 2 — Authenticated: Use cookie with /api/filemetas to get premium dlink.
                               This endpoint is NOT affected by the sharing API block.
    """
    page_origin = first_origin
    try:
        # ── PHASE 1: Anonymous HTML fetch → jsToken ──────────────────────
        # IMPORTANT: No Cookie here. With cookie, /sharing/link returns errno 400141.
        anon_page_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        print(f"Fetching page anonymously (no cookie): {first_url}")
        response = session.get(first_url, headers=anon_page_headers, timeout=12, allow_redirects=True)

        if response.status_code not in [200]:
            print(f"Anonymous page fetch failed: HTTP {response.status_code}")
            return None

        # Check if we got JSON error instead of HTML (shouldn't happen without cookie)
        if '"errno"' in response.text[:200]:
            print(f"Anonymous page returned JSON error: {response.text[:200]}")
            return None

        match = re.search(r'fn%28%22(.*?)%22%29', response.text)
        if not match:
            print("jsToken not found in anonymous HTML page.")
            return None

        js_token = match.group(1)
        print(f"jsToken extracted (anonymous). Length: {len(js_token)}")

        # ── PHASE 1b: Anonymous /share/list → file metadata ──────────────
        # Also no cookie here. We confirmed this returns errno:0 with file info.
        api_response = _share_list_request(session, page_origin, short, js_token, timeout=12)
        item = _item_from_share_list_response(api_response)
        if not item:
            print("Anonymous share/list failed to return file metadata.")
            return None

        print(f"File metadata retrieved: '{item['filename']}' ({item['size']} bytes)")

        # ── PHASE 2: Authenticated /api/filemetas → premium dlink ─────────
        # Cookie is used HERE (not above). filemetas is NOT affected by sharing API block.
        dlink = item.get("dlink", "")
        if not dlink and item.get("path") and cookie_header:
            print("No dlink in anonymous response. Fetching premium dlink via /api/filemetas...")
            dlink = _get_dlink_via_filemetas(
                session, page_origin, item["path"], js_token, cookie_header
            )

        if not dlink:
            print("Could not obtain dlink from either share/list or filemetas.")
            return None

        item["dlink"] = dlink
        item["referer"] = f"{page_origin}/sharing/link?surl={short}"
        item["origin"] = page_origin
        print(f"Extraction successful. dlink obtained.")
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


# ── Multi-Fragment Download Config ────────────────────────────────────────
DOWNLOAD_WORKERS = 5          # parallel connections per file
MIN_CHUNK_SIZE = 10 * 1024 * 1024   # 10 MB minimum per chunk


def _build_dl_headers(referer=None, origin=None) -> dict:
    h = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
        "Cookie": _auth_cookie_header(),
    }
    if referer:
        h["Referer"] = referer
    if origin:
        h["Origin"] = origin
    return h


def _download_chunk(dlink: str, start: int, end: int, headers: dict, filepath_chunk: str, timeout: int = 60) -> int:
    """Download a single byte-range chunk and write to a temp file. Returns bytes downloaded."""
    chunk_headers = dict(headers)
    chunk_headers["Range"] = f"bytes={start}-{end}"
    session = curl_requests.Session(impersonate="chrome110")
    if config.STATIC_PROXY:
        session.proxies = format_curl_proxy(config.STATIC_PROXY)
    resp = session.get(dlink, headers=chunk_headers, stream=True, timeout=timeout)
    if resp.status_code not in (200, 206):
        raise Exception(f"Chunk download failed: HTTP {resp.status_code} for range {start}-{end}")
    downloaded = 0
    with open(filepath_chunk, "wb") as f:
        for data in resp.iter_content(chunk_size=512 * 1024):
            if data:
                f.write(data)
                downloaded += len(data)
    return downloaded


async def download_file(
    dlink: str,
    filename: str,
    message,
    total_size: int,
    referer: str | None = None,
    origin: str | None = None,
) -> str:
    """
    Downloads from TeraBox using multi-fragment parallel chunks (HTTP Range requests).
    With N workers, effective speed = N × per-connection speed.
    Falls back to single-stream if server does not support Range.
    """
    os.makedirs("downloads", exist_ok=True)
    safe_name = filename.replace("/", "_").replace("\\", "_")
    filepath = f"downloads/{uuid.uuid4().hex[:8]}_{safe_name}"
    headers = _build_dl_headers(referer, origin)

    # ── Step 1: HEAD request — check Range support & get content-length ──
    print(f"Probing download URL for Range support: {dlink[:80]}...")
    try:
        head_session = curl_requests.Session(impersonate="chrome110")
        head_resp = await asyncio.to_thread(
            head_session.head, dlink, headers=headers, timeout=15, allow_redirects=True
        )
        accept_ranges = head_resp.headers.get("Accept-Ranges", "none").lower()
        content_length = int(head_resp.headers.get("Content-Length", total_size or 0))
        supports_range = accept_ranges == "bytes" and content_length > 0
        print(f"Accept-Ranges: {accept_ranges} | Content-Length: {content_length} bytes | Range support: {supports_range}")
    except Exception as e:
        print(f"HEAD request failed ({e}). Assuming no Range support.")
        supports_range = False
        content_length = total_size or 0

    # Use actual content length if we have it
    file_size = content_length or total_size

    # ── Step 2: Decide strategy ───────────────────────────────────────────
    num_workers = DOWNLOAD_WORKERS if supports_range and file_size >= MIN_CHUNK_SIZE else 1
    print(f"Download strategy: {num_workers} parallel worker(s) for {file_size / 1024 / 1024:.1f} MB")

    start_time = time.time()

    if num_workers == 1:
        # ── Single-stream fallback ────────────────────────────────────────
        print("Using single-stream download...")
        session = curl_requests.Session(impersonate="chrome110")
        req = await asyncio.to_thread(
            session.get, dlink, headers=headers, stream=True, timeout=30
        )
        if req.status_code != 200:
            raise Exception(f"TeraBox server error: HTTP {req.status_code}")

        downloaded = 0
        iterator = req.iter_content(chunk_size=1024 * 1024)

        def get_next(it):
            try:
                return next(it)
            except StopIteration:
                return None

        with open(filepath, "wb") as f:
            while True:
                chunk = await asyncio.to_thread(get_next, iterator)
                if chunk is None:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                await progress_callback(
                    current=downloaded, total=file_size,
                    message=message, action="Downloading (1x)", filename=filename, start_time=start_time,
                )
    else:
        # ── Multi-fragment parallel download ──────────────────────────────
        chunk_size = file_size // num_workers
        ranges = []
        for i in range(num_workers):
            start = i * chunk_size
            end = (file_size - 1) if i == num_workers - 1 else (start + chunk_size - 1)
            ranges.append((start, end))

        print(f"Splitting into {num_workers} chunks:")
        chunk_files = []
        for i, (s, e) in enumerate(ranges):
            cf = f"{filepath}.part{i}"
            chunk_files.append(cf)
            print(f"  Chunk {i}: bytes {s}–{e} ({(e-s+1)/1024/1024:.1f} MB) → {cf}")

        # Track total downloaded across all workers
        downloaded_per_chunk = [0] * num_workers
        total_downloaded = 0

        async def download_chunk_async(idx: int, start: int, end: int, chunk_file: str):
            nonlocal total_downloaded
            bytes_done = await asyncio.to_thread(
                _download_chunk, dlink, start, end, headers, chunk_file
            )
            downloaded_per_chunk[idx] = bytes_done
            total_downloaded = sum(downloaded_per_chunk)
            return bytes_done

        # Progress reporter task
        async def report_progress():
            while total_downloaded < file_size:
                await progress_callback(
                    current=total_downloaded, total=file_size,
                    message=message,
                    action=f"Downloading ({num_workers}x parallel)",
                    filename=filename, start_time=start_time,
                )
                await asyncio.sleep(3)

        # Run all chunks in parallel + progress reporter
        tasks = [download_chunk_async(i, s, e, chunk_files[i]) for i, (s, e) in enumerate(ranges)]
        progress_task = asyncio.create_task(report_progress())

        results = await asyncio.gather(*tasks, return_exceptions=True)
        progress_task.cancel()

        # Check for errors
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                raise Exception(f"Chunk {i} failed: {r}")

        # ── Merge chunk files into final file ─────────────────────────────
        print(f"Merging {num_workers} chunks → {filepath}")
        with open(filepath, "wb") as out:
            for cf in chunk_files:
                with open(cf, "rb") as part:
                    while True:
                        data = part.read(4 * 1024 * 1024)
                        if not data:
                            break
                        out.write(data)
                os.remove(cf)
                print(f"  Merged and removed: {cf}")

        elapsed = time.time() - start_time
        avg_speed = file_size / elapsed / 1024 / 1024 if elapsed > 0 else 0
        print(f"Multi-fragment download complete! Avg speed: {avg_speed:.1f} MB/s")

        # Final progress update
        await progress_callback(
            current=file_size, total=file_size,
            message=message,
            action=f"Downloading ({num_workers}x parallel)",
            filename=filename, start_time=start_time,
        )

    print(f"File download completed: {filepath}")
    return filepath
