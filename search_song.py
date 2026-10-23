"""
歌曲查詢腳本：接收參數，回傳 JSON 格式結果。被 index.js 的 /m、/c、/r 指令呼叫。
  search_song.py <關鍵字>             歌名搜尋
  search_song.py --const <低> [高]    依定數列出譜面
  search_song.py --random <低> [高]   依定數隨機抽一個譜面
"""
import sys
import json
import random
from song_data import fetch_songs_data, search_songs, song_info, sheet_brief, sheet_const, find_sheets_by_const

CONST_LIST_LIMIT = 100


def dump(obj):
    print(json.dumps(obj, ensure_ascii=False))


def by_const(mode, args):
    low = float(args[0])
    high = float(args[1]) if len(args) > 1 else low
    if low > high:
        low, high = high, low

    matches = find_sheets_by_const(low, high)
    if not matches:
        dump({"error": "not_found"})
        return

    if mode == "--random":
        song, sheet = random.choice(matches)
        dump({"song": song_info(song), "pick": sheet_brief(sheet)})
        return

    matches.sort(key=lambda m: (-sheet_const(m[1]), m[0].get("title", "")))
    items = [{"title": song.get("title", "未知"), **sheet_brief(sheet)} for song, sheet in matches[:CONST_LIST_LIMIT]]
    dump({"total": len(matches), "items": items})


def main():
    args = sys.argv[1:]
    if not args:
        dump({"error": "no_query"})
        return

    fetch_songs_data()

    if args[0] in ("--const", "--random"):
        by_const(args[0], args[1:])
        return

    query = " ".join(args)
    results = search_songs(query, limit=5, romaji=True)
    if not results:
        dump({"error": "not_found", "query": query})
        return

    dump({"results": [song_info(song) for song in results], "query": query})


if __name__ == "__main__":
    main()
