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
| `/b50` | 產生 Best 50 圖片（需先 `/bind`，且機器人須為遊戲內好友） |
| `/addfriend friendcode:<代碼>` | 讓機器人送出好友申請給你 |
| `/m query:<關鍵字>` | 以歌名查詢定數（模糊搜尋；多首符合時以按鈕選擇） |
| `/c lv:<定數> [to:<定數>]` | 列出某個定數或範圍的譜面，例：`/c 13.1`、`/c 13.0 13.4` |
| `/r [lv:<定數>] [to:<定數>]` | 依定數隨機抽一個譜面，例：`/r 13.5`、`/r 13.5 14.0`（不填就全部隨機） |

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

> `.env` 由 `index.js` 載入並傳給 Python 腳本。若直接執行 Python 腳本（例如 cron），需自行 export 這些變數。

### 啟動

```bash
node index.js
```

## 資料檔

| 檔案 | 內容 |
|---|---|
| `cookies.json` | 機器人帳號的登入工作階段（敏感，**不會**提交） |
| `bindings.json` | Discord 使用者 ID → maimai 好友 ID |
| `songs_data_cache.json` | 歌曲資料快取，每 `SONGS_CACHE_TTL` 秒更新 |
| `covers/` | 歌曲封面快取 |

## 安全性

- 切勿提交 `.env` 或 `cookies.json`，兩者都能取得帳號存取權
