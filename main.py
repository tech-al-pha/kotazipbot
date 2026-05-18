import json
import os
import zipfile
import tempfile
import threading
from dotenv import load_dotenv
import telebot
from loguru import logger
from groq import Groq
from flask import Flask

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it to the .env file.")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is missing. Add it to the .env file.")

groq_client = Groq(api_key=GROQ_API_KEY)
bot = telebot.TeleBot(TOKEN)

logger.add("bot.log", rotation="10 MB", retention="7 days", backtrace=True, diagnose=True)
logger.info("KotaZipBot started...")

# ─── Flask App (for cron job ping) ──────────────────────────
flask_app = Flask(__name__)

@flask_app.route("/ping")
def ping():
    return "Bot is alive!", 200

@flask_app.route("/")
def home():
    return "KotaZipBot is running!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)


# ─── Helper Functions ────────────────────────────────────────
def safe_send(chat_id, text, parse_mode="HTML"):
    try:
        bot.send_message(chat_id, text, parse_mode=parse_mode, disable_web_page_preview=True)
    except Exception:
        bot.send_message(chat_id, text, parse_mode=None, disable_web_page_preview=True)


def send_long(chat_id, text):
    chunk_size = 3500
    for start in range(0, len(text), chunk_size):
        chunk = text[start:start + chunk_size]
        try:
            bot.send_message(chat_id, chunk, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            bot.send_message(chat_id, chunk, parse_mode=None, disable_web_page_preview=True)


def extract_with_groq(content: str, file_name: str) -> str:
    """Send content to Groq AI and get structured course info back."""
    prompt = f"""You are an expert course content extractor. Below is the content of a file named: "{file_name}"

Your job is to analyze this content and clearly extract the following:

1. Course / Batch Name
2. Platform (AppX, AppsLixt, Adda247, CipherSchools, CodeHelp, PW, Unacademy, Khan Global, etc.)
3. Subjects / Topics List (list all of them)
4. Any Links (video links, PDF links, notes, drive links, etc.)
5. Teacher / Instructor Name (if available)
6. Duration or Schedule (if available)
7. Any other important information

Rules:
- Give clean and readable output
- Skip any point if the information is not available
- Do NOT show raw JSON or technical data
- Only show useful and relevant information

File Content:
{content[:6000]}"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return f"AI extraction failed: {str(e)}"


# ─── Bot Commands ────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🔥 <b>Welcome to KotaZipBot</b>\n\n"
        "Send me any file and I will extract all course info using AI!\n\n"
        "<b>Supported formats:</b>\n"
        "✅ .json — Course JSON files\n"
        "✅ .txt — Text files\n"
        "✅ .zip — ZIP archives\n\n"
        "<b>I will extract:</b>\n"
        "📚 Course name\n"
        "🏫 Platform (AppX, Adda, CP, PW...)\n"
        "📖 Subjects and Topics\n"
        "🔗 Links\n"
        "👨‍🏫 Teacher info\n\n"
        "Just send a file and I will do the rest! 🚀",
        parse_mode="HTML",
    )


@bot.message_handler(commands=["help"])
def help_cmd(message):
    bot.send_message(
        message.chat.id,
        "📌 <b>Help Menu</b>\n\n"
        "<b>Supported Formats:</b>\n"
        "✅ .json — Course JSON files\n"
        "✅ .txt — Text files\n"
        "✅ .zip — ZIP archives (with JSON/TXT inside)\n\n"
        "<b>Commands:</b>\n"
        "/start — Start the bot\n"
        "/help — Show this menu\n\n"
        "🤖 Powered by Groq AI (LLaMA 70B)\n"
        "Works with any platform — AppX, Adda, CP, PW and more!",
        parse_mode="HTML",
    )


# ─── Document Handler ─────────────────────────────────────────
@bot.message_handler(content_types=["document"])
def handle_document(message):
    try:
        file_name = message.document.file_name
        file_size = message.document.file_size
        logger.info(f"Received file: {file_name} ({file_size} bytes)")

        bot.reply_to(
            message,
            f"📥 <b>File received:</b> {file_name}\n"
            f"📦 Size: {file_size} bytes\n\n"
            f"🤖 Extracting with AI... please wait!",
            parse_mode="HTML",
        )

        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = os.path.join(tmpdir, file_name)
            with open(local_path, "wb") as f:
                f.write(downloaded_file)

            # ─── JSON ─────────────────────────────────────────
            if file_name.lower().endswith(".json"):
                with open(local_path, "r", encoding="utf-8", errors="replace") as f:
                    try:
                        data = json.load(f)
                        raw_text = json.dumps(data, indent=2, ensure_ascii=False)
                    except json.JSONDecodeError:
                        f.seek(0)
                        raw_text = f.read()

                result = extract_with_groq(raw_text, file_name)
                safe_send(message.chat.id, f"✅ <b>Extracted Info:</b>\n\n{result}")

            # ─── TXT ──────────────────────────────────────────
            elif file_name.lower().endswith(".txt"):
                with open(local_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                result = extract_with_groq(content, file_name)
                safe_send(message.chat.id, f"✅ <b>Extracted Info:</b>\n\n{result}")

            # ─── ZIP ──────────────────────────────────────────
            elif file_name.lower().endswith(".zip"):
                with zipfile.ZipFile(local_path, "r") as zip_ref:
                    members = zip_ref.namelist()

                    file_list = "\n".join(f"• {m}" for m in members[:20])
                    if len(members) > 20:
                        file_list += f"\n... and {len(members) - 20} more files"

                    bot.reply_to(
                        message,
                        f"🗜️ ZIP contains <b>{len(members)}</b> files:\n\n{file_list}",
                        parse_mode="HTML",
                    )

                    processed = 0
                    for member in members:
                        if member.endswith("/"):
                            continue
                        if member.lower().endswith((".json", ".txt")):
                            try:
                                with zip_ref.open(member) as f:
                                    raw = f.read()
                                try:
                                    text = raw.decode("utf-8")
                                except UnicodeDecodeError:
                                    text = raw.decode("latin-1", errors="replace")

                                if member.lower().endswith(".json"):
                                    try:
                                        data = json.loads(text)
                                        text = json.dumps(data, indent=2, ensure_ascii=False)
                                    except json.JSONDecodeError:
                                        pass

                                result = extract_with_groq(text, member)
                                safe_send(
                                    message.chat.id,
                                    f"📄 <b>{member}</b>\n\n{result}"
                                )
                                processed += 1

                            except Exception as inner_e:
                                logger.warning(f"Could not process {member}: {inner_e}")

                    if processed == 0:
                        bot.send_message(
                            message.chat.id,
                            "ZIP processed, but no JSON or TXT files found inside.",
                            parse_mode="HTML",
                        )

            # ─── Unsupported ───────────────────────────────────
            else:
                bot.reply_to(
                    message,
                    "⚠️ Only <b>.json, .txt, and .zip</b> files are supported right now.\n"
                    "Need another format? Let me know!",
                    parse_mode="HTML"
                )

        logger.success(f"Processed file: {file_name}")

    except Exception as e:
        logger.exception("Failed to process document")
        bot.reply_to(message, f"❌ <b>Error:</b> {str(e)}", parse_mode="HTML")


# ─── Text Message Handler ─────────────────────────────────────
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    bot.reply_to(
        message,
        "📁 Please send a file — JSON, TXT, or ZIP!\n"
        "Text messages are not supported.",
        parse_mode="HTML"
    )


# ─── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    # Start Flask in a separate thread for cron job pings
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    logger.info("Flask server started for cron ping!")

    # Start bot polling
    logger.info("Bot polling started...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
