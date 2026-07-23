import time
import os
import sys

# Try importing curl_cffi
try:
    from curl_cffi import requests
except ImportError:
    print("[ERROR] curl_cffi not found")
    sys.exit(1)

# Import config to get STATIC_PROXY
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    import config
    STATIC_PROXY = config.STATIC_PROXY
except Exception as e:
    print(f"[WARN] Could not load config: {e}")
    STATIC_PROXY = None

def format_curl_proxy(proxy_str: str) -> dict:
    if not proxy_str:
        return {}
    proxy_str = proxy_str.strip()
    parts = proxy_str.split(":")
    if len(parts) == 4:
        ip, port, user, pwd = parts
        formatted = f"http://{user}:{pwd}@{ip}:{port}"
    else:
        if not proxy_str.startswith("http://") and not proxy_str.startswith("https://"):
            formatted = f"http://proxy_str"
        else:
            formatted = proxy_str
    return {"http": formatted, "https": formatted}

def main():
    api_url = "https://apiv2.dlterabox.site/api/v3/terabox"
    test_link = "https://1024terabox.com/s/1Y3mGsppFPjSOhljtR33Shg"
    
    print("=== VPS DOWNLOAD DIAGNOSTIC TEST (PROXY CHECK) ===")
    print(f"Loaded STATIC_PROXY: {STATIC_PROXY}")
    
    try:
        r = requests.get(api_url, params={"url": test_link}, timeout=15)
        dlink = r.json().get("data", {}).get("file", {}).get("download_url")
        if not dlink:
            print("Error: No dlink")
            return
    except Exception as e:
        print(f"API call failed: {e}")
        return

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive"
    }

    if STATIC_PROXY:
        print("\n4. Testing download connection THROUGH PROXY...")
        proxies = format_curl_proxy(STATIC_PROXY)
        print(f"Using formatted proxy: {proxies}")
        
        try:
            start_time = time.time()
            resp = requests.get(dlink, headers=headers, proxies=proxies, stream=True, timeout=15)
            print(f"Proxy Response Status: {resp.status_code}")
            print("Proxy Response Headers:")
            for k, v in resp.headers.items():
                print(f"  {k}: {v}")
                
            print("\nAttempting to read first 1MB through proxy...")
            bytes_read = 0
            for chunk in resp.iter_content(chunk_size=1024 * 128):
                if chunk:
                    bytes_read += len(chunk)
                    print(f"Proxy Read {bytes_read / 1024:.1f} KB...")
                    if bytes_read >= 1024 * 1024:
                        break
            elapsed = time.time() - start_time
            print(f"\n[PROXY SUCCESS] Read {bytes_read / 1024 / 1024:.2f} MB in {elapsed:.2f} seconds!")
            print(f"Proxy Speed: {(bytes_read / (1024 * 1024)) / elapsed:.2f} MB/s")
        except Exception as e:
            print(f"\n[PROXY ERROR] Download through proxy failed: {e}")
    else:
        print("\n[INFO] No STATIC_PROXY configured in .env, skipping proxy test.")

if __name__ == "__main__":
    main()
