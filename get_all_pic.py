import os
import re
import time
import json
import requests
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# --- 設定區域 ---
USER_ID = os.getenv("MAI_USER")
USER_PW = os.getenv("MAI_PASS")
COOKIE_FILE = "cookies.json"
COVER_DIR = "covers"

if not os.path.exists(COVER_DIR):
    os.makedirs(COVER_DIR)

def get_safe_name(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name)

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

def run_sync():
    print("🤖 機器人啟動中...", flush=True)
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new') 
    options.add_argument('--window-size=1920,1080')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # --- 關鍵：還原你的 CDP 繞過設定 ---
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    wait = WebDriverWait(driver, 20)

    try:
        # --- 1. 還原你的完整登入邏輯 ---
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

        # --- 2. 進入 Genre 99 掃描歌名 ---
        print("🔍 正在讀取全歌曲總表 (Genre 99)...", flush=True)
        driver.get("https://maimaidx-eng.com/maimai-mobile/record/musicGenre/search/?genre=99")
        
        # 確保頁面渲染出歌曲方塊
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "music_name_block")))
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        all_song_names = sorted(list(set([div.text.strip() for div in soup.select(".music_name_block")])))
        print(f"✅ 成功獲取 {len(all_song_names)} 首歌曲名稱。", flush=True)

        # --- 3. 檢查缺失並下載 ---
        missing_songs = [n for n in all_song_names if not os.path.exists(os.path.join(COVER_DIR, f"{get_safe_name(n)}.png"))]
        
        if not missing_songs:
            print("✨ 本地封面已齊全，無需更新。", flush=True)
            return

        print(f"📦 準備抓取 {len(missing_songs)} 首新封面...", flush=True)

        for i, name in enumerate(missing_songs):
            print(f"[{i+1}/{len(missing_songs)}] 搜尋: {name}", flush=True)
            driver.get(f"https://arcade-songs.zetaraku.dev/maimai/?title={quote(name)}")
            
            time.sleep(3.5) # 給予 SPA 渲染時間
            
            html = driver.page_source
            # 使用 Regex 抓取
            pattern = r'https://dp4p6x0xfi5o9\.cloudfront\.net/maimai/img/cover-m/[a-z0-9]+\.png'
            match = re.search(pattern, html)
            
            if not match:
                match = re.search(r'https://dp4p6x0xfi5o9\.cloudfront\.net/maimai/img/cover/[a-z0-9]+\.png', html)

            if match:
                img_url = match.group(0)
                try:
                    img_data = requests.get(img_url, timeout=10).content
                    with open(os.path.join(COVER_DIR, f"{get_safe_name(name)}.png"), 'wb') as f:
                        f.write(img_data)
                    print(f"  ✅ 下載成功")
                except:
                    print(f"  ❌ 下載失敗")
            else:
                print(f"  ⚠️ 找不到圖源")
            
            time.sleep(0.3)

    except Exception as e:
        print(f"💥 流程中斷: {e}", flush=True)
    finally:
        driver.quit()
        print("\n🏁 同步結束。", flush=True)

if __name__ == "__main__":
    run_sync()