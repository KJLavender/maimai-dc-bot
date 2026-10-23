import time
import json
import os
import sys
from fetch_rating_analysis import fetch_friend_b50_analysis
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- 設定區域 ---
USER_ID = os.getenv("MAI_USER")
USER_PW = os.getenv("MAI_PASS")
COOKIE_FILE = "cookies.json"

if len(sys.argv) > 1:
    TARGET_FRIEND_ID = sys.argv[1]
else:
    TARGET_FRIEND_ID = ""

def save_cookies(driver):
    all_cookies = driver.get_cookies()
    filtered = [c for c in all_cookies if "maimaidx-eng.com" in c.get('domain', '')]
    with open(COOKIE_FILE, "w") as f:
        json.dump(filtered, f)
    print("💾 Cookie 已存檔", flush=True)

def load_cookies(driver):
    if not os.path.exists(COOKIE_FILE): return False
    try:
        with open(COOKIE_FILE, "r") as f:
            cookies = json.load(f)
        for cookie in cookies:
            if 'expiry' in cookie: cookie['expiry'] = int(cookie['expiry'])
            if 'sameSite' in cookie: del cookie['sameSite']
            try:
                driver.add_cookie(cookie)
            except: continue
        return True
    except: return False

def run_full_process():
    print("🤖 機器人啟動中...", flush=True)
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new') 
    options.add_argument('--window-size=1920,1080')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    wait = WebDriverWait(driver, 20)

    """try:"""
    driver.get("https://maimaidx-eng.com/maimai-mobile/")
    login_needed = True
    
    if load_cookies(driver):
        driver.get("https://maimaidx-eng.com/maimai-mobile/home/")
        if "home" in driver.current_url and "200002" not in driver.page_source:
            print("⚡ Cookie 有效，快速跳轉！", flush=True)
            login_needed = False

    if login_needed:
        print("🔑 執行完整帳密登入...", flush=True)
        driver.get("https://maimaidx-eng.com/maimai-mobile/")
        sega_id_entry = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "c-button--openid--segaId")))
        driver.execute_script("arguments[0].click();", sega_id_entry)
        
        agree_checkbox = wait.until(EC.presence_of_element_located((By.ID, "agree")))
        driver.execute_script("arguments[0].click();", agree_checkbox)
        
        wait.until(EC.presence_of_element_located((By.ID, "sid")))
        driver.execute_script(f"document.getElementById('sid').value = '{USER_ID}';")
        driver.execute_script(f"document.getElementById('password').value = '{USER_PW}';")
        
        login_btn = driver.find_element(By.ID, "btnSubmit")
        driver.execute_script("arguments[0].click();", login_btn)
        
        wait.until(EC.url_contains("home"))
        print("🎉 登入成功！", flush=True)
        save_cookies(driver)

    # 呼叫分析
    final_image_path = fetch_friend_b50_analysis(driver, TARGET_FRIEND_ID)
    if final_image_path:
        print(f"OUTPUT_FILE:{final_image_path}", flush=True)
    else:
        print("❌ 分析失敗，未產生圖片", flush=True)
    """
    except Exception as e:
        print(f"❌ 流程崩潰: {e}", flush=True)
    finally:
        driver.quit()"""

if __name__ == "__main__":
    run_full_process()