import re
import time
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def get_song_constant_regex(song_name, diff, kind, driver):
    """
    輸入歌名、難度、類型，從 SheetInternalLevel 標籤抓取定數
    """
    # 轉換參數以符合網頁搜尋過濾
    u_diff = diff.lower().replace(":", "")
    u_kind = kind.lower()
    encoded_name = quote(song_name)
    
    # 網址帶入過濾條件，確保頁面只有目標譜面
    target_url = f"https://arcade-songs.zetaraku.dev/maimai/?title={encoded_name}&types={u_kind}&difficulties={u_diff}"
    
    try:
        print(f"🚀 正在開啟頁面: {target_url}")
        driver.get(target_url)
        
        # 必須等待 JS 渲染出 SheetInternalLevel
        time.sleep(1)
        
        html_content = driver.page_source
        
        # --- 針對 SheetInternalLevel 的正則表達式 ---
        # 匹配 <span ... class="SheetInternalLevel">13.7</span>
        # [0-9.]+ 會匹配包含小數點的數字
        pattern = r'class="SheetInternalLevel">([0-9.]+)<'
        
        matches = re.findall(pattern, html_content)
        
        if matches:
            # 拿到第一個匹配到的數字
            constant = matches[0]
            return float(constant)
            
    except Exception as e:
        print(f"⚠️ 抓取 {song_name} 定數時發生錯誤: {e}")
    
    return None

# --- 測試執行區塊 ---
if __name__ == "__main__":
    options = Options()
    # 如果要開無頭模式，取消下面這行註解
    options.add_argument("--headless") 
    
    test_driver = webdriver.Chrome(options=options)
    
    try:
        # 測試範例：月光, master, dx
        name = input("請輸入歌名 (如: 月光): ")
        diff = input("請輸入難度 (如: master): ")
        kind = input("請輸入類型 (如: dx): ")
        
        val = get_song_constant_regex(name, diff, kind, test_driver)
        
        if val:
            print(f"\n✨ 成功獲取定數!")
            print(f"📊 {name} [{diff}] 定數為: {val}")
        else:
            print(f"\n❌ 找不到定數。")
            print("💡 提示: 請確認頁面是否正確出現了帶有數字的藍色正方形標籤。")
            
    finally:
        print("\n測試結束，關閉瀏覽器...")
        test_driver.quit()