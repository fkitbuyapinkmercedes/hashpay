# HashPay MVP

Monorepo for the HashPay Telegram bot and Telegram Mini App.

## Structure

```text
hashpay/
  bot/   # aiogram bot for Railway/local launch
  web/   # Telegram Mini App / landing for Vercel
```

## Deploy

### 1. Vercel for the Mini App

- Import the repository into Vercel.
- Set `Root Directory` to `web`.
- Deploy the project and copy the production URL, for example `https://hashpay-web.vercel.app`.

### 2. Railway for the bot

- Create a Railway service from the same repository.
- Set `Root Directory` to `bot`.
- Railway will use `bot/Dockerfile`, so no extra start command is required.
- In Railway Variables add:

```text
BOT_TOKEN=...
WEBAPP_URL=https://hashpay-web.vercel.app
ADMIN_CHAT_ID=123456789
```

## Local launch

### Bot

```powershell
cd bot
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python bot.py
```

- Send `/myid` to the bot from your personal Telegram account.
- Copy the returned value into `ADMIN_CHAT_ID`.
- Admin commands for manual processing:

```text
/orders
/take HP-XXXX
/done HP-XXXX
/cancel HP-XXXX
```

### Web

- Open `web/index.html` locally for a quick UI check.
- For Telegram Mini App testing use the Vercel URL inside the bot.

## Future backend connection

`web/index.html` already contains an optional hook for a standalone API:

- set `window.HASHPAY_CONFIG = { apiBaseUrl: "https://your-api-domain.com" }`
- the Mini App will `POST` applications to `/api/applications`
- it also forwards `Telegram.WebApp.initData` in the `X-Telegram-Init-Data` header for backend verification

This means you can later add a proper API on Railway, FastAPI, Django, or Vercel Functions without rewriting the Mini App UI.

## Manual-order MVP

- The Mini App creates a manual application with a unique ID.
- The bot stores the request locally in SQLite and sends it to the admin chat.
- The operator updates statuses manually via bot commands.

Note: SQLite is enough for a demo or school MVP. For durable production storage on Railway you should later move orders to Postgres or another external database.
