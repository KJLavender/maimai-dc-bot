"""
音GO 網站（https://maimai-japan-map.netlify.app）的「好友代碼自動抓成績」工作程式。

網站把工作放在 Firestore 的 jobs/{uid}：
  {type: "friend" | "b50", code: 好友代碼, status: "queued", at}
這支程式監聽排隊中的工作，一次做一個：
  friend：跑 add_friend.py 送好友申請，成功就記下 maiBind/{好友代碼} = {uid}（誰送的申請）
  b50   ：確認 maiBind 是同一個帳號後，跑 catch-friend-score.py 抓成績，轉成網站格式寫進 users/{uid}/mai/b50
做完把 status 改成 sent / done / error，msg 是給使用者看的說明。

需要：
  pip install firebase-admin python-dotenv
  Firebase 服務帳戶金鑰（Firebase 控制台 → 專案設定 → 服務帳戶 → 產生新的私密金鑰），
  放在這個資料夾的 firebase-key.json，或用環境變數 FIREBASE_KEY 指定路徑
  .env 裡的 MAI_USER / MAI_PASS（和 Discord bot 共用）；OTOGO_BOT_NAME = 機器人帳號在遊戲裡的名字
用法：python3 otogo_worker.py
"""
import os
import re
import sys
import json
import time
import queue
import subprocess
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from dotenv import load_dotenv

from b50_history import load_record

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

BOT_NAME = os.getenv("OTOGO_BOT_NAME", "音GO")
KEY_FILE = os.getenv("FIREBASE_KEY", os.path.join(HERE, "firebase-key.json"))
SCRIPT_TIMEOUT = 600
DIFFS = {"Expert": 2, "Master": 3, "Re:Master": 4}
SITE_DOWN = re.compile(r"ERR_CONNECTION_REFUSED|ERR_CONNECTION_TIMED_OUT|ERR_CONNECTION_RESET|"
                       r"ERR_NAME_NOT_RESOLVED|ERR_TIMED_OUT|ERR_INTERNET_DISCONNECTED")
MSG_SITE_DOWN = "maimai 官網目前連不上（可能正在維護），請稍後再試。"


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def run(script, code):
    """跑 mai-bot 的 Python 腳本，回傳 stdout+stderr"""
    try:
        p = subprocess.run([sys.executable, script, code], cwd=HERE, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=SCRIPT_TIMEOUT,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return "TIMEOUT"


def to_payload(record, old):
    """b50_data/{好友代碼}.json → 網站的成績格式（templates/b50.js）"""
    latest = record["latest"]
    at = int(time.time() * 1000)
    scores, new = [], set()
    for c in latest["charts"]:
        if c.get("難度") not in DIFFS:
            continue
        kind = "dx" if c["類型"] == "DX" else "std"
        scores.append([c["歌曲"], kind, DIFFS[c["難度"]], float(c["達成率"]), "", ""])
        if c.get("分類") == "New":
            new.add(f"{c['歌曲']}|{kind}")
    rating = int(latest.get("rating") or 0)
    hist = [h for h in (old or {}).get("hist", []) if isinstance(h, list)]
    if rating:
        hist.append([at, rating])
    return {
        "v": 1, "at": at, "name": latest.get("player") or "玩家", "rating": rating,
        "scores": scores, "new": sorted(new), "src": "friend", "hist": hist[-200:],
    }


class Worker:
    def __init__(self):
        firebase_admin.initialize_app(credentials.Certificate(KEY_FILE))
        self.db = firestore.client()
        self.q = queue.Queue()
        self.watch = None

    def listen(self):
        def on_snapshot(_docs, changes, _read_time):
            for ch in changes:
                if ch.type.name in ("ADDED", "MODIFIED"):
                    self.q.put(ch.document.id)

        query = self.db.collection("jobs").where(filter=FieldFilter("status", "==", "queued"))
        self.watch = query.on_snapshot(on_snapshot)
        log("開始監聽 jobs")

    def bound_uid(self, code):
        snap = self.db.collection("maiBind").document(code).get()
        return snap.get("uid") if snap.exists else None

    def finish(self, ref, status, msg):
        ref.update({"status": status, "msg": msg, "done": firestore.SERVER_TIMESTAMP})
        log(f"  → {status}：{msg}")

    def do_friend(self, ref, uid, code):
        out = run("add_friend.py", code)
        if "SUCCESS_REQUEST_SENT" in out:
            self.db.collection("maiBind").document(code).set({"uid": uid, "at": firestore.SERVER_TIMESTAMP})
            return self.finish(ref, "sent", f"已送出好友申請！請到 maimai DX NET「好友」→「好友申請」"
                                            f"接受「{BOT_NAME}」，再按下面的按鈕。")
        if "ERROR_WRONG_CODE" in out:
            return self.finish(ref, "error", "找不到這個好友代碼，請確認 13 位數字有沒有打錯。")
        if "ERROR_ALREADY_FRIEND_OR_FULL" in out:
            # 已經是好友時無法確認是不是本人：只有當初送申請的帳號可以直接用
            if self.bound_uid(code) == uid:
                return self.finish(ref, "done", "已經是好友了，可以直接更新 B50。")
            return self.finish(ref, "error", f"這個代碼已經是「{BOT_NAME}」的好友（或好友已滿）。如果是你本人，"
                                             f"請先在 maimai DX NET 刪除好友「{BOT_NAME}」再送一次。")
        if SITE_DOWN.search(out):
            return self.finish(ref, "error", MSG_SITE_DOWN)
        log(out[-800:])
        self.finish(ref, "error", "送出好友申請失敗，請稍後再試。")

    def do_b50(self, ref, uid, code):
        if self.bound_uid(code) != uid:
            return self.finish(ref, "error", "請先送出好友申請（這個好友代碼不是由你的帳號送出申請的）。")
        out = run("catch-friend-score.py", code)
        record = load_record(code) if "OUTPUT_FILE:" in out else None
        if not record or "latest" not in record:
            if SITE_DOWN.search(out):
                return self.finish(ref, "error", MSG_SITE_DOWN)
            log(out[-800:])
            return self.finish(ref, "error", f"抓不到成績：請確認已在 maimai DX NET 接受「{BOT_NAME}」的好友申請，"
                                             f"過幾分鐘再試。")
        mai_ref = self.db.collection("users").document(uid).collection("mai").document("b50")
        old_snap = mai_ref.get()
        try:
            old = json.loads(old_snap.get("data")) if old_snap.exists else None
        except (ValueError, KeyError):
            old = None
        data = to_payload(record, old)
        mai_ref.set({"at": data["at"], "data": json.dumps(data, ensure_ascii=False)})
        self.finish(ref, "done", f"已更新：Rating {data['rating']}（{len(data['scores'])} 個譜面）")

    def handle(self, uid):
        ref = self.db.collection("jobs").document(uid)
        snap = ref.get()
        if not snap.exists or snap.get("status") != "queued":
            return
        job = snap.to_dict()
        code, kind = str(job.get("code", "")), job.get("type")
        if not re.fullmatch(r"\d{13}", code) or kind not in ("friend", "b50"):
            return self.finish(ref, "error", "工作內容不正確。")
        try:
            # 只在文件沒被改過時才接手，避免同一個工作做兩次
            ref.update({"status": "running"}, option=self.db.write_option(last_update_time=snap.update_time))
        except Exception:
            return
        log(f"{kind} {code[:4]}…（{uid[:6]}）")
        try:
            (self.do_friend if kind == "friend" else self.do_b50)(ref, uid, code)
        except Exception as e:
            log(f"  例外：{e!r}")
            self.finish(ref, "error", "處理時發生錯誤，請稍後再試。")

    def loop(self):
        self.listen()
        while True:
            try:
                uid = self.q.get(timeout=60)
            except queue.Empty:
                # 監聽斷掉（網路問題等）就重新開
                if self.watch is None or getattr(self.watch, "_closed", False):
                    log("監聽中斷，重新連線")
                    self.listen()
                continue
            self.handle(uid)


if __name__ == "__main__":
    Worker().loop()
