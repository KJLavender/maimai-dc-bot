# maimai-dc-bot

**English** | [繁體中文](README.zh-TW.md)

A Discord bot for maimai DX (the international version of the Sega arcade rhythm game). Type `/b50` and it draws an image of your Best 50, the 50 scores that make up your rating. It can also look up how hard a chart is and send you a friend request in the game.

The game's official site (maimai DX NET) has no public API, so the bot logs in as its own account with a headless Chrome browser (Selenium) and reads the pages. For `/b50` the bot account has to be your friend in the game, because it reads your scores through the friend page. Song data and chart constants come from the [arcade-songs](https://arcade-songs.zetaraku.dev) dataset. A chart constant is the hidden decimal difficulty of a chart, such as 13.4.

The bot is written for Linux and runs on an Ubuntu VM. `get_levels.py` and `fetch_rating_analysis.py` contain absolute `/home/ubuntu/...` paths, and the scripts are started with `python3`.

## Commands

| Command | What it does |
|---|---|
| `/bind friendid:<ID>` | Links your maimai Friend ID to your Discord account |
| `/unbind` | Removes the link |
| `/myid` | Shows the Friend ID you linked |
| `/b50` | Draws your Best 50 image (needs `/bind`, and the bot must be your friend in the game). Shows the rating change since your last run. If the official site is down, it sends your last result instead |
| `/up` | Suggests which charts to improve. It uses your last `/b50` and lists charts that are close to the next rank and would raise your rating the most |
| `/log` | Your rating history (one entry per `/b50`) with a progress chart |
| `/addfriend friendcode:<code>` | The bot sends you a friend request |
| `/m query:<keyword>` | Looks up chart constants by song title. Fuzzy search; Japanese titles can be typed in romaji, e.g. `senbonzakura`. If several songs match, you pick one with buttons |
| `/c lv:<const> [to:<const>]` | Lists charts with a constant or in a range, e.g. `/c 13.1`, `/c 13.0 13.4` |
| `/r [lv:<const>] [to:<const>]` | Picks a random chart, e.g. `/r 13.5`, `/r 13.5 14.0`. With no options it picks from all charts |
| `/rt query:<const or title>` | Rating you get at each rank, including the +1 for ALL PERFECT. `/rt 13.3` shows the ratings for constant 13.3 (`/rt 13` means 13.0). `/rt <title>` shows them for every chart of that song |
| `/h` | Shows all commands |

`/b50` and `/addfriend` open the browser, so the bot handles one of them at a time. A second request gets a "please wait" message.

## How `/b50` works

1. `index.js` starts `catch-friend-score.py` with your Friend ID.
2. That script logs in to maimai DX NET (reusing `cookies.json`) and reads your scores from the friend page.
3. `fetch_rating_analysis.py` looks up the constant of each chart and picks the best 35 old-version scores and the best 15 new-version scores.
4. `generate_b50_image.py` draws the image. Covers that are missing are downloaded into `covers/`.
5. `b50_history.py` saves the result in `b50_data/`. `/up`, `/log` and the offline fallback read from there.

## Files

| File | Purpose |
|---|---|
| `index.js` | The Discord bot. Registers the slash commands and starts the Python scripts |
| `catch-friend-score.py` | Entry point for `/b50`: logs in and fetches the friend's scores |
| `fetch_rating_analysis.py` | Computes the Best 50 from scores and constants |
| `generate_b50_image.py` | Draws the B50 image |
| `add_friend.py` | `/addfriend`: sends the friend request |
| `search_song.py`, `song_data.py` | `/m`, `/c`, `/r`: song search and constants, from the `data.json` dataset behind arcade-songs |
| `get_levels.py` | Scrapes constants into `levels.json` (meant to run from cron) |
| `get_all_pic.py` | Downloads all song covers into `covers/` ahead of time |
| `b50_history.py` | Stores each `/b50` result; powers `/up`, `/log` and the fallback |
| `otogo_worker.py` | Fetches scores by friend code for the [OtoGO website](https://maimai-japan-map.netlify.app) (see below) |

## Setup

You need Node.js 18 or newer, Python 3.10 or newer, and Google Chrome or Chromium (`webdriver-manager` downloads the matching chromedriver). You also need these fonts:

- `wqy-microhei`: `sudo apt install fonts-wqy-microhei`
- `impact.ttf` and `ariblk.ttf` in the project folder. They are not in the repo because of their licenses, and the image cannot be drawn without them.

```bash
git clone https://github.com/KJLavender/maimai-dc-bot.git
cd maimai-dc-bot
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill it in
```

Settings in `.env`:

| Variable | Meaning |
|---|---|
| `MAI_BOT_TOKEN` | Discord bot token |
| `CLIENT_ID` | Discord application ID |
| `GUILD_ID` | ID of the server where the slash commands are registered |
| `MAI_USER`, `MAI_PASS` | The maimai DX NET account the bot logs in with |
| `SONGS_CACHE_TTL` | Optional. How long the song data is cached, in seconds. Default `21600` (6 hours) |
| `OTOGO_BOT_NAME` | Only for `otogo_worker.py`. The bot account's in-game name, shown to website users |
| `FIREBASE_KEY` | Only for `otogo_worker.py`. Optional path to the Firebase service account key. Default `./firebase-key.json` |

Start the bot:

```bash
node index.js
```

`index.js` loads `.env` and passes it to the Python scripts. If you run a Python script yourself (for example from cron), export these variables first.

The bot registers its commands in the one server given by `GUILD_ID` when it starts.

## OtoGO website worker (optional)

On the [OtoGO website](https://maimai-japan-map.netlify.app), a signed-in user can enter their friend code, accept the bot's friend request and press a button to fetch their B50. The site puts a job in Firestore under `jobs/{uid}`. `otogo_worker.py` watches for queued jobs and handles them one at a time:

- `friend`: runs `add_friend.py`. On success it records `maiBind/{friendCode} = {uid}`, which says which website account sent the request.
- `b50`: only if `maiBind` points to the same account, it runs `catch-friend-score.py` and writes the scores to `users/{uid}/mai/b50`.

If a friend code is already the bot's friend but was requested by a different account, the job is rejected. The owner can remove the bot as a friend and request again. This stops people from reading someone else's scores with only their code.

To set it up:

1. In the Firebase console, go to Project settings, then Service accounts, then Generate new private key. Save the file as `firebase-key.json` in the project folder, or point `FIREBASE_KEY` at it. It is in `.gitignore`. Do not commit it.
2. Set `OTOGO_BOT_NAME` in `.env`.
3. Run `python3 otogo_worker.py`.

To keep it running, use a systemd service such as `/etc/systemd/system/otogo-worker.service`:

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
journalctl -u otogo-worker -f   # logs
```

## Data files

| File | Content |
|---|---|
| `cookies.json` | Login session of the bot account. Sensitive, not committed |
| `bindings.json` | Discord user ID to maimai Friend ID |
| `songs_data_cache.json` | Cached song data, refreshed after `SONGS_CACHE_TTL` seconds |
| `covers/` | Song cover images |
| `b50_data/` | Per-player records: latest scores, rating history and the last B50 image |

## Security

- Never commit `.env` or `cookies.json`. Both give access to accounts.
- Never commit `firebase-key.json`. It has admin access to the OtoGO Firestore.
