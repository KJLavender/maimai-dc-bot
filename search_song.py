"""
歌曲定數查詢腳本：接收歌名關鍵字，回傳 JSON 格式結果。
被 index.js 的 /m 指令呼叫。
"""
import sys
import json
from song_data import fetch_songs_data, search_songs, get_song_levels

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "no_query"}))
        return

    query = " ".join(sys.argv[1:])
    fetch_songs_data()

    results = search_songs(query, limit=5)

    if not results:
        print(json.dumps({"error": "not_found", "query": query}))
        return

    output = []
    for song in results:
        title = song.get("title", "未知")
        artist = song.get("artist", "未知")
        levels_info = get_song_levels(song)
        output.append({
            "title": title,
            "artist": artist,
            "levels": levels_info
        })

    print(json.dumps({"results": output, "query": query}, ensure_ascii=False))


if __name__ == "__main__":
    main()
