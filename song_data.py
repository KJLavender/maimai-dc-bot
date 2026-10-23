"""
歌曲資料模組：從 CloudFront JSON 取得定數、封面與模糊匹配
資料來源: https://dp4p6x0xfi5o9.cloudfront.net/maimai/data.json
"""
import sys
import json
import os
import re
import time
import requests
from difflib import SequenceMatcher

DATA_URL = "https://dp4p6x0xfi5o9.cloudfront.net/maimai/data.json"
CACHE_FILE = "songs_data_cache.json"
ROMAJI_CACHE_FILE = "songs_romaji_cache.json"
CACHE_TTL_SECONDS = int(os.environ.get("SONGS_CACHE_TTL", 6 * 60 * 60))

# 全域歌曲資料
_songs_data = []


def _log(msg):
    """狀態訊息輸出到 stderr，避免汙染 stdout 的 JSON"""
    print(msg, file=sys.stderr, flush=True)


def fetch_songs_data(force_refresh=False):
    """
    從網路抓取歌曲資料，並快取至本地檔案。
    回傳歌曲列表。
    """
    global _songs_data

    # 如果已載入記憶體且不強制刷新
    if _songs_data and not force_refresh:
        return _songs_data

    # 嘗試從快取載入（未過期才使用）
    cache_fresh = (
        os.path.exists(CACHE_FILE)
        and time.time() - os.path.getmtime(CACHE_FILE) < CACHE_TTL_SECONDS
    )
    if not force_refresh and cache_fresh:
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _songs_data = json.load(f)
            if _songs_data:
                _log(f"📦 從快取載入 {len(_songs_data)} 首歌曲資料")
                return _songs_data
        except:
            pass

    # 從網路抓取
    try:
        _log("🌐 正在從 CloudFront 抓取歌曲資料庫...")
        resp = requests.get(DATA_URL, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            _songs_data = data.get("songs", data) if isinstance(data, dict) else data
            # 存入快取
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(_songs_data, f, ensure_ascii=False)
            _log(f"✅ 成功載入 {len(_songs_data)} 首歌曲資料")
        else:
            _log(f"⚠️ 抓取歌曲資料失敗 (HTTP {resp.status_code})")
    except Exception as e:
        _log(f"⚠️ 抓取歌曲資料庫失敗: {e}")

    # 抓取失敗時退回使用過期快取
    if not _songs_data and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _songs_data = json.load(f)
            _log(f"📦 使用過期快取 {len(_songs_data)} 首歌曲資料")
        except:
            pass

    return _songs_data


# 統一各種羅馬拼音寫法（黑本式/訓令式、長音），讓 shoukai / shokai / syoukai 都視為相同
_ROMAJI_RULES = [
    ("jy", "j"), ("shi", "si"), ("sh", "sy"), ("chi", "ti"), ("ch", "ty"),
    ("tsu", "tu"), ("fu", "hu"), ("ji", "zi"), ("j", "zy"),
    ("ou", "o"), ("oo", "o"), ("uu", "u"), ("aa", "a"), ("ii", "i"), ("ee", "e"),
]


def normalize_romaji(text):
    text = re.sub(r"[^a-z0-9]", "", text.lower())
    for old, new in _ROMAJI_RULES:
        text = text.replace(old, new)
    return text


def _romaji_index():
    """回傳 {歌名: 正規化羅馬拼音}，結果快取在檔案，只替新歌做轉換"""
    index = {}
    if os.path.exists(ROMAJI_CACHE_FILE):
        try:
            with open(ROMAJI_CACHE_FILE, "r", encoding="utf-8") as f:
                index = json.load(f)
        except (OSError, ValueError):
            index = {}

    missing = [s.get("title", "") for s in _songs_data if s.get("title", "") not in index]
    if not missing:
        return index

    try:
        import pykakasi
    except ImportError:
        _log("⚠️ 未安裝 pykakasi，無法用羅馬拼音搜尋")
        return index

    kks = pykakasi.kakasi()
    for title in missing:
        hepburn = "".join(item["hepburn"] for item in kks.convert(title))
        index[title] = normalize_romaji(hepburn)

    try:
        with open(ROMAJI_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
    except OSError:
        pass
    return index


def _romaji_score(query_romaji, title_romaji):
    if not query_romaji or not title_romaji:
        return 0
    if query_romaji == title_romaji:
        return 95
    if len(query_romaji) >= 3 and query_romaji in title_romaji:
        return 75 + (len(query_romaji) / len(title_romaji)) * 20
    ratio = SequenceMatcher(None, query_romaji, title_romaji).ratio()
    return ratio * 55 if ratio > 0.6 else 0


def search_songs(query, limit=25, romaji=False):
    """
    模糊搜尋歌曲，回傳最相關的結果。
    支援完全匹配、包含匹配、字元匹配與 SequenceMatcher。
    romaji=True 時也比對歌名的羅馬拼音。
    """
    if not _songs_data:
        fetch_songs_data()

    query_lower = query.lower()
    query_romaji = normalize_romaji(query) if romaji and re.search(r"[a-zA-Z]", query) else ""
    romaji_index = _romaji_index() if query_romaji else {}
    results = []

    for song in _songs_data:
        title = song.get("title", "")
        title_lower = title.lower()

        score = 0

        # 完全匹配
        if query_lower == title_lower:
            score = 100
        # 包含查詢字串
        elif query_lower in title_lower:
            score = 80 + (len(query) / max(len(title), 1)) * 20
        # 標題包含在查詢中
        elif title_lower in query_lower:
            score = 70 + (len(title) / max(len(query), 1)) * 20
        # 查詢字串的每個字都出現在標題中
        elif all(ch in title_lower for ch in query_lower if ch.strip()):
            score = 50 + (len(query) / max(len(title), 1)) * 20
        else:
            # 使用 SequenceMatcher 計算相似度
            ratio = SequenceMatcher(None, query_lower, title_lower).ratio()
            if ratio > 0.4:
                score = ratio * 60

        if query_romaji:
            score = max(score, _romaji_score(query_romaji, romaji_index.get(title, "")))

        if score > 0:
            results.append((score, song))

    results.sort(key=lambda x: x[0], reverse=True)
    # 有明確命中時，去掉只是字元湊巧相似的結果
    if romaji and results and results[0][0] >= 75:
        results = [r for r in results if r[0] > 70]
    return [song for _, song in results[:limit]]


def find_best_match(query, kind=None):
    """
    找出最匹配的單首歌曲。
    kind: "DX" 或 "STD"，可選，用於額外過濾。
    回傳歌曲 dict 或 None。
    """
    results = search_songs(query, limit=5)
    if not results:
        return None

    # 如果指定了 kind，優先選擇有對應譜面類型的
    if kind:
        target_type = "dx" if kind == "DX" else "standard"
        for song in results:
            sheets = song.get("sheets", [])
            for sheet in sheets:
                if sheet.get("type", "") == target_type:
                    return song

    return results[0]


def get_internal_level(song_name, kind, diff_label):
    """
    從資料庫取得歌曲定數。
    
    參數:
        song_name: 歌曲名稱
        kind: "DX" 或 "STD"
        diff_label: "Basic", "Advanced", "Expert", "Master", "Re:Master"
    
    回傳: float 定數值，或 None
    """
    if not _songs_data:
        fetch_songs_data()

    song = find_best_match(song_name, kind)
    if not song:
        return None

    # 轉換類型標籤
    target_type = "dx" if kind == "DX" else "standard"
    # 轉換難度標籤 (data.json 使用小寫)
    diff_map = {
        "Basic": "basic",
        "Advanced": "advanced",
        "Expert": "expert",
        "Master": "master",
        "Re:Master": "remaster",
    }
    target_diff = diff_map.get(diff_label, diff_label.lower().replace(":", ""))

    sheets = song.get("sheets", [])
    for sheet in sheets:
        if sheet.get("type") == target_type and sheet.get("difficulty") == target_diff:
            internal = sheet.get("internalLevel")
            if internal:
                try:
                    return float(internal)
                except (ValueError, TypeError):
                    pass
            # 嘗試用 level 欄位 (可能是整數等級如 "13+")
            level = sheet.get("level", "")
            if level and "+" in str(level):
                try:
                    base = float(str(level).replace("+", ""))
                    return base + 0.7  # 粗略估計
                except:
                    pass
    return None


def get_cover_url(song_name):
    """
    取得歌曲封面圖片的完整 URL。
    回傳 URL 字串或 None。
    """
    if not _songs_data:
        fetch_songs_data()

    song = find_best_match(song_name)
    if not song:
        return None

    image_name = song.get("imageName", "")
    if image_name:
        return f"https://dp4p6x0xfi5o9.cloudfront.net/maimai/img/cover/{image_name}"
    return None


def get_song_version(song_name):
    """
    取得歌曲所屬版本 (如 PRiSM PLUS, CiRCLE 等)。
    回傳版本字串或 None。
    """
    if not _songs_data:
        fetch_songs_data()

    song = find_best_match(song_name)
    if not song:
        return None

    return song.get("version", None)


def get_song_levels(song):
    """取得歌曲各難度的定數資訊列表"""
    sheets = song.get("sheets", [])
    info_lines = []

    for sheet in sheets:
        difficulty = sheet.get("difficulty", "")
        sheet_type = sheet.get("type", "")
        internal_level = sheet.get("internalLevel")
        level = sheet.get("level", "")

        if sheet_type == "utage":
            continue

        type_label = "DX" if sheet_type == "dx" else "STD"
        diff_display = difficulty.upper()

        if internal_level:
            info_lines.append(f"[{type_label}] {diff_display} — 等級: {level} | 定數: {internal_level}")
        else:
            info_lines.append(f"[{type_label}] {diff_display} — 等級: {level} | 定數: 未知")

    return info_lines


def sheet_const(sheet):
    try:
        return float(sheet.get("internalLevel"))
    except (TypeError, ValueError):
        return None


def sheet_brief(sheet):
    return {
        "type": sheet.get("type"),
        "difficulty": sheet.get("difficulty"),
        "level": sheet.get("level"),
        "const": sheet.get("internalLevel"),
        "designer": sheet.get("noteDesigner"),
    }


def song_info(song):
    """給 Discord 顯示用的歌曲資訊"""
    return {
        "title": song.get("title", "未知"),
        "artist": song.get("artist", "未知"),
        "bpm": song.get("bpm"),
        "version": song.get("version"),
        "image": song.get("imageName"),
        "sheets": [sheet_brief(s) for s in song.get("sheets", []) if s.get("type") != "utage"],
    }


def find_sheets_by_const(low, high):
    """找出國際版有開放、定數在 [low, high] 之間的譜面，回傳 (song, sheet) 列表"""
    if not _songs_data:
        fetch_songs_data()

    matches = []
    for song in _songs_data:
        for sheet in song.get("sheets", []):
            if sheet.get("type") == "utage" or sheet.get("regions", {}).get("intl") is False:
                continue
            const = sheet_const(sheet)
            if const is not None and low <= const <= high:
                matches.append((song, sheet))
    return matches
