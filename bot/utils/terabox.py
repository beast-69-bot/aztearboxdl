import os
import uuid
import time
from curl_cffi import requests as curl_requests
from config import NDUS_COOKIE
from bot.utils.progress import progress_callback


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36"
    )
}


def get_terabox_info(surl: str) -> dict | None:
    """
    Fetches file metadata from TeraBox using the public share URL ID.
    Returns a dict with filename, size, and dlink, or None on failure.
    """
    short = surl[1:] if surl.startswith("1") else surl
    api_url = (
        f"https://www.1024tera.com/api/shorturlinfo?shorturl={short}"
        f"&root=1&channel=dubox&clienttype=0&web=1&dp-logid=0"
    )
    try:
        session = curl_requests.Session(impersonate="chrome110")
        session.cookies.update({"ndus": NDUS_COOKIE})
        resp = session.get(api_url, headers=HEADERS, timeout=15)
        data = resp.json()
        if data.get("errno") != 0 or not data.get("list"):
            return None
        item = data["list"][0]
        return {
            "filename": item.get("server_filename", "video.mp4"),
            "size": int(item.get("size", 0)),
            "dlink": item.get("dlink"),
        }
    except Exception:
        return None


async def download_file(dlink: str, filename: str, message, total_size: int) -> str:
    """
    Downloads a file from TeraBox to local VPS storage with live progress.
    Returns the local file path.
    """
    os.makedirs("downloads", exist_ok=True)
    filepath = f"downloads/{uuid.uuid4().hex[:8]}_{filename}"

    session = curl_requests.Session(impersonate="chrome110")
    session.cookies.update({"ndus": NDUS_COOKIE})

    req = session.get(dlink, headers=HEADERS, stream=True)
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
