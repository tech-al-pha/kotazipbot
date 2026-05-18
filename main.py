import json
import os
import zipfile
import tempfile
from dotenv import load_dotenv
import telebot
from loguru import logger
import google.generativeai as genai

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it to the .env file.")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing. Add it to the .env file.")

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

bot = telebot.TeleBot(TOKEN)
logger.add("bot.log", rotation="10 MB", retention="7 days", backtrace=True, diagnose=True)
logger.info("🚀 KotaZipBot started...")


def _safe_send_message(chat_id, text, parse_mode="HTML"):
    bot.send_message(chat_id, text, parse_mode=parse_mode, disable_web_page_preview=True)


def _send_long_message(chat_id, text, parse_mode="HTML"):
    chunk_size = 3500
    for start in range(0, len(text), chunk_size):
        chunk = text[start:start + chunk_size]
        bot.send_message(chat_id, chunk, parse_mode=parse_mode, disable_web_page_preview=True)


def extract_with_gemini(content: str, file_name: str) -> str:
    """Gemini AI se content extract karao nicely formatted"""
    prompt = f"""
Tu ek course extractor hai. Neeche ek file ka content diya gaya hai jiska naam hai: "{file_name}"

Tera kaam hai is content ko analyze karna aur clearly extract karna:

1. 📚 Course/Batch ka naam
2. 🏫 Platform detect karo (AppX, AppsLixt, Adda247, CipherSchools, CP, PW, Unacademy, etc.)
3. 📖 Subjects / Topics list
4. 🔗 Koi bhi links (video, PDF, notes, etc.)
5. 👨‍🏫 Teacher/Instructor ka naam (agar ho)
6. 📅 Duration ya Schedule (agar ho)
7. 📝 Koi bhi important info

Format: Clean aur readable Telegram HTML format mein do.
Bold headings ke liye <b>text</b> use karo.
Agar koi cheez nahi milti to skip karo.
Sirf relevant info do, raw data mat do.

File Content:
{content[:8000]}
"""
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return f"⚠️ AI extraction failed: {str(e)}\n\nRaw content neeche hai:"


@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🔥 <b>Welcome to KotaZipBot</b>\n\n"
        "Mujhe koi bhi file bhejo — JSON, TXT, ZIP, PDF\n"
        "Main AI se extract karke bataunga:\n\n"
        "📚 Course name\n"
        "🏫 Platform\n"
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
        "📌 <b>Supported Formats:</b>\n\n"
        "✅ .json — Course JSON files\n"
        "✅ .txt — Text files\n"
        "✅ .zip — ZIP archives (JSON/TXT andar)\n"
        "✅ .pdf — PDF documents\n\n"
        "🤖 Gemini AI se smart extraction hoti hai!\n"
        "Koi bhi platform ka data ho — AppX, Adda, CP, PW — sab samjhega!",
        parse_mode="HTML",
    )


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
            f"🤖 AI se extract kar raha hoon...",
            parse_mode="HTML",
        )

        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = os.path.join(tmpdir, file_name)
            with open(local_path, "wb") as f:
                f.write(downloaded_file)

            # ─── JSON ───────────────────────────────────────────
            if file_name.lower().endswith(".json"):
                with open(local_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                raw_text = json.dumps(data, indent=2, ensure_ascii=False)
                result = extract_with_gemini(raw_text, file_name)
                _safe_send_message(message.chat.id, f"✅ <b>Extracted Info:</b>\n\n{result}")

            # ─── TXT ────────────────────────────────────────────
            elif file_name.lower().endswith(".txt"):
                with open(local_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                result = extract_with_gemini(content, file_name)
                _safe_send_message(message.chat.id, f"✅ <b>Extracted Info:</b>\n\n{result}")

            # ─── PDF ────────────────────────────────────────────
            elif file_name.lower().endswith(".pdf"):
                try:
                    import pdfplumber
                    with pdfplumber.open(local_path) as pdf:
                        text = ""
                        for page in pdf.pages[:10]:  # max 10 pages
                            text += page.extract_text() or ""
                    if text.strip():
                        result = extract_with_gemini(text, file_name)
                        _safe_send_message(message.chat.id, f"✅ <b>Extracted Info:</b>\n\n{result}")
                    else:
                        bot.reply_to(message, "⚠️ PDF mein readable text nahi mila (scanned image ho sakti hai).")
                except ImportError:
                    bot.reply_to(message, "⚠️ PDF support ke liye <code>pdfplumber</code> install karo:\n<code>pip install pdfplumber</code>", parse_mode="HTML")

            # ─── ZIP ────────────────────────────────────────────
            elif file_name.lower().endswith(".zip"):
                with zipfile.ZipFile(local_path, "r") as zip_ref:
                    members = zip_ref.namelist()
                    bot.reply_to(
                        message,
                        f"🗜️ ZIP mein <b>{len(members)}</b> files hain:\n" +
                        "\n".join(f"• {m}" for m in members[:20]) +
                        ("\n..." if len(members) > 20 else ""),
                        parse_mode="HTML",
                    )

                    processed = 0
                    for member in members:
                        if member.endswith("/"):
                            continue
                        if member.lower().endswith((".json", ".txt", ".pdf")):
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

                                result = extract_with_gemini(text, member)
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
                            "✅ ZIP process hua, lekin koi JSON/TXT/PDF file nahi mili andar.",
                            parse_mode="HTML",
                        )

            else:
                bot.reply_to(
                    message,
                    "⚠️ Abhi <b>.json, .txt, .zip, .pdf</b> support karta hoon.\n"
                    "Koi aur format chahiye? Batao!",
                    parse_mode="HTML"
                )

        logger.success(f"Processed file: {file_name}")

    except Exception as e:
        logger.exception("Failed to process document")
        bot.reply_to(message, f"❌ <b>Error:</b> {str(e)}", parse_mode="HTML")


if __name__ == "__main__":
    logger.info("Bot polling shuru...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
