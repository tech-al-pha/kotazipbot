# KotaZipBot

A simple Telegram bot that extracts JSON, TXT, and ZIP files and returns the contents to the user.

## Setup

1. Create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Create a `.env` file with your bot token:

```env
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
```

4. Run the bot:

```powershell
python main.py
```

## Supported file types

- `.json`
- `.txt`
- `.zip`

The bot will extract file contents and send readable output back to Telegram.
