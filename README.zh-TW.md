# maimai-dc-bot

[English](README.md) | **繁體中文**

**maimai DX（國際版）** 的 Discord 機器人：產生 Best 50 圖片、查詢歌曲定數、由機器人帳號送出好友申請。

- Discord 端：Node.js + [discord.js](https://discord.js.org)
- 資料端：Python 腳本（Selenium + 無頭 Chrome）登入 [maimai DX NET](https://maimaidx-eng.com)
- 歌曲資料與定數來自 [arcade-songs](https://arcade-songs.zetaraku.dev) 資料集

> 設計在 Linux 上執行（部署於 Oracle Cloud Ubuntu VM）。腳本以 `python3` 呼叫，部分路徑為絕對路徑（`/home/ubuntu/...`）。

## 指令

| 指令 | 說明 |
|---|---|
| `/bind friendid:<ID>` | 將 maimai 好友 ID 綁定到 Discord 帳號 |
| `/unbind` | 解除綁定 |
| `/myid` | 查看目前綁定的好友 ID |
| `/b50` | 產生 Best 50 圖片（需先 `/bind`，且機器人須為遊戲內好友）。會顯示跟上次相比的 rating 變化；官網連不上時先給上次的結果 |
| `/up` | 推分建議：依上次 `/b50` 的資料，列出差一點就到下個評級、最能拉高總 rating 的譜面 |
| `/log` | rating 紀錄（每次 `/b50` 記一筆）與進步曲線圖 |
| `/addfriend friendcode:<代碼>` | 讓機器人送出好友申請給你 |
| `/m query:<關鍵字>` | 以歌名查詢定數（模糊搜尋，日文歌名可打羅馬拼音，例：`senbonzakura`；多首符合時以按鈕選擇） |
| `/c lv:<定數> [to:<定數>]` | 列出某個定數或範圍的譜面，例：`/c 13.1`、`/c 13.0 13.4` |
| `/r [lv:<定數>] [to:<定數>]` | 依定數隨機抽一個譜面，例：`/r 13.5`、`/r 13.5 14.0`（不填就全部隨機） |
| `/rt query:<定數或歌名>` | 各評級的 rating（含 ALL PERFECT +1）：`/rt 13.3` 列出定數 13.3 的 AP/SSS+/SSS/… rating（`/rt 13` = 13.0）；`/rt 歌名` 列出該曲每個譜面的 rating |
| `/h` | 顯示所有指令與說明 |

## 專案結構

| 檔案 | 用途 |
|---|---|
| `index.js` | Discord 機器人：註冊斜線指令並呼叫 Python 腳本 |
| `catch-friend-score.py` | `/b50` 入口：登入（沿用 `cookies.json`）並抓取好友成績 |
| `fetch_rating_analysis.py` | 依成績與定數計算 Best 50 |
| `generate_b50_image.py` | 繪製 B50 圖片；缺少的封面會下載到 `covers/` |
| `add_friend.py` | `/addfriend`：送出好友申請 |
| `search_song.py` / `song_data.py` | `/m`、`/c`、`/r`：從 CloudFront 資料集搜尋歌曲與定數 |
| `get_levels.py` | 抓取定數寫入 `levels.json`（供 cron 定期執行） |
| `get_all_pic.py` | 預先下載所有歌曲封面到 `covers/` |
| `b50_history.py` | 把每次 `/b50` 的結果存到 `b50_data/`；提供 `/up`、`/log` 與官網斷線時的備援 |
| `otogo_worker.py` | [音GO 網站](https://maimai-japan-map.netlify.app)的好友代碼代抓成績（見下方） |

## 安裝

### 需求

- Node.js 18+
- Python 3.10+
- Google Chrome / Chromium（chromedriver 由 `webdriver-manager` 自動管理）
- 字型：
  - `wqy-microhei`（`sudo apt install fonts-wqy-microhei`）
  - `impact.ttf` 與 `ariblk.ttf` 放在專案根目錄（因授權因素未包含在 repo 中）

### 安裝步驟

```bash
git clone https://github.com/KJLavender/maimai-dc-bot.git
cd maimai-dc-bot
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 設定

```bash
cp .env.example .env
```

| 變數 | 說明 |
|---|---|
| `MAI_BOT_TOKEN` | Discord 機器人 Token |
| `CLIENT_ID` | Discord 應用程式 ID |
| `GUILD_ID` | 註冊斜線指令的伺服器 ID |
| `MAI_USER` / `MAI_PASS` | 機器人使用的 maimai DX NET 帳號 |
| `SONGS_CACHE_TTL` | 選填。歌曲資料快取秒數，預設 `21600`（6 小時） |
| `OTOGO_BOT_NAME` | 僅 `otogo_worker.py`。機器人帳號在遊戲裡的名字，會顯示給網站使用者 |
| `FIREBASE_KEY` | 僅 `otogo_worker.py`。選填，Firebase 服務帳戶金鑰路徑，預設 `./firebase-key.json` |

> `.env` 由 `index.js` 載入並傳給 Python 腳本。若直接執行 Python 腳本（例如 cron），需自行 export 這些變數。

### 啟動

```bash
node index.js
```

### 音GO 網站代抓程式（選用）

在[音GO 網站](https://maimai-japan-map.netlify.app)登入的使用者可以輸入好友代碼、接受機器人的好友申請，再按按鈕抓 B50。網站把工作放在 Firestore 的 `jobs/{uid}`；`otogo_worker.py` 監聽排隊中的工作，一次做一個：

- `friend`：跑 `add_friend.py`；成功就記下 `maiBind/{好友代碼} = {uid}`（哪個帳號送的申請）
- `b50`：`maiBind` 是同一個帳號才跑 `catch-friend-score.py`，把成績轉成網站格式寫進 `users/{uid}/mai/b50`

如果代碼已經是機器人的好友、但不是這個帳號送的申請，工作會被拒絕（本人可以先刪掉機器人好友再送一次），這樣沒有人能只靠別人的代碼偷看成績。

1. Firebase 控制台 → 專案設定 → 服務帳戶 → 產生新的私密金鑰，存成專案資料夾裡的 `firebase-key.json`（或設定 `FIREBASE_KEY`）。已列入 .gitignore，千萬不要提交
2. 在 `.env` 設定 `OTOGO_BOT_NAME` 為機器人帳號在遊戲裡的名字
3. `pip install -r requirements.txt`，然後 `python3 otogo_worker.py`

要讓它一直跑，用 systemd 服務（`/etc/systemd/system/otogo-worker.service`）：

```ini
[Unit]
Description=OtoGO B50 worker
After=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/mai-bot
ExecStart=/home/ubuntu/mai-bot/.venv/bin/python otogo_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now otogo-worker
journalctl -u otogo-worker -f   # 看紀錄
```

## 資料檔

| 檔案 | 內容 |
|---|---|
| `cookies.json` | 機器人帳號的登入工作階段（敏感，**不會**提交） |
| `bindings.json` | Discord 使用者 ID → maimai 好友 ID |
| `songs_data_cache.json` | 歌曲資料快取，每 `SONGS_CACHE_TTL` 秒更新 |
| `covers/` | 歌曲封面快取 |
| `b50_data/` | 每位玩家的 B50 紀錄：最新成績、rating 歷史與上次的 B50 圖 |

## 安全性

- 切勿提交 `.env` 或 `cookies.json`，兩者都能取得帳號存取權
- 切勿提交 `firebase-key.json`，它有音GO Firestore 的管理員權限
