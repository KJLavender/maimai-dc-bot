# maimai-dc-bot

[English](README.md) | **繁體中文**

給 maimai DX（Sega 街機音樂遊戲的國際版）用的 Discord 機器人。輸入 `/b50`，它會畫出你的 Best 50 圖片，也就是組成你 rating 的 50 筆成績。它也能查譜面難度，並在遊戲裡送好友申請給你。

maimai DX NET 這個官方網站沒有公開的 API，所以機器人用自己的帳號，以無頭 Chrome 瀏覽器（Selenium）登入並讀網頁。`/b50` 需要機器人帳號是你的遊戲好友，因為成績是從好友頁面讀的。歌曲資料和定數來自 [arcade-songs](https://arcade-songs.zetaraku.dev) 資料集。定數是譜面藏起來的小數點難度，例如 13.4。

機器人是為 Linux 寫的，跑在一台 Ubuntu VM 上。`get_levels.py` 和 `fetch_rating_analysis.py` 裡有寫死的 `/home/ubuntu/...` 路徑，腳本也是用 `python3` 啟動。

## 指令

| 指令 | 功能 |
|---|---|
| `/bind friendid:<ID>` | 把你的 maimai 好友 ID 綁到 Discord 帳號 |
| `/unbind` | 解除綁定 |
| `/myid` | 查看你綁定的好友 ID |
| `/b50` | 畫出你的 Best 50 圖片（要先 `/bind`，且機器人要是你的遊戲好友）。會顯示和上次相比的 rating 變化。官網連不上時，改傳上次的結果 |
| `/up` | 推分建議。依你上次 `/b50` 的資料，列出差一點就到下個評級、最能拉高 rating 的譜面 |
| `/log` | rating 紀錄（每次 `/b50` 記一筆）和進步曲線圖 |
| `/addfriend friendcode:<代碼>` | 機器人送好友申請給你 |
| `/m query:<關鍵字>` | 用歌名查定數。支援模糊搜尋，日文歌名可以打羅馬拼音，例如 `senbonzakura`。有好幾首符合時，用按鈕選 |
| `/c lv:<定數> [to:<定數>]` | 列出某個定數或某個範圍的譜面，例如 `/c 13.1`、`/c 13.0 13.4` |
| `/r [lv:<定數>] [to:<定數>]` | 隨機抽一個譜面，例如 `/r 13.5`、`/r 13.5 14.0`。不填條件就從全部譜面抽 |
| `/rt query:<定數或歌名>` | 各評級能拿到的 rating，含 ALL PERFECT 的 +1。`/rt 13.3` 列出定數 13.3 的 rating（`/rt 13` 等於 13.0）。`/rt 歌名` 列出該曲每個譜面的 rating |
| `/h` | 顯示所有指令 |

`/b50` 和 `/addfriend` 會開瀏覽器，所以機器人一次只處理其中一個。第二個請求會收到「請稍候」的訊息。

## `/b50` 怎麼運作

1. `index.js` 帶著你的好友 ID 啟動 `catch-friend-score.py`。
2. 這支腳本登入 maimai DX NET（沿用 `cookies.json`），從好友頁面讀你的成績。
3. `fetch_rating_analysis.py` 查每個譜面的定數，挑出舊版本的最佳 35 筆和新版本的最佳 15 筆。
4. `generate_b50_image.py` 畫圖。缺的封面會下載到 `covers/`。
5. `b50_history.py` 把結果存進 `b50_data/`。`/up`、`/log` 和離線備援都是從這裡讀。

## 檔案

| 檔案 | 用途 |
|---|---|
| `index.js` | Discord 機器人。註冊斜線指令，並啟動 Python 腳本 |
| `catch-friend-score.py` | `/b50` 的入口：登入並抓好友的成績 |
| `fetch_rating_analysis.py` | 依成績和定數算出 Best 50 |
| `generate_b50_image.py` | 畫 B50 圖片 |
| `add_friend.py` | `/addfriend`：送好友申請 |
| `search_song.py`、`song_data.py` | `/m`、`/c`、`/r`：搜尋歌曲和定數，資料來自 arcade-songs 背後的 `data.json` |
| `get_levels.py` | 抓定數寫進 `levels.json`（設計成用 cron 定期跑） |
| `get_all_pic.py` | 事先把所有歌曲封面下載到 `covers/` |
| `b50_history.py` | 儲存每次 `/b50` 的結果，供 `/up`、`/log` 和備援使用 |
| `otogo_worker.py` | 替[音GO 網站](https://maimai-japan-map.netlify.app)用好友代碼抓成績（見下方） |

## 安裝

需要 Node.js 18 以上、Python 3.10 以上，以及 Google Chrome 或 Chromium（`webdriver-manager` 會下載對應的 chromedriver）。還需要這些字型：

- `wqy-microhei`：`sudo apt install fonts-wqy-microhei`
- `impact.ttf` 和 `ariblk.ttf` 放在專案資料夾。因為授權關係沒有放進 repo，少了它們就畫不出圖。

```bash
git clone https://github.com/KJLavender/maimai-dc-bot.git
cd maimai-dc-bot
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # 然後填入設定
```

`.env` 的設定：

| 變數 | 意思 |
|---|---|
| `MAI_BOT_TOKEN` | Discord 機器人 Token |
| `CLIENT_ID` | Discord 應用程式 ID |
| `GUILD_ID` | 要註冊斜線指令的伺服器 ID |
| `MAI_USER`、`MAI_PASS` | 機器人用來登入的 maimai DX NET 帳號 |
| `SONGS_CACHE_TTL` | 選填。歌曲資料的快取秒數，預設 `21600`（6 小時） |
| `OTOGO_BOT_NAME` | 只有 `otogo_worker.py` 用。機器人帳號在遊戲裡的名字，會顯示給網站使用者 |
| `FIREBASE_KEY` | 只有 `otogo_worker.py` 用。選填，Firebase 服務帳戶金鑰的路徑，預設 `./firebase-key.json` |

啟動機器人：

```bash
node index.js
```

`index.js` 會讀 `.env` 並傳給 Python 腳本。如果你自己跑 Python 腳本（例如用 cron），要先自己 export 這些變數。

機器人啟動時，只會把指令註冊到 `GUILD_ID` 指定的那一個伺服器。

## 音GO 網站代抓程式（選用）

在[音GO 網站](https://maimai-japan-map.netlify.app)登入的使用者，可以輸入好友代碼、接受機器人的好友申請，再按按鈕抓自己的 B50。網站會把工作放在 Firestore 的 `jobs/{uid}`。`otogo_worker.py` 監看排隊中的工作，一次處理一個：

- `friend`：執行 `add_friend.py`。成功就記下 `maiBind/{好友代碼} = {uid}`，表示是哪個網站帳號送的申請。
- `b50`：`maiBind` 指向同一個帳號才會執行 `catch-friend-score.py`，並把成績寫到 `users/{uid}/mai/b50`。

如果某個好友代碼已經是機器人的好友，但申請是別的帳號送的，工作會被拒絕。本人可以先把機器人從好友刪掉再重新申請。這樣可以避免有人只拿別人的代碼就看到對方的成績。

設定步驟：

1. 到 Firebase 控制台，進入 專案設定 > 服務帳戶 > 產生新的私密金鑰。把檔案存成專案資料夾裡的 `firebase-key.json`，或用 `FIREBASE_KEY` 指向它。這個檔案已列入 `.gitignore`，不要提交。
2. 在 `.env` 設定 `OTOGO_BOT_NAME`。
3. 執行 `python3 otogo_worker.py`。

要讓它一直跑，可以用 systemd 服務，例如 `/etc/systemd/system/otogo-worker.service`：

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
| `cookies.json` | 機器人帳號的登入狀態。屬於敏感資料，不提交 |
| `bindings.json` | Discord 使用者 ID 對應 maimai 好友 ID |
| `songs_data_cache.json` | 歌曲資料快取，超過 `SONGS_CACHE_TTL` 秒後重新抓 |
| `covers/` | 歌曲封面圖 |
| `b50_data/` | 每位玩家的紀錄：最新成績、rating 歷史和上次的 B50 圖 |

## 安全注意事項

- 不要提交 `.env` 或 `cookies.json`，兩者都能用來存取帳號。
- 不要提交 `firebase-key.json`，它有音GO Firestore 的管理員權限。
