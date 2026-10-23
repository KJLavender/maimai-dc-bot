"""
歌曲資料模組：從 CloudFront JSON 取得定數、封面與模糊匹配
資料來源: https://dp4p6x0xfi5o9.cloudfront.net/maimai/data.json
"""
import sys
import json
import os
import time
import requests
from difflib import SequenceMatcher

DATA_URL = "https://dp4p6x0xfi5o9.cloudfront.net/maimai/data.json"
CACHE_FILE = "songs_data_cache.json"
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


def search_songs(query, limit=25):
    """
    模糊搜尋歌曲，回傳最相關的結果。
    支援完全匹配、包含匹配、字元匹配與 SequenceMatcher。
    """
    if not _songs_data:
        fetch_songs_data()

    query_lower = query.lower()
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

        if score > 0:
            results.append((score, song))

    results.sort(key=lambda x: x[0], reverse=True)
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
