import pandas as pd
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
import os, re, time
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

# 設定難度顏色
DIFF_COLORS = {
    "Basic": (76, 175, 80),
    "Advanced": (255, 193, 7),
    "Expert": (244, 67, 54),
    "Master": (156, 39, 176),
    "Re:Master": (192, 192, 192)
}

# 最近一次從好友頁讀到的玩家名稱與官方 rating，給 B50 紀錄用
last_profile = {}

def create_gradient_mask(w, h):
    mask = Image.new('L', (w, h), 0)
    for y in range(h):
        alpha = int((y / h) ** 1.8 * 240)
        for x in range(w): mask.putpixel((x, y), alpha)
    return mask

def generate_b50_image(df, friend_idx, driver):
    if not os.path.exists("covers"): os.makedirs("covers")
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0"}

    # --- 核心優化：獲取封面並轉為 Image 物件 ---
    def get_song_cover_object(song_name, driver):
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', str(song_name))
        c_path = f"covers/{safe_name}.png"
        
        # 1. 優先從本地讀取 (速度最快)
        if os.path.exists(c_path):
            return Image.open(c_path).convert("RGBA")
        
        # 2. 本地沒圖，啟動 Selenium 抓取 URL
        target_url = f"https://arcade-songs.zetaraku.dev/maimai/?title={song_name}"
        try:
            print(f"📡 正在搜尋封面網址: {song_name}",flush=True)
            driver.get(target_url)
            time.sleep(3) # 等待 JS 渲染
            
            html_content = driver.page_source
            # 使用你測試成功的 Regex 模式
            pattern = r'https://dp4p6x0xfi5o9\.cloudfront\.net/maimai/img/cover-m/[a-z0-9]+\.png'
            match = re.search(pattern, html_content)
            
            if match:
                img_url = match.group(0)
                # 3. 下載圖片並轉為 PIL Object
                resp = session.get(img_url, timeout=5)
                if resp.status_code == 200:
                    img_obj = Image.open(BytesIO(resp.content)).convert("RGBA")
                    img_obj.save(c_path) # 儲存起來下次用
                    return img_obj
        except Exception as e:
            print(f"⚠️ 封面抓取失敗 ({song_name}): {e}",flush=True)
        
        # 4. 失敗則回傳深灰色塊
        return Image.new('RGBA', (220, 150), (50, 50, 50, 255))

    # 獲取頭像/Rating底圖用
    def get_img(url):
        try:
            if url.startswith('/'): url = "https://maimaidx-eng.com" + url
            resp = session.get(url, headers=headers, timeout=5)
            return Image.open(BytesIO(resp.content)).convert("RGBA")
        except: return Image.new('RGBA', (220, 150), (40, 40, 40, 255))

    # 分類資料
    new_songs = df[df["分類"]=="New"]
    old_songs = df[df["分類"]=="Old"]
    bg_h = 450 + ((len(new_songs)+4)//5 * 185) + ((len(old_songs)+4)//5 * 185) + 100
    
    img = Image.new('RGB', (1250, bg_h), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 字體設定
    f_path = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
    f_title, f_name = ImageFont.truetype(f_path, 40), ImageFont.truetype(f_path, 45)
    f_r_big, f_card_r = ImageFont.truetype("impact.ttf", 36), ImageFont.truetype("ariblk.ttf", 30)
    f_song, f_val, f_type = ImageFont.truetype(f_path, 18), ImageFont.truetype("ariblk.ttf", 22), ImageFont.truetype("ariblk.ttf", 15)

    # --- 抓取玩家資訊 ---
    # --- 頂部好友資訊 (修正段位與成績圖消失問題) ---
    driver.get(f"https://maimaidx-eng.com/maimai-mobile/friend/friendDetail/?idx={friend_idx}")
    soup = BeautifulSoup(driver.page_source, "html.parser")
    
    name = soup.find("div", class_="name_block").text.strip()
    rating = soup.find("div", class_="rating_block").text.strip()
    last_profile.update(name=name, rating=rating)
    icon_tag = soup.find("img", class_="w_112 f_l")
    
    base_x = 250   # 文字與條狀圖的起始 X 軸
    start_y = 50   # 整體起始 Y 軸
    
    # 1. 繪製頭像 (維持左側)
    if icon_tag:
        icon = get_img(icon_tag["src"]).resize((180, 180))
        img.paste(icon, (50, start_y+5), icon)
    
    # 2. 繪製名稱 (第一列)
    draw.text((base_x, start_y-5), name, fill=(0, 0, 0), font=f_name)
    
    r_base_tag = soup.find("img", src=lambda s: s and "rating_base" in s)
    # 3. 繪製 Rating 條 (第二列)
    if r_base_tag:
        r_base = get_img(r_base_tag["src"]).resize((280, 60))
        img.paste(r_base, (base_x, start_y + 65), r_base)
        
        # 繪製 Rating 數字 (精確對齊底圖)
        rx, ry, sp = base_x + 151, start_y + 74, 23.2
        for i, d in enumerate(rating):
            draw.text((rx + i * sp, ry), d, fill=(255, 255, 255), font=f_r_big)

    # 4. 繪製段位與階級小圖 (第三列：Rating 條下方)
    dan_tag = soup.find("img", src=lambda s: s and "course" in s)
    class_tag = soup.find("img", src=lambda s: s and "class" in s)
    
    badge_y = start_y + 135  # 設定在 Rating 條下方的 Y 座標
    current_badge_x = base_x
    
    if dan_tag:
        dan_icon = get_img(dan_tag["src"]).resize((110, 55))
        img.paste(dan_icon, (current_badge_x, badge_y), dan_icon)
        current_badge_x += 125 # 橫向間隔
        
    if class_tag:
        class_icon = get_img(class_tag["src"]).resize((110, 55))
        img.paste(class_icon, (current_badge_x, badge_y), class_icon)

    # --- 歌曲區塊繪製 ---
    def draw_section(data, start_y, title):
        draw.text((50, start_y), title, fill=(0, 0, 0), font=f_title)
        cy = start_y + 80
        grad_mask = create_gradient_mask(220, 150)
        black_layer = Image.new('RGBA', (220, 150), (0, 0, 0, 255))

        for i, row in data.reset_index().iterrows():
            x, y = 50 + (i%5) * 235, cy + (i//5) * 185
            diff = row['難度']
            color = DIFF_COLORS.get(diff, (100, 100, 100))
            
            cover_img = get_song_cover_object(row['歌曲'], driver)
            card = ImageOps.fit(cover_img, (220, 150), centering=(0.5, 0.5))

            card = Image.alpha_composite(card, Image.composite(black_layer, Image.new('RGBA', (220, 150), (0,0,0,0)), grad_mask))
            overlay = Image.new('RGBA', (220, 150), (0,0,0,0))
            ImageDraw.Draw(overlay).rectangle([140, 0, 220, 45], fill=color+(180,))
            card = Image.alpha_composite(card, overlay)
            
            cdraw = ImageDraw.Draw(card)
            rtxt = str(row['R值'])
            tw = cdraw.textbbox((0, 0), rtxt, font=f_card_r)[2] - cdraw.textbbox((0, 0), rtxt, font=f_card_r)[0]
            cdraw.text((180 - tw/2, 2), rtxt, fill=(255, 255, 255) if diff != "Re:Master" else (0,0,0), font=f_card_r)

            # --- 修正後的名稱與類型繪製邏輯 ---
            # 1. 繪製達成率資訊
            cdraw.text((10, 85), f"{row['定數']}  {row['達成率']}%", fill=(255, 255, 255), font=f_val)
            
            # 2. 處理類型 (DX/STD) 佈局
            stype = str(row['類型'])
            type_w = f_type.getlength(stype)
            type_x = 220 - type_w - 5  # 右側留 5px 間距
            cdraw.text((type_x, 122), stype, fill=(200, 200, 200), font=f_type)

            # 3. 精確計算並截斷歌曲名稱
            sname = str(row['歌曲'])
            max_name_w = type_x - 15  # 名稱與類型標籤之間留 10px 緩衝
            
            if f_song.getlength(sname) > max_name_w:
                while f_song.getlength(sname + "...") > max_name_w and len(sname) > 0:
                    sname = sname[:-1]
                sname += "..."
            
            cdraw.text((10, 115), sname, fill=(255, 255, 255), font=f_song)
            # ------------------------------------

            img.paste(card.convert("RGB"), (x, y))
            draw.rectangle([x, y, x+220, y+150], outline=color, width=4)

        return cy + ((len(data)+4)//5) * 185

    last_y = draw_section(new_songs, 300, "NEW")
    draw_section(old_songs, last_y + 60, "OTHERS")

    # --- 修改輸出邏輯 ---
    # 使用絕對路徑，確保 Node.js 刪除時不會找錯地方
    output_filename = f"b50_{friend_idx}_{int(time.time())}.png"
    abs_path = os.path.abspath(output_filename)
    
    img.save(abs_path)
    
    # 這裡必須 print 出來，讓 Node.js 的 stdout 抓到
    print(f"OUTPUT_FILE:{abs_path}", flush=True)
    
    return abs_path