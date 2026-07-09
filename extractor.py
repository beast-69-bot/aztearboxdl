import asyncio
import sys
import re

# Fix for Windows: Playwright requires SelectorEventLoop (not ProactorEventLoop)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def normalize_url(url_or_id: str) -> str:
    """Normalize user input into a full Diskwala app URL."""
    url_or_id = url_or_id.strip().rstrip('/\\')
    
    # If it is already a full URL
    if url_or_id.startswith("http://") or url_or_id.startswith("https://"):
        match = re.search(r"diskwala\.com/(?:app/)?([a-zA-Z0-9_-]+)", url_or_id)
        if match:
            file_id = match.group(1)
            return f"https://diskwala.com/app/{file_id}"
        return url_or_id
    
    # Otherwise treat it as a file ID
    return f"https://diskwala.com/app/{url_or_id}"


async def extract_metadata(url_or_id: str) -> dict:
    """
    Extension/bookmarklet bridge mode:
    This function is no longer the primary extraction method.
    The frontend now uses the browser extension or bookmarklet bridge.
    This is kept as a fallback only.
    """
    raise NotImplementedError(
        "Direct headless extraction is blocked by AppiCrypt. "
        "Please use the browser extension or bookmarklet method."
    )
