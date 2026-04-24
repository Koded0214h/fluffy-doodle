# 🧠 KODED OS — Personal Telegram Second Brain

Your personal AI chief of staff. Lives in Telegram. Powered by Gemini 2.5 Flash.

## Features

- 📸 **Snap your task list** — photo → AI reads it → schedules reminders
- 🎙️ **Voice notes** — transcribed + parsed into tasks automatically  
- 💬 **Natural text** — just talk to it, it figures out what you mean
- ⏰ **Proactive reminders** — pings you 10 min before each task
- 🌅 **Morning standup** — 7:30am daily check-in
- 🌙 **Evening wind-down** — 9pm daily recap
- 🎯 **Opportunity tracker** — hackathons, deadlines, internships with countdowns
- 📊 **Weekly summary** — AI-generated Sunday recap across all your tracks

## Setup

### 1. Clone & install

```bash
git clone <your-repo>
cd koded-os
pip install -r requirements.txt
```

### 2. Create your Telegram bot

1. Open Telegram → DM `@BotFather`
2. Send `/newbot`
3. Follow prompts, copy the token

### 3. Get your Telegram user ID

DM `@userinfobot` on Telegram — it'll tell you your ID

### 4. Get Gemini API key (FREE)

Go to https://aistudio.google.com/apikey and generate a free key

### 5. Configure

```bash
cp .env.example .env
# Edit .env with your tokens
```

### 6. Run

```bash
python bot.py
```

### 7. Deploy to Contabo VPS (production)

```bash
# On your VPS
git clone <your-repo>
cd koded-os
pip install -r requirements.txt
cp .env.example .env && nano .env

# Run with systemd or screen
screen -S koded-os
python bot.py
# Ctrl+A, D to detach
```

Or use a systemd service:

```ini
[Unit]
Description=KODED OS Telegram Bot
After=network.target

[Service]
WorkingDirectory=/root/koded-os
ExecStart=/usr/bin/python3 bot.py
Restart=always
EnvironmentFile=/root/koded-os/.env

[Install]
WantedBy=multi-user.target
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Boot up KODED OS |
| `/tasks` | View active tasks |
| `/opps` | View tracked opportunities |
| `/summary` | Generate weekly summary now |
| `/clear` | Clear today's task list |

## Usage

**Add tasks by photo:**
> Just snap your handwritten or typed list → send it

**Add tasks by voice:**
> "I need to push the FarmIntel fix by 3pm, prep Stackd session at 6, and review DSA problems tonight"

**Add tasks by text:**
> "fix farmIntel CORS bug by 3pm, Stackd session prep at 6"

**Track an opportunity:**
> "Microsoft internship deadline is May 30"
> "ETH Lagos hackathon, June 15"

**Mark done:**
> "done with the farmIntel bug"
> "finished prepping Stackd"

## Architecture

```
bot.py              — Entry point, handler registration
config.py           — Env vars, Koded's context for Gemini
database.py         — SQLite via aiosqlite (tasks, opportunities, logs)
gemini.py           — All Gemini 2.5 Flash calls (vision, audio, text, summaries)
scheduler.py        — APScheduler jobs (standup, reminders, wind-down, weekly)
handlers/
  commands.py       — /start /help /tasks /opps /clear /summary
  messages.py       — text, photo, voice message handlers
```
