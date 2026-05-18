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
logger.info("🚀 KotaZipBot started...")

# ─── Flask App (Cron Job Ping ke liye) ──────────────────────
flask_app = Flask(__name__)

@flask_app.route("/ping")
def ping():
    return "🟢 Bot alive!", 200

@flask_app.route("/")
def home():
    return "🤖 KotaZipBot is running!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)


# ─── Helper Functions ────────────────────────────────────────
def _safe_send_message(chat_id, text, parse_mode="HTML"):
    try:
        bot.send_message(chat_id, text, parse_mode=parse_mode, disable_web_page_preview=True)
    except Exception:
        bot.send_message(chat_id, text, parse_mode=None, disable_web_page_preview=True)


def _send_long_message(chat_id, text, parse_mode="HTML"):
    chunk_size = 3500
    for start in range(0, len(text), chunk_size):
        chunk = text[start:start + chunk_size]
        try:
            bot.send_message(chat_id, chunk, parse_mode=parse_mode, disable_web_page_preview=True)
        except Exception:
            bot.send_message(chat_id, chunk, parse_mode=None, disable_web_page_preview=True)


def extract_with_groq(content: str, file_name: str) -> str:
    """Groq AI se content extract karao nicely formatted"""
    prompt = f"""Tu ek expert course extractor hai. Neeche ek file ka content diya gaya hai jiska naam hai: "{file_name}"

Tera kaam hai is content ko analyze karna aur clearly extract karna:

1. 📚 Course/Batch ka naam
2. 🏫 Platform detect karo (AppX, AppsLixt, Adda247, CipherSchools, CP, PW, Unacademy, etc.)
3. 📖 Subjects / Topics list (sab likho)
4. 🔗 Koi bhi links (video, PDF, notes, drive, etc.)
5. 👨‍🏫 Teacher/Instructor ka naam (agar ho)
6. 📅 Duration ya Schedule (agar ho)
7. 📝 Koi bhi important extra info

Rules:
- Clean aur readable format mein do
- Agar koi cheez nahi milti to us point ko skip karo
- Raw JSON ya technical data mat dikhao
- Sirf useful information extract karo
- Hinglish mein answer de sakta hai

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
        return f"⚠️ AI extraction failed: {str(e)}"


# ─── Bot Commands ────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🔥 <b>Welcome to KotaZipBot</b>\n\n"
        "Mujhe koi bhi file bhejo aur main AI se extract karke saari info dunga!\n\n"
        "<b>Supported formats:</b>\n"
        "✅ .json — Course JSON files\n"
        "✅ .txt — Text files\n"
        "✅ .zip — ZIP archives\n\n"
        "<b>Main extract karunga:</b>\n"
        "📚 Course name\n"
        "🏫 Platform (AppX, Adda, CP, PW...)\n"
        "📖 Subjects & Topics\n"
        "🔗 Links\n"
        "👨‍🏫 Teacher info\n\n"
        "Bas file bhejo! 🚀",
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
        "✅ .zip — ZIP archives (JSON/TXT andar)\n\n"
        "<b>Commands:</b>\n"
        "/start — Bot shuru karo\n"
        "/help — Ye menu dekho\n\n"
        "🤖 Groq AI (LLaMA 70B) se smart extraction hoti hai!\n"
        "Koi bhi platform ka data ho — AppX, Adda, CP, PW — sab samjhega!",
        parse_mode="HTML",
    )


# ─── Document Handler ─────────────────────────────────────────
@bot.message_handler(content_types=["document"])
def handle_document(message):
    try:
        file_name = message.document.file_name
        file_size = message.document.file_size
        logger.info(f"Received document: {file_name} ({file_size} bytes)")

        bot.reply_to(
            message,
            f"📥 <b>File received:</b> {file_name}\n"
            f"📦 Size: {file_size} bytes\n\n"
            f"🤖 AI se extract kar raha hoon... thoda wait karo!",
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
                _safe_send_message(
                    message.chat.id,
                    f"✅ <b>Extracted Info:</b>\n\n{result}"
                )

            # ─── TXT ──────────────────────────────────────────
            elif file_name.lower().endswith(".txt"):
                with open(local_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                result = extract_with_groq(content, file_name)
                _safe_send_message(
                    message.chat.id,
                    f"✅ <b>Extracted Info:</b>\n\n{result}"
                )

            # ─── ZIP ──────────────────────────────────────────
            elif file_name.lower().endswith(".zip"):
                with zipfile.ZipFile(local_path, "r") as zip_ref:
                    members = zip_ref.namelist()

                    file_list = "\n".join(f"• {m}" for m in members[:20])
                    if len(members) > 20:
                        file_list += f"\n... aur {len(members) - 20} aur files"

                    bot.reply_to(
                        message,
                        f"🗜️ ZIP mein <b>{len(members)}</b> files hain:\n\n{file_list}",
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
                                _safe_send_message(
                                    message.chat.id,
                                    f"📄 <b>{member}</b>\n\n{result}"
                                )
                                processed += 1

                            except Exception as inner_e:
                                logger.warning(f"Could not process {member}: {inner_e}")

                    if processed == 0:
                        bot.send_message(
                            message.chat.id,
                            "✅ ZIP process hua, lekin koi JSON/TXT file nahi mili andar.",
                            parse_mode="HTML",
                        )

            # ─── Unsupported ───────────────────────────────────
            else:
                bot.reply_to(
                    message,
                    "⚠️ Abhi <b>.json, .txt, .zip</b> support karta hoon.\n"
                    "Koi aur format chahiye? Batao!",
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
        "📁 Bhai file bhejo — JSON, TXT, ya ZIP!\n"
        "Text se kaam nahi chalega 😄",
        parse_mode="HTML"
    )


# ─── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    # Flask alag thread mein chalao (cron ping ke liye)
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    logger.info("✅ Flask server started for cron ping!")

    # Bot polling shuru
    logger.info("🤖 Bot polling shuru...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
