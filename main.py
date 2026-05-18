import json
import os
import zipfile
import tempfile
from dotenv import load_dotenv
import telebot
from loguru import logger

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it to the .env file.")

bot = telebot.TeleBot(TOKEN)
logger.add("bot.log", rotation="10 MB", retention="7 days", backtrace=True, diagnose=True)
logger.info("🚀 KotaZipBot started...")


def _safe_send_message(chat_id, text, parse_mode="Markdown"):
    bot.send_message(chat_id, text, parse_mode=parse_mode, disable_web_page_preview=True)


def _send_long_message(chat_id, text, parse_mode="Markdown"):
    chunk_size = 3500
    for start in range(0, len(text), chunk_size):
        chunk = text[start:start + chunk_size]
        bot.send_message(chat_id, f"```{chunk}```", parse_mode="Markdown")


@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🔥 <b>Welcome to KotaZipBot</b>\n\n"
        "Send me a JSON, TXT, or ZIP file and I will extract the contents for you.\n"
        "Main usko extract kar ke dunga 🔥",
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
            f"📥 File received: <b>{file_name}</b>\nSize: {file_size} bytes",
            parse_mode="HTML",
        )

        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = os.path.join(tmpdir, file_name)
            with open(local_path, "wb") as f:
                f.write(downloaded_file)

            bot.reply_to(message, "🔄 Extracting...")

            if file_name.lower().endswith(".json"):
                with open(local_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                extracted = json.dumps(data, indent=4, ensure_ascii=False)
                _safe_send_message(message.chat.id, "✅ Extracted JSON content:", parse_mode="HTML")
                _send_long_message(message.chat.id, extracted)

            elif file_name.lower().endswith(".txt"):
                with open(local_path, "r", encoding="utf-8") as f:
                    content = f.read()
                _safe_send_message(message.chat.id, "📝 File content:", parse_mode="HTML")
                _send_long_message(message.chat.id, content)

            elif file_name.lower().endswith(".zip"):
                with zipfile.ZipFile(local_path, "r") as zip_ref:
                    members = zip_ref.namelist()
                    bot.reply_to(
                        message,
                        f"🗜️ ZIP file contains {len(members)} item(s):\n" + "\n".join(members[:20]) + ("\n..." if len(members) > 20 else ""),
                        parse_mode="HTML",
                    )

                    extracted_texts = []
                    for member in members:
                        if member.endswith("/"):
                            continue
                        if member.lower().endswith((".json", ".txt")):
                            try:
                                with zip_ref.open(member) as f:
                                    raw = f.read()
                                    text = raw.decode("utf-8")
                            except UnicodeDecodeError:
                                text = raw.decode("latin-1", errors="replace")

                            if member.lower().endswith(".json"):
                                try:
                                    data = json.loads(text)
                                    text = json.dumps(data, indent=4, ensure_ascii=False)
                                except json.JSONDecodeError:
                                    pass

                            snippet = text[:3500]
                            extracted_texts.append(f"📄 <b>{member}</b>\n```{snippet}```")

                    if extracted_texts:
                        for part in extracted_texts:
                            bot.send_message(message.chat.id, part, parse_mode="HTML")
                    else:
                        bot.send_message(
                            message.chat.id,
                            "✅ ZIP processed, but no JSON/TXT files were found inside to display.",
                            parse_mode="HTML",
                        )

            else:
                bot.reply_to(message, "⚠️ Abhi sirf .json, .txt, aur .zip files support karta hoon.")

        logger.success(f"Processed file: {file_name}")

    except Exception as e:
        logger.exception("Failed to process document")
        bot.reply_to(message, f"❌ Error: {str(e)}")


if __name__ == "__main__":
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
