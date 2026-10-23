# maimai-dc-bot

**English** | [繁體中文](README.zh-TW.md)

A Discord bot for **maimai DX (international)**: generate your Best 50 image, look up chart constants, and send friend requests from the bot's account.

- Discord side: Node.js + [discord.js](https://discord.js.org)
- Data side: Python scripts (Selenium + headless Chrome) that log in to [maimai DX NET](https://maimaidx-eng.com)
- Song data and chart constants from the [arcade-songs](https://arcade-songs.zetaraku.dev) dataset

> Designed to run on Linux (deployed on an Oracle Cloud Ubuntu VM). Scripts are invoked with `python3` and some paths are absolute (`/home/ubuntu/...`).

## Commands

| Command | Description |
|---|---|
| `/bind friendid:<ID>` | Bind your maimai Friend ID to your Discord account |
| `/unbind` | Remove your binding |
| `/myid` | Show your bound Friend ID |
| `/b50` | Generate your Best 50 image (requires `/bind`, and the bot must be your in-game friend) |
| `/addfriend friendcode:<code>` | The bot sends you a friend request |
| `/m query:<keyword>` | Look up chart constants by song title (fuzzy search; pick from buttons if several match) |
| `/c lv:<const> [to:<const>]` | List charts with a given constant or range, e.g. `/c 13.1`, `/c 13.0 13.4` |
| `/r [lv:<const>] [to:<const>]` | Pick a random chart by constant, e.g. `/r 13.5`, `/r 13.5 14.0` (no options = any chart) |
| `/calc query:<const or title>` | Rating per rank: `/calc 13.3` shows SSS+/SSS/... ratings for constant 13.3; `/calc <title>` shows them for every chart of that song |
| `/h` | Show all commands and how to use them |

## Project layout

| File | Purpose |
|---|---|
| `index.js` | Discord bot: registers slash commands and spawns the Python scripts |
| `catch-friend-score.py` | `/b50` entry: logs in (reusing `cookies.json`) and fetches the friend's scores |
| `fetch_rating_analysis.py` | Computes the Best 50 from scores and chart constants |
| `generate_b50_image.py` | Draws the B50 image; downloads missing covers into `covers/` |
| `add_friend.py` | `/addfriend`: sends a friend request |
| `search_song.py` / `song_data.py` | `/m`, `/c`, `/r`: song search and chart constants from the CloudFront dataset |
| `get_levels.py` | Scrapes chart constants into `levels.json` (meant for cron) |
| `get_all_pic.py` | Pre-downloads all song covers into `covers/` |

## Setup

### Prerequisites

- Node.js 18+
- Python 3.10+
- Google Chrome / Chromium (chromedriver is managed by `webdriver-manager`)
- Fonts:
  - `wqy-microhei` (`sudo apt install fonts-wqy-microhei`)
  - `impact.ttf` and `ariblk.ttf` placed in the project root (not included in this repo for licensing reasons)

### Install

```bash
git clone https://github.com/KJLavender/maimai-dc-bot.git
cd maimai-dc-bot
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `MAI_BOT_TOKEN` | Discord bot token |
| `CLIENT_ID` | Discord application ID |
| `GUILD_ID` | Server ID where slash commands are registered |
| `MAI_USER` / `MAI_PASS` | maimai DX NET account used by the bot |
| `SONGS_CACHE_TTL` | Optional. Song data cache lifetime in seconds, default `21600` (6 hours) |

> `.env` is loaded by `index.js` and passed to the Python scripts. When running Python scripts directly (e.g. from cron), export these variables yourself.

### Run

```bash
node index.js
```

## Data files

| File | Content |
|---|---|
| `cookies.json` | Login session of the bot account (sensitive, **not** committed) |
| `bindings.json` | Discord user ID → maimai Friend ID |
| `songs_data_cache.json` | Song database cache, refreshed every `SONGS_CACHE_TTL` seconds |
| `covers/` | Song cover cache |

## Security

- Never commit `.env` or `cookies.json`; both grant access to accounts
