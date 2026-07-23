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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


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


def _fetch_file_size_via_range(dlink: str) -> int:
    """Sends a fast Range request (0-1) to get the exact file size in bytes from Content-Range header."""
    try:
        session = curl_requests.Session(impersonate="chrome110")
        if config.STATIC_PROXY:
            session.proxies = format_curl_proxy(config.STATIC_PROXY)
        
        headers = {
            "User-Agent": HEADERS["User-Agent"],
            "Range": "bytes=0-1"
        }
        # Send GET request with Range
        resp = session.get(dlink, headers=headers, timeout=10, allow_redirects=True)
        if resp.status_code == 206:
            content_range = resp.headers.get("Content-Range", "")
            if "/" in content_range:
                total_bytes = int(content_range.split("/")[-1].strip())
                print(f"[API EXTRACT] Extracted file size from Content-Range: {total_bytes} bytes")
                return total_bytes
        # Fallback to Content-Length
        content_length = int(resp.headers.get("Content-Length", 0))
        if content_length > 0:
            return content_length
    except Exception as e:
        print(f"[API EXTRACT] Range size check failed: {e}")
    return 0


def _parse_readable_size(readable_size: str) -> int:
    """Parses a string like '416.55 MB' or '1.2 GB' into bytes."""
    if not readable_size:
        return 0
    try:
        readable_size = readable_size.strip().upper()
        match = re.match(r"([\d\.]+)\s*(KB|MB|GB|TB|B)?", readable_size)
        if not match:
            return 0
        val = float(match.group(1))
        unit = match.group(2)
        if unit == "KB":
            return int(val * 1024)
        elif unit == "MB":
            return int(val * 1024 * 1024)
        elif unit == "GB":
            return int(val * 1024 * 1024 * 1024)
        elif unit == "TB":
            return int(val * 1024 * 1024 * 1024 * 1024)
        return int(val)
    except Exception:
        return 0


def get_terabox_info(surl: str) -> dict | None:
    """
    Fetches file metadata from TeraBox using the high-speed public API.
    """
    # Robust shortcode extraction supporting both raw shortcodes and full URLs
    if "surl=" in surl:
        match = re.search(r"surl=([A-Za-z0-9_-]+)", surl)
        short = match.group(1) if match else surl
    elif "/s/" in surl:
        match = re.search(r"/s/([A-Za-z0-9_-]+)", surl)
        short = match.group(1) if match else surl
    else:
        short = surl
    
    api_url = "https://apiv2.dlterabox.site/api/v3/terabox"
    test_link = f"https://1024terabox.com/s/{short}"
    
    print(f"[API EXTRACT] Attempting API extraction for: {test_link}")
    try:
        session = curl_requests.Session(impersonate="chrome110")
        if config.STATIC_PROXY:
            session.proxies = format_curl_proxy(config.STATIC_PROXY)
            
        headers = {
            "User-Agent": HEADERS["User-Agent"]
        }
        
        resp = session.get(api_url, params={"url": test_link}, headers=headers, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            file_info = data.get("data", {}).get("file", {})
            dlink = file_info.get("download_url") or file_info.get("direct_link")
            filename = file_info.get("file_name", "video.mp4")
            readable_size = file_info.get("size_readable") or data.get("total_size")
            
            if dlink:
                print(f"[API EXTRACT] [OK] API call successful. File: {filename}")
                
                # Fetch exact size in bytes via fast range check
                exact_size = _fetch_file_size_via_range(dlink)
                if exact_size == 0:
                    exact_size = _parse_readable_size(readable_size)
                    
                return {
                    "filename": filename,
                    "size": exact_size,
                    "dlink": dlink,
                    "referer": f"https://1024terabox.com/sharing/link?surl={short}",
                    "origin": "https://1024terabox.com"
                }
            else:
                print(f"[API EXTRACT] API response did not contain download_url. Error: {data.get('error')}")
        else:
            print(f"[API EXTRACT] API returned status code {resp.status_code}")
    except Exception as e:
        print(f"[API EXTRACT] API extraction failed: {e}")
    return None


# ── Multi-Fragment Download Config ────────────────────────────────────────
DOWNLOAD_WORKERS = 8          # parallel connections per file
MIN_CHUNK_SIZE = 2 * 1024 * 1024    # 2 MB minimum — parallel kicks in for most files


def _build_dl_headers(referer=None, origin=None) -> dict:
    h = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
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

    # ── Step 1: Probe download URL for Range support & get content-length ──
    print(f"Probing download URL for Range support: {dlink[:80]}...")
    supports_range = False
    content_length = total_size or 0
    
    try:
        head_session = curl_requests.Session(impersonate="chrome110")
        if config.STATIC_PROXY:
            head_session.proxies = format_curl_proxy(config.STATIC_PROXY)
        head_resp = await asyncio.to_thread(
            head_session.head, dlink, headers=headers, timeout=10, allow_redirects=True
        )
        accept_ranges = head_resp.headers.get("Accept-Ranges", "none").lower()
        content_length = int(head_resp.headers.get("Content-Length", total_size or 0))
        supports_range = accept_ranges == "bytes" and content_length > 0
        print(f"HEAD probe: Accept-Ranges: {accept_ranges} | Content-Length: {content_length} bytes | Range support: {supports_range}")
    except Exception as e:
        print(f"HEAD probe failed ({e}). Trying Range GET probe...")
        
    if not supports_range:
        # Try a quick GET range probe (highly reliable fallback for Cloudflare Workers/Workers reverse proxy)
        try:
            get_session = curl_requests.Session(impersonate="chrome110")
            if config.STATIC_PROXY:
                get_session.proxies = format_curl_proxy(config.STATIC_PROXY)
            
            probe_headers = dict(headers)
            probe_headers["Range"] = "bytes=0-1"
            
            probe_resp = await asyncio.to_thread(
                get_session.get, dlink, headers=probe_headers, timeout=10, allow_redirects=True
            )
            if probe_resp.status_code == 206:
                supports_range = True
                content_range = probe_resp.headers.get("Content-Range", "")
                if "/" in content_range:
                    content_length = int(content_range.split("/")[-1].strip())
                else:
                    content_length = total_size or 0
                print(f"Range GET probe: [OK] SUPPORTED! | Content-Length: {content_length} bytes")
            else:
                print(f"Range GET probe: [FAILED] NOT SUPPORTED (Status Code: {probe_resp.status_code})")
        except Exception as pe:
            print(f"Range GET probe failed: {pe}")

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

        # ── Merge chunk files into final file (Offloaded to thread) ───────
        print(f"Merging {num_workers} chunks → {filepath}")
        def merge_files():
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

        await asyncio.to_thread(merge_files)


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
