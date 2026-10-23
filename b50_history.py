"""
B50 紀錄、推分建議與 rating 歷史。
  - save_result()：/b50 成功後由 fetch_rating_analysis 呼叫，存下成績與圖片
  - CLI（被 index.js 呼叫，輸出 JSON）：
      b50_history.py up <好友ID>     推分建議
      b50_history.py log <好友ID>    rating 歷史（含折線圖）
      b50_history.py last <好友ID>   上次的 B50 圖片與時間
"""
import os
import re
import sys
import json
import math
import shutil
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "b50_data")
HISTORY_LIMIT = 200
FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"

# (評級, 達成率門檻, 係數)
RANKS = [
    ("S", 97.0, 20.0),
    ("S+", 98.0, 20.3),
    ("SS", 99.0, 20.8),
    ("SS+", 99.5, 21.1),
    ("SSS", 100.0, 21.6),
    ("SSS+", 100.5, 22.4),
]


def _check_id(friend_id):
    # 好友 ID 會拿來組檔名，只允許數字以免路徑穿越
    if not re.fullmatch(r"\d{1,20}", str(friend_id)):
        raise ValueError("invalid friend id")
    return str(friend_id)


def _path(friend_id, suffix):
    return os.path.join(DATA_DIR, f"{_check_id(friend_id)}{suffix}")


def _json_default(obj):
    return obj.item() if hasattr(obj, "item") else str(obj)


def load_record(friend_id):
    path = _path(friend_id, ".json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_result(friend_id, all_df, b50_df, image_path, profile=None):
    """存下這次的成績與圖片，回傳 (上次 rating 或 None, 這次 rating)"""
    os.makedirs(DATA_DIR, exist_ok=True)
    record = load_record(friend_id) or {"history": []}
    prev = record["history"][-1]["rating"] if record["history"] else None

    official = str((profile or {}).get("rating", "")).strip()
    total = int(official) if official.isdigit() else int(b50_df["R值"].sum())
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    record["latest"] = {
        "time": now,
        "rating": total,
        "player": (profile or {}).get("name"),
        "charts": all_df.to_dict("records"),
    }
    record["history"] = (record["history"] + [{"time": now, "rating": total}])[-HISTORY_LIMIT:]

    tmp = _path(friend_id, ".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, default=_json_default)
    os.replace(tmp, _path(friend_id, ".json"))
    shutil.copyfile(image_path, _path(friend_id, ".png"))
    return prev, total


def chart_rating(constant, achievement, coeff):
    # 整數運算避免浮點誤差
    c10 = round(float(constant) * 10)
    ach = round(min(float(achievement), 100.5) * 10000)
    return math.floor(c10 * ach * round(coeff * 10) / 1e8)


def suggestions(charts, limit=10):
    """找出「差一點就到下個評級」且能讓總 rating 上升的譜面"""
    new = sorted((c for c in charts if c["分類"] == "New"), key=lambda c: -c["R值"])[:15]
    old = sorted((c for c in charts if c["分類"] == "Old"), key=lambda c: -c["R值"])[:35]
    in_b50 = {id(c) for c in new + old}
    floor = {
        "New": new[-1]["R值"] if len(new) == 15 else 0,
        "Old": old[-1]["R值"] if len(old) == 35 else 0,
    }

    picks = []
    for c in charts:
        best = None
        for name, threshold, coeff in [r for r in RANKS if r[1] > c["達成率"]][:2]:
            new_r = chart_rating(c["定數"], threshold, coeff)
            gain = new_r - (c["R值"] if id(c) in in_b50 else floor[c["分類"]])
            if gain <= 0:
                continue
            gap = threshold - c["達成率"]
            score = gain / max(gap, 0.05)
            if best is None or score > best["score"]:
                best = {
                    "title": c["歌曲"], "type": c["類型"], "difficulty": c["難度"],
                    "const": c["定數"], "achievement": c["達成率"], "target": threshold,
                    "rank": name, "gap": round(gap, 4), "gain": gain,
                    "in_b50": id(c) in in_b50, "score": score,
                }
        if best:
            picks.append(best)

    picks.sort(key=lambda p: (-p["score"], -p["gain"]))
    return picks[:limit]


def _font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default(size)


def draw_history(history, out_path):
    """畫 rating 折線圖，資料少於 2 筆時不畫"""
    points = history[-30:]
    if len(points) < 2:
        return None

    w, h = 900, 450
    left, right, top, bottom = 90, 40, 50, 70
    img = Image.new("RGB", (w, h), (30, 33, 40))
    draw = ImageDraw.Draw(img)
    f_small, f_big = _font(16), _font(22)

    values = [p["rating"] for p in points]
    lo, hi = min(values), max(values)
    pad = max(10, (hi - lo) * 0.15)
    lo, hi = lo - pad, hi + pad

    def xy(i, v):
        x = left + (w - left - right) * i / (len(points) - 1)
        y = top + (h - top - bottom) * (1 - (v - lo) / (hi - lo))
        return x, y

    for k in range(5):
        v = lo + (hi - lo) * k / 4
        _, y = xy(0, v)
        draw.line([(left, y), (w - right, y)], fill=(60, 64, 72), width=1)
        draw.text((10, y - 9), f"{int(v)}", fill=(170, 170, 170), font=f_small)

    coords = [xy(i, v) for i, v in enumerate(values)]
    draw.line(coords, fill=(255, 196, 0), width=3)
    for x, y in coords:
        draw.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(255, 196, 0))

    draw.text((left, h - bottom + 15), points[0]["time"][:10], fill=(170, 170, 170), font=f_small)
    last_date = points[-1]["time"][:10]
    draw.text((w - right - f_small.getlength(last_date), h - bottom + 15), last_date, fill=(170, 170, 170), font=f_small)
    draw.text((left, 12), f"Rating {values[0]} -> {values[-1]}", fill=(255, 255, 255), font=f_big)

    img.save(out_path)
    return out_path


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage"}))
        return
    mode, friend_id = sys.argv[1], sys.argv[2]
    try:
        record = load_record(friend_id)
    except ValueError:
        print(json.dumps({"error": "invalid_id"}))
        return
    if not record or "latest" not in record:
        print(json.dumps({"error": "no_record"}))
        return

    latest = record["latest"]
    if mode == "up":
        out = {"time": latest["time"], "rating": latest["rating"], "items": suggestions(latest["charts"])}
    elif mode == "log":
        graph = draw_history(record["history"], _path(friend_id, "_history.png"))
        out = {"history": record["history"][-10:], "count": len(record["history"]), "image": graph}
    elif mode == "last":
        image = _path(friend_id, ".png")
        out = {"time": latest["time"], "rating": latest["rating"], "image": image if os.path.exists(image) else None}
    else:
        out = {"error": "usage"}
    print(json.dumps(out, ensure_ascii=False, default=_json_default))


if __name__ == "__main__":
    main()
