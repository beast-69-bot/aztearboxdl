import os
import re
import sys
import json
import asyncio
import argparse
import base64
import urllib.request
import urllib.parse
import ssl

# Reconfigure stdout to use UTF-8 on Windows to prevent encoding errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Parse command line arguments
parser = argparse.ArgumentParser(description="TeraBox Cookie Refresher")
parser.add_argument("--headless", action="store_true", help="Run the browser in headless mode")
args = parser.parse_args()

# Determine workspace directory dynamically
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))

# Manual dotenv loader to remove python-dotenv dependency
def manual_load_dotenv(dotenv_path):
    if not os.path.exists(dotenv_path):
        return
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")

# Determine paths dynamically based on workspace structure
if os.path.isdir(os.path.join(WORKSPACE_DIR, "aztearboxdl")):
    # Local Windows Dev Environment
    AZ_ENV = os.path.join(WORKSPACE_DIR, "aztearboxdl", ".env")
    TERA_ENV = os.path.join(WORKSPACE_DIR, "TeraBox-Dl", ".env")
    TERA_PY = os.path.join(WORKSPACE_DIR, "TeraBox-Dl", "terabox.py")
    PARENT_DIR = os.path.dirname(WORKSPACE_DIR)
else:
    # VPS Linux Environment (inside aztearboxdl root)
    AZ_ENV = os.path.join(WORKSPACE_DIR, ".env")
    TERA_ENV = os.path.join(os.path.dirname(WORKSPACE_DIR), "TeraBox-Dl", ".env")
    TERA_PY = os.path.join(os.path.dirname(WORKSPACE_DIR), "TeraBox-Dl", "terabox.py")
    PARENT_DIR = os.path.dirname(WORKSPACE_DIR)

# Load credentials from .env
manual_load_dotenv(os.path.join(WORKSPACE_DIR, ".env"))
manual_load_dotenv(AZ_ENV)

USER_EMAIL = os.getenv("TERABOX_EMAIL")
USER_PASS = os.getenv("TERABOX_PASSWORD")
TWO_CAPTCHA_API_KEY = os.getenv("TWO_CAPTCHA_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
STATIC_PROXY = os.getenv("STATIC_PROXY")

# Find the AZ NETWORK TG BOTS directory dynamically (handles different casing/separators)
def find_bots_dir(parent):
    options = ["AZ NETWORK TG BOTS", "AZ-NETWORK-TG-BOTS", "az-network-tg-bots", "az_network_tg_bots"]
    for opt in options:
        path = os.path.join(parent, opt)
        if os.path.isdir(path):
            return path
    return os.path.join(parent, "AZ NETWORK TG BOTS") # fallback

BOTS_DIR = find_bots_dir(PARENT_DIR)

# Destination Paths to Update
TARGET_PATHS = {
    "az_dotenv": AZ_ENV,
    "tera_dotenv": TERA_ENV,
    "tera_py": TERA_PY,
    "fap1_dotenv": os.path.join(BOTS_DIR, "faphouse_bots", "faphouse1", ".env"),
    "fap2_dotenv": os.path.join(BOTS_DIR, "faphouse_bots", "faphouse2", ".env"),
    "fap3_dotenv": os.path.join(BOTS_DIR, "faphouse_bots", "faphouse3", ".env"),
    "faphouse_cookies_txt": os.path.join(BOTS_DIR, "faphouse_cookies.txt"),
}

def telegram_send_photo(photo_path, caption):
    """Send a photo/screenshot to the admin via the Telegram Bot API using urllib."""
    if not BOT_TOKEN or not ADMIN_ID or ADMIN_ID == "0":
        return False
        
    if not os.path.exists(photo_path):
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            file_content = f.read()
            
        boundary = "----TelegramFormBoundary1234567890"
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }
        
        parts = []
        # Chat ID field
        parts.append(f"--{boundary}\r\n".encode())
        parts.append('Content-Disposition: form-data; name="chat_id"\r\n\r\n'.encode())
        parts.append(f"{ADMIN_ID}\r\n".encode())
        
        # Caption field
        parts.append(f"--{boundary}\r\n".encode())
        parts.append('Content-Disposition: form-data; name="caption"\r\n\r\n'.encode())
        parts.append(f"{caption}\r\n".encode())
        
        # Photo field
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="photo"; filename="{os.path.basename(photo_path)}"\r\n'.encode())
        parts.append('Content-Type: image/png\r\n\r\n'.encode())
        parts.append(file_content)
        parts.append('\r\n'.encode())
        
        # End boundary
        parts.append(f"--{boundary}--\r\n".encode())
        
        body = b"".join(parts)
        req = urllib.request.Request(url, data=body, headers=headers)
        
        # Bypass SSL check for Telegram API on VPS
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=15.0, context=ctx) as res:
            res_data = json.loads(res.read().decode('utf-8'))
            if res_data.get("ok"):
                print(f"[TELEGRAM] Sent screenshot to admin {ADMIN_ID}.")
                return True
    except Exception as e:
        print(f"[TELEGRAM ERROR] Failed to send photo: {e}")
    return False

def parse_playwright_proxy(proxy_str):
    if not proxy_str:
        return None
    proxy_str = proxy_str.strip()
    
    # 1. Check for format ip:port:username:password
    parts = proxy_str.split(":")
    if len(parts) == 4:
        ip, port, user, pwd = parts
        return {
            "server": f"http://{ip}:{port}",
            "username": user,
            "password": pwd
        }
        
    # 2. Check for format http://user:pass@ip:port
    from urllib.parse import urlparse
    try:
        parsed = urlparse(proxy_str)
        if not parsed.scheme:
            parsed = urlparse("http://" + proxy_str)
        server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        res = {"server": server}
        if parsed.username:
            res["username"] = parsed.username
        if parsed.password:
            res["password"] = parsed.password
        return res
    except Exception:
        return None

def build_cookie_header(cookies):
    """Build a Cookie header from Playwright cookies for TeraBox domains."""
    allowed_domains = ("terabox.com", "terabox.app", "1024tera.com", "1024terabox.com")
    pairs = []
    seen = set()
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        domain = cookie.get("domain", "")
        if not name or value is None:
            continue
        if not any(allowed in domain for allowed in allowed_domains):
            continue
        if name in seen:
            continue
        seen.add(name)
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)

def get_cookie_value(cookies, name):
    for cookie in cookies:
        if cookie.get("name") == name and cookie.get("value"):
            return cookie["value"]
    return None

def urllib_verify_cookie_header(cookie_header):
    """Verify whether a browser Cookie header is accepted by TeraBox API."""
    if not cookie_header:
        return False

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie_header,
    }

    url = "https://www.terabox.com/api/list?dir=%2F&num=10&page=1"
    req = urllib.request.Request(url, headers=headers)
    try:
        # Bypass SSL verification to prevent issues on VPS
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=10.0, context=ctx) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                print(f"[INFO] Cookie API validation errno={data.get('errno')}, request_id={data.get('request_id')}")
                return data.get("errno") == 0
    except Exception as e:
        print(f"[WARN] Cookie API validation failed: {e}")
    return False

def urllib_verify_ndus(ndus):
    """Verify if the ndus cookie is currently valid using urllib."""
    if not ndus:
        return False
    return urllib_verify_cookie_header(f"ndus={ndus}")

def urllib_solve_2captcha(api_key, image_bytes):
    """Solve the captcha image using 2Captcha API and urllib."""
    encoded_string = base64.b64encode(image_bytes).decode('utf-8')
    submit_url = "https://2captcha.com/in.php"
    payload = {
        "method": "base64",
        "key": api_key,
        "body": encoded_string,
        "json": 1
    }
    
    try:
        data_encoded = urllib.parse.urlencode(payload).encode('utf-8')
        req = urllib.request.Request(submit_url, data=data_encoded)
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, data=data_encoded, timeout=15.0, context=ctx) as res:
            res_data = json.loads(res.read().decode('utf-8'))
            if res_data.get("status") != 1:
                print(f"[2CAPTCHA ERROR] Submission failed: {res_data.get('request')}")
                return None
            captcha_id = res_data["request"]
            print(f"[2CAPTCHA] Submitted successfully. ID: {captcha_id}. Waiting for solution...")
            
            # Poll for solution
            poll_url = f"https://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1"
            for attempt in range(30):
                import time
                time.sleep(2)
                req_poll = urllib.request.Request(poll_url)
                with urllib.request.urlopen(req_poll, timeout=10.0, context=ctx) as res_poll:
                    poll_data = json.loads(res_poll.read().decode('utf-8'))
                    if poll_data.get("status") == 1:
                        code = poll_data["request"]
                        print(f"[2CAPTCHA] Solved: {code}")
                        return code
                    elif poll_data.get("request") == "CAPCHA_NOT_READY":
                        continue
                    else:
                        print(f"[2CAPTCHA ERROR] Polling failed: {poll_data.get('request')}")
                        return None
    except Exception as e:
        print(f"[2CAPTCHA ERROR] Request failed: {e}")
    return None

def update_env_variable(env_path, key, value):
    """Update a specific key-value pair in a .env file."""
    if not os.path.exists(env_path):
        return False
    
    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    new_lines = []
    updated = False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            updated = True
        else:
            new_lines.append(line)
            
    if not updated:
        new_lines.append(f"{key}={value}\n")
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    return True

def update_files(new_ndus, cookie_header=None):
    """Propagate the new ndus cookie to all required target configurations."""
    print("[INFO] Propagating new cookie to all bots...")
    
    # 1. Update aztearboxdl/.env
    if update_env_variable(TARGET_PATHS["az_dotenv"], "NDUS_COOKIE", new_ndus):
        print("[SUCCESS] Updated aztearboxdl/.env")
    if cookie_header and update_env_variable(TARGET_PATHS["az_dotenv"], "TERABOX_COOKIE_HEADER", cookie_header):
        print("[SUCCESS] Updated aztearboxdl/.env full cookie header")
        
    # 2. Update TeraBox-Dl/.env
    if update_env_variable(TARGET_PATHS["tera_dotenv"], "COOKIE_JSON", f'{{"ndus": "{new_ndus}"}}'):
        print("[SUCCESS] Updated TeraBox-Dl/.env")
        
    # 3. Update TeraBox-Dl/terabox.py (hardcoded cookie)
    py_path = TARGET_PATHS["tera_py"]
    if os.path.exists(py_path):
        with open(py_path, "r", encoding="utf-8") as f:
            py_content = f.read()
        pattern = r'("ndus":\s*")[a-zA-Z0-9_-]+(")'
        new_content = re.sub(pattern, rf'\1{new_ndus}\2', py_content)
        with open(py_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("[SUCCESS] Updated TeraBox-Dl/terabox.py")
        
    # 4. Update faphouse bots .env files
    for key in ["fap1_dotenv", "fap2_dotenv", "fap3_dotenv"]:
        if update_env_variable(TARGET_PATHS[key], "NDUS_COOKIE", new_ndus):
            print(f"[SUCCESS] Updated {os.path.basename(os.path.dirname(TARGET_PATHS[key]))}/.env")
            
    # 5. Update faphouse_cookies.txt
    txt_path = TARGET_PATHS["faphouse_cookies_txt"]
    if os.path.exists(txt_path) or os.path.exists(os.path.dirname(txt_path)):
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"{new_ndus}\n")
        print("[SUCCESS] Updated faphouse_cookies.txt")

async def perform_autologin():
    """Launch Playwright browser, type credentials, detect captcha and solve manually or via 2Captcha."""
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        user_data_dir = os.path.join(WORKSPACE_DIR, ".terabox_session")
        
        # Parse static proxy if defined in .env
        proxy_opts = parse_playwright_proxy(STATIC_PROXY)
        
        context_args = {
            "user_data_dir": user_data_dir,
            "headless": args.headless,
            "viewport": {"width": 1280, "height": 800},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        if proxy_opts:
            context_args["proxy"] = proxy_opts
            print(f"[INFO] Launching Chromium (headless={args.headless}) using profile {user_data_dir} via STATIC_PROXY: {proxy_opts['server']}...")
        else:
            print(f"[INFO] Launching Chromium (headless={args.headless}) using profile {user_data_dir}...")
            
        context = await p.chromium.launch_persistent_context(**context_args)
        
        page = await context.new_page()
        
        # Helper to capture debug screenshot, notify bot, and exit
        async def save_debug_and_exit(error_msg):
            debug_path = os.path.join(WORKSPACE_DIR, "debug_screenshot.png")
            try:
                await page.screenshot(path=debug_path)
                print(f"[DEBUG] Saved failure screenshot to: {debug_path}")
                clean_msg = re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', error_msg)
                telegram_send_photo(debug_path, f"❌ *TeraBox Auto\\-Login Failed\\!*\nError: {clean_msg}")
            except Exception as e:
                print(f"[WARN] Failed to capture debug screenshot: {e}")
            await context.close()
            return None
            
        # 1. Navigate to TeraBox
        print("[INFO] Navigating to TeraBox...")
        try:
            await page.goto("https://www.terabox.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000) # Wait for page redirects and cookies to load
        except Exception as e:
            return await save_debug_and_exit(f"Navigation failed: {e}")
            
        async def collect_browser_session(label):
            """Collect cookies from the persistent browser profile and verify full cookie context."""
            cookies = await context.cookies()
            ndus_val = get_cookie_value(cookies, "ndus")
            cookie_header = build_cookie_header(cookies)
            names = sorted({c.get("name", "") for c in cookies if c.get("name")})
            print(f"[INFO] {label}: collected {len(cookies)} cookies. Names: {', '.join(names[:30])}")
            print(f"[INFO] {label}: ndus present={bool(ndus_val)}, full cookie header length={len(cookie_header)}")

            if cookie_header and urllib_verify_cookie_header(cookie_header):
                print(f"[SUCCESS] {label}: full browser cookie header is valid.")
                return ndus_val, cookie_header

            if ndus_val and urllib_verify_ndus(ndus_val):
                print(f"[SUCCESS] {label}: ndus cookie is valid.")
                return ndus_val, f"ndus={ndus_val}"

            return ndus_val, cookie_header

        async def is_logged_in_ui():
            """Best-effort UI check. Avoids clearing a valid browser profile just because API validation is strict."""
            # 1. Check URL redirect
            url = page.url.lower()
            if any(path in url for path in ["/main", "/webmaster", "/disk"]):
                return True

            # 2. Check visual dashboard indicators
            logged_in_selectors = [
                "text=AI Notebook",
                "text=Tera AI",
                "text=Home",
                "text=Shared Presentation",
                ".u-avatar",
                ".avatar",
                ".personal-info",
                "text=Sign Out",
                "text=Log Out"
            ]
            for selector in logged_in_selectors:
                try:
                    locator = page.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible(timeout=200):
                        return True
                except Exception:
                    continue
            return False

        # 2. Check if already logged in. Do not clear cookies just because ndus-only API validation fails.
        try:
            print("[INFO] Checking if session is already logged in...")
            # Poll for up to 8 seconds for dashboard redirect or UI indicators to settle
            is_logged_in = False
            for _ in range(16):
                if await is_logged_in_ui():
                    is_logged_in = True
                    break
                await page.wait_for_timeout(500)

            ndus_val, cookie_header = await collect_browser_session("Initial browser session")
            
            # We strictly require the API check to pass.
            # If the API check fails (even if visual page seems active due to caching), we perform a fresh login.
            if cookie_header and urllib_verify_cookie_header(cookie_header):
                print("[SUCCESS] Browser session is already logged in and active!")
                await context.close()
                return ndus_val, cookie_header

            print("[INFO] Browser session is not usable. Clearing expired cookies to perform clean login...")
            await context.clear_cookies()
            # Reload page so the form is clean and doesn't have stale/expired cookie states
            await page.goto("https://www.terabox.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[WARN] Error during session validation: {e}")
            
        # 3. Perform Login Flow (if not logged in)
        try:
            login_btn = page.locator(".login-btn").first
            await login_btn.wait_for(state="visible", timeout=5000)
            await login_btn.click()
            await page.wait_for_timeout(2000)
        except Exception:
            pass
            
        print("[INFO] Opening Email login dialog...")
        try:
            email_logo = page.locator(".other-item .logo").nth(1)
            await email_logo.wait_for(state="visible", timeout=5000)
            await email_logo.click()
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"[ERROR] Could not click email tab logo: {e}")
            return await save_debug_and_exit(f"Could not click email tab logo: {e}")
            
        print("[INFO] Entering credentials...")
        try:
            await page.locator("input[placeholder*='email']").first.fill(USER_EMAIL)
            await page.locator("input[type='password']").first.fill(USER_PASS)
            await page.wait_for_timeout(500)
            
            await page.locator(".btn-class-login").first.click()
            print("[INFO] Credentials submitted. Waiting for authentication response...")
            
            # Poll for up to 15 seconds for captcha OR success cookies
            for _ in range(30):
                await page.wait_for_timeout(500)
                
                # Stop waiting if captcha is visible
                captcha_input = page.locator("input[placeholder*='verification code']").first
                if await captcha_input.count() > 0:
                    break
                    
                # Stop waiting if ndus cookie is set
                cookies = await context.cookies()
                ndus_val = next((c["value"] for c in cookies if c["name"] == "ndus"), None)
                if ndus_val:
                    break
        except Exception as e:
            return await save_debug_and_exit(f"Failed to input credentials: {e}")
            
        # 4. Handle CAPTCHA / verification puzzle
        attempt_limit = 3
        for try_num in range(attempt_limit):
            captcha_input = page.locator("input[placeholder*='verification code']")
            if await captcha_input.count() > 0 or "verification" in page.url.lower():
                print(f"\n[WARNING] CAPTCHA / Verification challenge detected! (Attempt {try_num+1}/{attempt_limit})")
                
                # Locate the canvas captcha image
                canvas_locator = page.locator("#canvas").first
                try:
                    await canvas_locator.wait_for(state="visible", timeout=5000)
                except Exception:
                    pass
                
                # Extract captcha image directly from browser canvas memory to prevent cropping/cuts
                captcha_img_path = os.path.join(WORKSPACE_DIR, "captcha.png")
                try:
                    import base64
                    base64_str = await page.evaluate("""() => {
                        const canvas = document.querySelector('#canvas');
                        return canvas ? canvas.toDataURL('image/png') : null;
                    }""")
                    if base64_str and "," in base64_str:
                        img_data = base64.b64decode(base64_str.split(",")[1])
                        with open(captcha_img_path, "wb") as f:
                            f.write(img_data)
                        print("[INFO] Successfully extracted raw captcha image from canvas memory.")
                    else:
                        raise Exception("Canvas image data is empty or invalid.")
                except Exception as e:
                    print(f"[WARN] Failed to extract canvas via memory: {e}. Falling back to screenshot...")
                    try:
                        await canvas_locator.screenshot(path=captcha_img_path)
                    except Exception:
                        try:
                            await page.screenshot(path=captcha_img_path)
                        except Exception:
                            pass
                
                # Send captcha notification to Telegram Bot if available
                telegram_send_photo(
                    captcha_img_path, 
                    f"⚠️ *TeraBox CAPTCHA Detected\\!* \\(Attempt {try_num+1}/{attempt_limit}\\)\nSolving automatically if 2Captcha API Key is set\\."
                )
                
                code = None
                # Check if 2Captcha API Key is set
                if TWO_CAPTCHA_API_KEY:
                    print("[2CAPTCHA] Found API Key. Attempting automatic solving...")
                    try:
                        if os.path.exists(captcha_img_path):
                            with open(captcha_img_path, "rb") as image_file:
                                image_bytes = image_file.read()
                        else:
                            image_bytes = await canvas_locator.screenshot()
                        code = urllib_solve_2captcha(TWO_CAPTCHA_API_KEY, image_bytes)
                    except Exception as e:
                        print(f"[2CAPTCHA ERROR] Automatic solve failed: {e}")
                
                # Fallback to Manual terminal input if 2Captcha failed or is missing
                if not code:
                    print(f"[ACTION REQUIRED] Please open the image '{captcha_img_path}' to see the code.")
                    if sys.stdin.isatty():
                        code = input(">>> Enter the 4-letter CAPTCHA code shown in the image: ").strip()
                    else:
                        print("[ERROR] Non-interactive environment. Cannot solve captcha without terminal input.")
                        await context.close()
                        return None
                
                if code:
                    try:
                        # Clear field first
                        await captcha_input.first.click()
                        await page.keyboard.press("Control+A")
                        await page.keyboard.press("Backspace")
                        
                        await captcha_input.first.fill(code)
                        await page.wait_for_timeout(500)
                        

                        try:
                            # Search for the Confirm button in closest ancestor div elements
                            confirm_btn = None
                            for level in range(1, 6):
                                xpath_selector = f"xpath=ancestor::div[{level}]"
                                btn = captcha_input.locator(xpath_selector).locator("button, input[type='submit'], .confirm-btn, [class*='confirm'], :has-text('Confirm')").first
                                if await btn.count() > 0:
                                    confirm_btn = btn
                                    break
                            
                            if confirm_btn:
                                print(f"[INFO] Clicking found confirm button at ancestor level...")
                                await confirm_btn.click()
                            else:
                                # Fallback to page-wide confirm button click
                                await page.locator("button:has-text('Confirm'), .confirm-btn, [class*='confirm']").first.click()
                        except Exception as e:
                            print(f"[WARN] Failed to click confirm button: {e}")
                        
                        print("[INFO] Captcha submitted. Waiting for session initialization...")
                        
                        # Poll for up to 12 seconds for the ndus cookie to appear
                        cookie_found = False
                        for i in range(24):
                            await page.wait_for_timeout(500)
                            
                            # Scan for visible error/toast/tip alerts on the page
                            try:
                                alert_selectors = [
                                    "[class*='error']", "[class*='toast']", "[class*='message']", 
                                    "[class*='tip']", ".alert", "[class*='warn']", "[class*='popup']"
                                ]
                                for sel in alert_selectors:
                                    elements = page.locator(sel)
                                    count = await elements.count()
                                    for idx in range(count):
                                        el = elements.nth(idx)
                                        if await el.is_visible():
                                            txt = (await el.text_content() or "").strip()
                                            if txt and len(txt) < 150:  # avoid printing huge logs
                                                print(f"[PAGE ALERT] {txt}")
                            except Exception:
                                pass
                                
                            cookies = await context.cookies()
                            if any(c["name"] == "ndus" for c in cookies):
                                cookie_found = True
                                break
                                
                        if cookie_found:
                            print("[INFO] New ndus cookie successfully detected in browser context.")
                            break
                    except Exception as e:
                        print(f"[ERROR] Failed to submit captcha: {e}")
            else:
                break
            
        # 5. Success verification
        ndus_val, cookie_header = await collect_browser_session("Post-login browser session")
        if cookie_header and (urllib_verify_cookie_header(cookie_header) or ndus_val):
            # Clean up captcha file if exists
            captcha_img_path = os.path.join(WORKSPACE_DIR, "captcha.png")
            if os.path.exists(captcha_img_path):
                try:
                    os.remove(captcha_img_path)
                except Exception:
                    pass
            await context.close()
            return ndus_val, cookie_header
             
        # If we got here, verification failed
        return await save_debug_and_exit("Login failed: ndus cookie was not found or was invalid after completing flow.")

async def main():
    print("--- TeraBox Auto-Login & Cookie Refresh Utility ---")
    if not USER_EMAIL or not USER_PASS:
        print("[ERROR] Credentials not found in .env. Please set TERABOX_EMAIL and TERABOX_PASSWORD.")
        sys.exit(1)
        
    # Configure global proxy for urllib calls if STATIC_PROXY is set
    if STATIC_PROXY:
        try:
            proxy_opts = parse_playwright_proxy(STATIC_PROXY)
            if proxy_opts:
                proxy_url = proxy_opts['server']
                if "username" in proxy_opts:
                    server_clean = proxy_url.replace("http://", "").replace("https://", "")
                    proxy_url = f"http://{proxy_opts['username']}:{proxy_opts['password']}@{server_clean}"
                proxy_support = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
                opener = urllib.request.build_opener(proxy_support)
                urllib.request.install_opener(opener)
                print(f"[INFO] Configured global proxy for urllib verification calls via STATIC_PROXY: {proxy_opts['server']}")
        except Exception as e:
            print(f"[WARN] Failed to configure global proxy for urllib: {e}")
        
    # Check if current cookie is still valid
    current_ndus = None
    current_cookie_header = None
    if os.path.exists(TARGET_PATHS["az_dotenv"]):
        with open(TARGET_PATHS["az_dotenv"], "r") as f:
            content = f.read()
        match = re.search(r"NDUS_COOKIE=(.*)", content)
        if match:
            current_ndus = match.group(1).strip()
        match = re.search(r"TERABOX_COOKIE_HEADER=(.*)", content)
        if match:
            current_cookie_header = match.group(1).strip()
             
    print("[INFO] Verifying current session cookie...")
    if urllib_verify_cookie_header(current_cookie_header) or urllib_verify_ndus(current_ndus):
        print("[SUCCESS] Current cookie is already valid! Synchronizing configs just in case...")
        update_files(current_ndus, current_cookie_header)
        return
        
    print("[INFO] Cookie is invalid or expired. Initializing automated login...")
    result = await perform_autologin()
    
    if result:
        new_ndus, cookie_header = result
        print("[SUCCESS] Successfully logged in and retrieved valid ndus cookie!")
        update_files(new_ndus, cookie_header)
    else:
        print("[ERROR] Failed to login or retrieve valid ndus cookie.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
