import re
import time
import math
import json
import os
import requests
import pandas as pd
from urllib.parse import quote
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from generate_b50_image import generate_b50_image, last_profile
from song_data import fetch_songs_data, get_internal_level, search_songs, find_best_match
from b50_history import save_result

LEVELS_FILE = "/home/ubuntu/levels.json"

def get_constant_logic(current_levels, name, kind, diff_label, driver=None):
    """
    整合多重來源的定數取得邏輯：
    1. 本地快取 (levels.json)
    2. CloudFront JSON 資料庫 (模糊匹配)
    3. Selenium 抓取 (最慢的備案)
    """
    # 1. 優先檢查本地快取
    if name in current_levels and kind in current_levels[name] and diff_label in current_levels[name][kind]:
        val = current_levels[name][kind][diff_label]
        if val is not None: return float(val)

    # 2. 從 CloudFront JSON 資料庫取得 (快速，不需要 Selenium)
    json_val = get_internal_level(name, kind, diff_label)
    if json_val:
        # 寫入本地快取
        if name not in current_levels: current_levels[name] = {}
        if kind not in current_levels[name]: current_levels[name][kind] = {}
        current_levels[name][kind][diff_label] = json_val
        with open(LEVELS_FILE, "w", encoding="utf-8") as f:
            json.dump(current_levels, f, ensure_ascii=False, indent=4)
        print(f"✨ [JSON] 成功取得定數: {name} -> {json_val}", flush=True)
        return json_val

    # 3. 備案：使用 Selenium 從 Zetaraku 抓取
    if not driver: return None

    # 記錄目前的對戰頁面網址，以便抓完後跳回
    battle_url = driver.current_url
    
    try:
        # 轉換參數以符合 Zetaraku 網頁過濾
        u_diff = diff_label.lower().replace(":", "")
        u_kind = "dx" if kind == "DX" else "std"
        encoded_name = quote(name)
        
        # 組合目標網址
        target_url = f"https://arcade-songs.zetaraku.dev/maimai/?title={encoded_name}&types={u_kind}&difficulties={u_diff}"
        
        print(f"🌐 正在抓取定數: {name} ({diff_label})...", flush=True)
        
        # 直接跳轉到定數網站
        driver.get(target_url)
        
        # 必須等待 JS 渲染出 SheetInternalLevel，設定 3.5 秒確保穩定
        time.sleep(2.5) 
        
        html_content = driver.page_source
        
        # 匹配 <span ... class="SheetInternalLevel">定數</span>
        pattern = r'class="SheetInternalLevel">([0-9.]+)<'
        matches = re.findall(pattern, html_content)
        
        if matches:
            val = float(matches[0])
            
            # 更新字典快取
            if name not in current_levels: current_levels[name] = {}
            if kind not in current_levels[name]: current_levels[name][kind] = {}
            current_levels[name][kind][diff_label] = val
            
            # 寫入 levels.json
            with open(LEVELS_FILE, "w", encoding="utf-8") as f:
                json.dump(current_levels, f, ensure_ascii=False, indent=4)
            
            print(f"✨ 成功同步定數: {name} -> {val}", flush=True)
            
            # 抓完後，跳回原本的對戰頁面
            driver.get(battle_url)
            # 等待對戰頁面載入完成
            WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CLASS_NAME, "w_450")))
            
            return val
        else:
            print(f"❌找不到({name})的定數!請通知管理員", flush=True)

    except Exception as e:
        print(f"⚠️ 補完失敗 ({name}): {e}", flush=True)
        # 失敗也要跳回原本的頁面，確保後續歌曲繼續執行
        driver.get(battle_url)
    
    return None

def get_new_songs_whitelist(session, driver):
    """抓取新歌白名單"""
    whitelist = set()
    url = "https://maimaidx-eng.com/maimai-mobile/record/musicVersion/search/"
    try:
        session.headers.update({"User-Agent": driver.execute_script("return navigator.userAgent")})
        resp = session.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        select_box = soup.find("select", {"name": "version"})
        
        if not select_box:
            driver.get(url)
            time.sleep(2)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            select_box = soup.find("select", {"name": "version"})

        if select_box:
            options = select_box.find_all("option")
            vids = sorted([int(o.get("value")) for o in options if o.get("value").isdigit()])
            for vid in vids[-2:]:
                v_resp = session.get(f"{url}?version={vid}")
                v_soup = BeautifulSoup(v_resp.text, "html.parser")
                for b in v_soup.select("div[class*='_score_back']"):
                    name = b.find("div", class_="music_name_block").text.strip()
                    kind_img = b.find("img", class_="music_kind_icon")
                    kind = "STD" if kind_img and "music_standard.png" in kind_img.get("src") else "DX"
                    whitelist.add((name, kind))
            print(f"✅ 成功獲取 {len(whitelist)} 首新歌", flush=True)
    except Exception as e:
        print(f"⚠️ 白名單獲取失敗: {e}", flush=True)
    return whitelist

def calculate_r(achievement, constant):
    calc_ach = min(achievement, 100.5)
    if achievement >= 100.5: coeff = 22.4
    elif achievement >= 100.0: coeff = 21.6
    elif achievement >= 99.5:  coeff = 21.1
    elif achievement >= 99.0:  coeff = 20.8
    elif achievement >= 98.0:  coeff = 20.3
    elif achievement >= 97.0:  coeff = 20.0
    elif achievement >= 94.0:  coeff = 16.8
    elif achievement >= 90.0:  coeff = 15.2
    elif achievement >= 80.0:  coeff = 13.6
    else: coeff = 12.0
    return math.floor(constant * coeff * (calc_ach / 100))

def fetch_friend_b50_analysis(driver, friend_idx):
    session = requests.Session()
    for cookie in driver.get_cookies():
        if "maimaidx-eng.com" in cookie.get('domain', ''):
            session.cookies.set(cookie['name'], cookie['value'])

    print("📊 準備獲取資料...", flush=True)
    
    # 預先載入 CloudFront 歌曲資料庫 (加速定數查詢)
    fetch_songs_data()
    
    whitelist = get_new_songs_whitelist(session, driver)
    
    levels = {}
    if os.path.exists(LEVELS_FILE):
        with open(LEVELS_FILE, "r", encoding="utf-8") as f:
            try:
                levels = json.load(f)
            except: levels = {}

    all_results = []
    diff_map = {2: "Expert", 3: "Master", 4: "Re:Master"}

    for diff_id, diff_label in diff_map.items():
        print(f"🔍 正在處理 {diff_label}...", flush=True)
        url = f"https://maimaidx-eng.com/maimai-mobile/friend/friendGenreVs/battleStart/?scoreType=2&genre=99&diff={diff_id}&idx={friend_idx}"
        
        try:
            driver.get(url)
            wait = WebDriverWait(driver, 10)
            start_btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button.f_0")))
            driver.execute_script("arguments[0].click();", start_btn)
            
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "w_450")))
            soup = BeautifulSoup(driver.page_source, "html.parser")
            entries = soup.select("div.w_450")
            
            for entry in entries:
                try:
                    name_div = entry.select_one(".music_name_block")
                    if not name_div: continue
                    name = name_div.text.strip()
                    
                    kind_img = entry.select_one("img.music_kind_icon")
                    kind = "DX" if kind_img and "music_dx.png" in kind_img.get('src') else "STD"
                    
                    score_tds = entry.select("td.p_r.f_b")
                    if not score_tds: continue
                    ach_text = score_tds[-1].text.replace('%', '').strip()
                    if ach_text == "-" or not ach_text: continue
                    achievement = float(ach_text)

                    # 這裡會確保 levels 被即時補完並存檔
                    constant = get_constant_logic(levels, name, kind, diff_label, driver=driver)
                    
                    if constant:
                        r_value = calculate_r(achievement, constant)
                        category = "New" if (name, kind) in whitelist else "Old"
                        all_results.append({
                            "分類": category, "歌曲": name, "類型": kind, "難度": diff_label,
                            "定數": constant, "達成率": achievement, "R值": r_value
                        })
                except: continue
        except: continue

    df = pd.DataFrame(all_results)
    if df.empty: return None

    # --- 關鍵修正：多重排序 ---
    # 1. 先按 "R值" 降序排列 (從高到低)
    # 2. 當 R值相同時，按 "達成率" 降序排列 (從高到低)
    
    # 處理新歌 (New) 的 B15
    df_new = df[df["分類"] == "New"].sort_values(
        by=["R值", "達成率"],
        ascending=[False, False]
    ).head(15)
    
    # 處理舊歌 (Old) 的 B35
    df_old = df[df["分類"] == "Old"].sort_values(
        by=["R值", "達成率"],
        ascending=[False, False]
    ).head(35)
    
    # 合併結果
    final_df = pd.concat([df_new, df_old])

    image_path = generate_b50_image(final_df, friend_idx, driver)
    if image_path:
        try:
            prev, total = save_result(friend_idx, df, final_df, image_path, last_profile)
            print(f"RATING:{total}:{'' if prev is None else prev}", flush=True)
        except Exception as e:
            print(f"⚠️ B50 紀錄存檔失敗: {e}", flush=True)
    return image_path