import requests
import time
import os
import sys

def main():
    api_url = "https://apiv2.dlterabox.site/api/v3/terabox"
    test_link = "https://1024terabox.com/s/1Y3mGsppFPjSOhljtR33Shg"
    
    print("=== VPS DOWNLOAD DIAGNOSTIC TEST ===")
    print(f"1. Fetching link from API...")
    try:
        r = requests.get(api_url, params={"url": test_link}, timeout=15)
        print(f"API Response Status: {r.status_code}")
        data = r.json()
        dlink = data.get("data", {}).get("file", {}).get("download_url")
        if not dlink:
            print("Error: No dlink in API response")
            print(data)
            return
        print(f"Got Dlink: {dlink[:100]}...")
    except Exception as e:
        print(f"API call failed: {e}")
        return
        
    print("\n2. Testing direct connection to download URL...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive"
    }
    
    try:
        start_time = time.time()
        print("Sending GET request (stream=True)...")
        # Try without proxy
        resp = requests.get(dlink, headers=headers, stream=True, timeout=15)
        print(f"Response Status: {resp.status_code}")
        print("Response Headers:")
        for k, v in resp.headers.items():
            print(f"  {k}: {v}")
            
        print("\nAttempting to read first 1MB...")
        bytes_read = 0
        for chunk in resp.iter_content(chunk_size=1024 * 128):
            if chunk:
                bytes_read += len(chunk)
                print(f"Read {bytes_read / 1024:.1f} KB...")
                if bytes_read >= 1024 * 1024:
                    break
        elapsed = time.time() - start_time
        print(f"\n[SUCCESS] Read {bytes_read / 1024 / 1024:.2f} MB in {elapsed:.2f} seconds!")
        print(f"Speed: {(bytes_read / (1024 * 1024)) / elapsed:.2f} MB/s")
    except Exception as e:
        print(f"\n[ERROR] Direct download failed: {e}")
        
    # Test with Range Header
    print("\n3. Testing Range GET connection...")
    range_headers = dict(headers)
    range_headers["Range"] = "bytes=0-1048576" # 1MB chunk
    try:
        start_time = time.time()
        resp = requests.get(dlink, headers=range_headers, stream=True, timeout=15)
        print(f"Response Status: {resp.status_code}")
        print(f"Content-Range: {resp.headers.get('Content-Range')}")
        print(f"Content-Length: {resp.headers.get('Content-Length')}")
        bytes_read = 0
        for chunk in resp.iter_content(chunk_size=1024 * 128):
            if chunk:
                bytes_read += len(chunk)
        elapsed = time.time() - start_time
        print(f"[SUCCESS] Range request read {bytes_read / 1024 / 1024:.2f} MB in {elapsed:.2f} seconds!")
        print(f"Range Speed: {(bytes_read / (1024 * 1024)) / elapsed:.2f} MB/s")
    except Exception as e:
        print(f"[ERROR] Range download failed: {e}")

if __name__ == "__main__":
    main()
