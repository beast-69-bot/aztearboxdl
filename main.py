import os
import sys
import asyncio

# Fix for Windows: Playwright needs SelectorEventLoop, not ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from extractor import extract_metadata, normalize_url

from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(
    title="Diskwala Link Extractor & Downloader",
    description="A sleek web application to bypass protection and extract direct download links from Diskwala."
)

# Enable CORS for the browser extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for intercepted links from extension bridge
stored_links = {}

# Ensure static files directory exists
current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

class ExtractRequest(BaseModel):
    url: str

class StoreLinkRequest(BaseModel):
    url: str
    data: dict

class StoreHeadersRequest(BaseModel):
    url: str
    appicrypt: str
    appicrypt_ts: str

class StoreResponseRequest(BaseModel):
    api_url: str
    referer: str
    data: dict

@app.post("/api/store_response")
async def api_store_response(request: StoreResponseRequest):
    """Receives a captured API response body from the CDP extension bridge."""
    import re
    
    print(f"📦 [CDP BRIDGE] Received response from {request.api_url}")
    print(f"   Referer: {request.referer}")
    print(f"   Data keys: {list(request.data.keys())}")
    
    # Use referer (the DiskWala share page) as the lookup key
    page_url = request.referer if request.referer else request.api_url
    share_url = normalize_url(page_url)
    
    if share_url not in stored_links:
        stored_links[share_url] = {}
    stored_links[share_url].update(request.data)
    
    print(f"✅ [CDP BRIDGE] Stored data under key: {share_url}")
    print(f"   Full data: {stored_links[share_url]}")
    
    return {"status": "success", "key": share_url}

@app.post("/api/store_headers")
async def api_store_headers(request: StoreHeadersRequest):
    import httpx
    import re
    
    # Extract file ID from request.url (Referer)
    match = re.search(r"diskwala\.com/app/([a-zA-Z0-9_-]+)", request.url)
    file_id = match.group(1) if match else ""
    
    if not file_id:
        print(f"❌ [BRIDGE] Could not extract file ID from URL: {request.url}")
        return {"status": "error", "detail": "Could not extract file ID"}
        
    # Detect target API URL based on request type
    if "/file/sign" in request.url:
        target_api_url = "https://ddudapidd.diskwala.com/api/v1/file/sign"
    else:
        target_api_url = "https://ddudapidd.diskwala.com/api/v1/file/temp_info"
        
    print(f"🔑 [BRIDGE] Captured Appicrypt headers for file {file_id}. Sending to {target_api_url}...")
    
    # Header mapping
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Appicrypt": request.appicrypt,
        "Appicrypt-Ts": request.appicrypt_ts,
        "Origin": "https://diskwala.com",
        "Referer": "https://diskwala.com/"
    }
    
    # Make request to DiskWala API
    async with httpx.AsyncClient() as client:
        try:
            # We fetch using the valid Appicrypt headers and payload
            res = await client.post(
                target_api_url,
                json={"id": file_id},
                headers=headers,
                timeout=10.0
            )
            
            if res.status_code == 200:
                data = res.json()
                print(f"✅ [BRIDGE] Successfully extracted details from {target_api_url}!")
                
                # Normalize the main URL matching the store
                share_url = normalize_url(request.url)
                if share_url not in stored_links:
                    stored_links[share_url] = {}
                stored_links[share_url].update(data)
                return {"status": "success", "data": data}
            else:
                print(f"❌ [BRIDGE] API request failed with status: {res.status_code} - Body: {res.text}")
                return {"status": "error", "detail": f"API responded with status {res.status_code}"}
        except Exception as e:
            print(f"❌ [BRIDGE] Network request error: {e}")
            return {"status": "error", "detail": str(e)}

@app.post("/api/store_link")
async def api_store_link(request: StoreLinkRequest):
    normalized = normalize_url(request.url)
    if normalized not in stored_links:
        stored_links[normalized] = {}
    
    # Merge the new keys (like merging temp_info metadata with sign download url)
    stored_links[normalized].update(request.data)
    print(f"✨ [BRIDGE] Successfully stored/updated signature details for: {normalized}")
    return {"status": "stored"}

@app.get("/api/get_stored_link")
async def api_get_stored_link(url: str):
    normalized = normalize_url(url)
    if normalized in stored_links:
        data = stored_links[normalized]
        
        # Check for any field that looks like a download URL
        known_url_keys = {"direct_url", "download_url", "download", "url", "fileUrl", 
                          "file_url", "signedUrl", "signed_url", "link", "src", "source"}
        found_url = None
        for key in known_url_keys:
            if key in data and isinstance(data[key], str) and data[key].startswith("http"):
                found_url = data[key]
                break
        
        # Also scan all string values for any http URL
        if not found_url:
            for key, val in data.items():
                if isinstance(val, str) and val.startswith("http"):
                    found_url = val
                    break
        
        if found_url:
            return {
                "status": "success",
                "metadata": data,
                "download_url": found_url
            }
        
        # Data is captured but no URL found yet — might be partial (temp_info only)
        if data:
            return {
                "status": "partial",
                "metadata": data
            }
    
    return {"status": "pending"}

@app.post("/api/extract")
async def api_extract(request: ExtractRequest):
    url = request.url.strip().rstrip('/\\')
    if not url:
        raise HTTPException(status_code=400, detail="Please enter a valid Diskwala URL.")
    
    normalized = normalize_url(url)
    
    # Headless extraction is blocked by AppiCrypt.
    # Return bridge_mode so the frontend switches to bookmarklet/extension mode.
    return {
        "status": "bridge_mode",
        "normalized_url": normalized,
        "message": "AppiCrypt detected. Use the browser bridge to extract the link."
    }


@app.get("/api/beacon")
async def api_beacon(url: str, page: str = ""):
    """
    Image beacon endpoint — receives download URL via a 1x1 image request.
    This works from HTTPS pages because image requests are not subject to CORS.
    The bookmarklet creates an Image() object pointing here to send us the URL.
    """
    from fastapi.responses import Response
    
    if url and url.startswith("http"):
        share_url = normalize_url(page) if page else "unknown"
        
        if share_url not in stored_links:
            stored_links[share_url] = {}
        stored_links[share_url]["download_url"] = url
        stored_links[share_url]["url"] = url
        
        print(f"🎯 [BEACON] Captured URL for {share_url}:")
        print(f"   → {url}")
    
    # Return a tiny 1x1 transparent PNG so the Image() doesn't throw an error
    PNG_1x1 = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    return Response(content=PNG_1x1, media_type="image/png", headers={
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-cache"
    })


@app.get("/")
async def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Static files are not yet created. Please wait."}

# Mount the static directory for CSS and JS files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
