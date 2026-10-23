import time
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# --- 設定區域 (保留你的原始設定) ---
USER_ID = os.getenv("MAI_USER")
USER_PW = os.getenv("MAI_PASS")
OUTPUT_FILE = "/home/ubuntu/mai-bot/levels.json"

def run_get_levels():
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

    try:
        # 1. 登入流程 (完全不變)
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

        all_levels = {}

        # 2. 遍歷難度
        diffs = {2: "Expert", 3: "Master", 4: "Re:Master"}
        for diff_id, diff_name in diffs.items():
            print(f"📂 正在開啟 {diff_name} 列表...", flush=True)
            url = f"https://maimaidx-eng.com/maimai-mobile/record/musicGenre/search/?genre=99&diff={diff_id}"
            driver.get(url)
            
            # 注入腳本
            driver.execute_script("""
                (function(d){
                    var s=d.createElement('script');
                    s.src='https://myjian.github.io/mai-tools/scripts/all-in-one.js?t=' + Math.floor(Date.now()/60000);
                    d.body.append(s);
                })(document);
            """)

            # ⭐ 補強：慢慢滾動到底部，觸發 lazy loading 與 JS 計算
            print(f"⌛ 正在滾動並等待 {diff_name} 渲染...")
            for i in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3) # 給予時間讓 JS 處理那一千多首歌

            # 4. 解析資料
            soup = BeautifulSoup(driver.page_source, "html.parser")
            # 4. 解析資料並區分 DX/STD
            # 修改：改為選取包含圖片與分數塊的父層容器
            music_entries = soup.select("div.w_450.m_15.p_r.f_0")
            count = 0
            
            for entry in music_entries:
                try:
                    # 歌曲名稱與等級塊
                    score_block = entry.select_one("div[class*='_score_back']")
                    if not score_block:
                        continue
                    
                    name = score_block.select_one(".music_name_block").text.strip()
                    lv_val = score_block.select_one(".music_lv_block").text.strip()
                    
                    # 🔍 修正：從 entry (父層) 抓取圖標
                    kind_icon = entry.select_one("img.music_kind_icon")
                    # 根據截圖中的檔名判斷
                    chart_type = "DX" if kind_icon and "music_dx.png" in kind_icon.get('src', '') else "STD"

                    if name not in all_levels:
                        all_levels[name] = {}
                    if chart_type not in all_levels[name]:
                        all_levels[name][chart_type] = {}

                    # 存入定數
                    try:
                        all_levels[name][chart_type][diff_name] = float(lv_val)
                    except ValueError:
                        # 如果 JS 還沒渲染完，先存整數等級字串
                        all_levels[name][chart_type][diff_name] = lv_val
                    
                    count += 1
                except Exception as e:
                    continue
            print(f"✅ {diff_name} 解析完成，共處理 {count} 塊資料。", flush=True)

        # 5. 存檔
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_levels, f, ensure_ascii=False, indent=4)
        print(f"\n✨ 定數表已儲存至: {os.path.abspath(OUTPUT_FILE)}")

    finally:
        driver.quit()

if __name__ == "__main__":
    run_get_levels()