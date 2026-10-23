import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

USER_ID = os.getenv("MAI_USER")
USER_PW = os.getenv("MAI_PASS")
TARGET_FRIEND_CODE = sys.argv[1] if len(sys.argv) > 1 else ""

def run_add_friend_process():
    if not TARGET_FRIEND_CODE:
        print("❌ 未提供好友代碼", flush=True)
        return

    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    # 偽裝成一般瀏覽器，避免被擋
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 20)

    try:
        # 1. 登入
        driver.get("https://maimaidx-eng.com/maimai-mobile/")
        login_btn = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "c-button--openid--segaId")))
        driver.execute_script("arguments[0].click();", login_btn)
        
        wait.until(EC.presence_of_element_located((By.ID, "agree")))
        driver.execute_script("document.getElementById('agree').click();")
        driver.execute_script(f"document.getElementById('sid').value = '{USER_ID}';")
        driver.execute_script(f"document.getElementById('password').value = '{USER_PW}';")
        driver.execute_script("document.getElementById('btnSubmit').click();")

        # 2. 搜尋好友
        wait.until(EC.url_contains("home"))
        driver.get(f"https://maimaidx-eng.com/maimai-mobile/friend/search/searchUser/?friendCode={TARGET_FRIEND_CODE}")
        
        print("⏳ 正在確認搜尋結果...", flush=True)
        time.sleep(3)

        # 3. 判斷搜尋結果
        page_html = driver.page_source
        if "WRONG CODE" in page_html:
            print("ERROR_WRONG_CODE", flush=True)
            return

        # 4. 取得邀請所需的隱藏參數 (idx & token)
        # 在搜尋結果頁面的 Form 裡面會有這兩個值
        try:
            # 嘗試抓取畫面上的邀請表單數據
            idx = driver.find_element(By.NAME, "idx").get_attribute("value")
            token_val = driver.find_element(By.NAME, "token").get_attribute("value")
            
            print(f"🔧 獲取憑證成功，準備送出邀請...", flush=True)

            # --- 關鍵暴力法：直接 POST 請求到邀請 URL ---
            # 這樣就不需要去點那個會跳彈窗的按鈕了
            driver.execute_script(f"""
                var form = document.createElement('form');
                form.method = 'POST';
                form.action = 'https://maimaidx-eng.com/maimai-mobile/friend/search/invite/';
                
                var inputIdx = document.createElement('input');
                inputIdx.type = 'hidden';
                inputIdx.name = 'idx';
                inputIdx.value = '{idx}';
                form.appendChild(inputIdx);
                
                var inputToken = document.createElement('input');
                inputToken.type = 'hidden';
                inputToken.name = 'token';
                inputToken.value = '{token_val}';
                form.appendChild(inputToken);
                
                var inputInvite = document.createElement('input');
                inputInvite.type = 'hidden';
                inputInvite.name = 'invite';
                inputInvite.value = '';
                form.appendChild(inputInvite);
                
                document.body.appendChild(form);
                form.submit();
            """)
            
            time.sleep(5)
            print("SUCCESS_REQUEST_SENT", flush=True)

        except Exception:
            # 如果找不到 idx，可能是已經加過好友或代碼失效
            if "Rating" in page_html or "Rating" in driver.page_source:
                print("ERROR_ALREADY_FRIEND_OR_FULL", flush=True)
            else:
                # 存下目前的畫面以便檢查
                driver.save_screenshot(os.path.join(os.getcwd(), "debug_error.png"))
                print(f"❌ 找不到邀請資訊，請檢查 debug_error.png", flush=True)

    except Exception as e:
        print(f"❌ 系統錯誤: {str(e)[:50]}", flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    run_add_friend_process()