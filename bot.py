import json
import uuid
import time
import logging
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import *

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =========================
# FILTER KATA TIDAK PANTAS
# =========================
LEET_MAP = str.maketrans({
    "0": "o",
    "1": "i",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "@": "a",
    "$": "s",
    "!": "i",
})

BAD_WORDS_ANYWHERE = [
    "anjing", "anjir", "anying", "anjg", "njir", "bjir",
    "bangsat", "bajingan", "sialan", "keparat", "kampret",
    "goblok", "tolol", "bego", "idiot",
    "kocak", "gila", "gendeng",
    "kontol", "kntl", "memek", "mmk",
    "tahi", "setan", "iblis",
    "asu", "jancok", "jancuk", "jancik",
    "ndasmu", "matamu", "raimu",
    "bangke", "bangkean",
    "shit", "fuck", "fck", "fak",
    "damn", "hell", "bastard",
    "asshole", "bitch",
    "motherfucker", "cunt",
    "dick", "pussy",
    "wtf", "stfu",
    "bullshit", "cringe",
]

BAD_WORDS_WHOLE = [
    "tai", "bs", "af", "cok", "cuk",
]

def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.translate(LEET_MAP)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"(.)\1{2,}", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def is_toxic(text: str) -> bool:
    normal = normalize_text(text)
    joined = normal.replace(" ", "")
    words = set(normal.split())

    for bad in BAD_WORDS_ANYWHERE:
        if bad in normal:
            return True
        if bad in joined:
            return True

    for bad in BAD_WORDS_WHOLE:
        if bad in words:
            return True

    return False

def is_caps_spam(text: str) -> bool:
    if not text:
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    upper = sum(1 for c in letters if c.isupper())
    ratio = upper / len(letters)
    return ratio > 0.8 and len(text) > 20

# =========================
# FILE BANTU (DATABASE LOKAL)
# =========================
def load_data():
    try:
        with open("data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"messages": {}, "stats": {}}

def save_data(data):
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_banned():
    try:
        with open("banned.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_banned(data):
    with open("banned.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data_db = load_data()
banned_users = load_banned()

last_message_time = {}
SPAM_DELAY = 60
MAX_MSG_LENGTH = 1500

# =========================
# TOMBOL ADMIN
# =========================
def admin_buttons(uid, user_id):
    if user_id in banned_users:
        ban_button = InlineKeyboardButton("✅ Unban", callback_data=f"unban:{uid}")
    else:
        ban_button = InlineKeyboardButton("🚫 Ban", callback_data=f"ban:{uid}")

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 Reply", callback_data=f"reply:{uid}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{uid}"),
            ban_button,
        ]
    ])

# =========================
# STATISTIK
# =========================
def update_stats(user_id):
    uid_str = str(user_id)
    if "stats" not in data_db:
        data_db["stats"] = {}
    data_db["stats"][uid_str] = data_db["stats"].get(uid_str, 0) + 1
    save_data(data_db)

# =========================
# COMMAND /start
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! Siswa dan siswi SMPN 54 Surabaya 👋\n\n"
        "Kamu bisa mengirim menfess dengan format:\n\n"
        "📩 #keep [pesan] — menfess curhatan ke admin BK (anonim)\n"
        "📢 #publish [pesan] — menfess ke channel utama (anonim)\n\n"
        "⚠️ Mohon gunakan bahasa yang sopan dan bertanggung jawab.\n"
        "Pesan yang mengandung kata tidak pantas akan otomatis ditolak."
    )

# =========================
# COMMAND /unban
# =========================
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    if not context.args:
        await update.message.reply_text("Format: /unban [ID_USER]")
        return

    try:
        user_id = int(context.args[0])
        if user_id in banned_users:
            banned_users.remove(user_id)
            save_banned(banned_users)
            await update.message.reply_text(f"✅ User {user_id} berhasil di-unban.")
        else:
            await update.message.reply_text("User tersebut tidak sedang diban.")
    except ValueError:
        await update.message.reply_text("Format: /unban [ID_USER]")

# =========================
# HANDLE PESAN USER (PRIVATE)
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    user = update.effective_user
    message = update.message

    if not message or not message.text:
        return

    text = message.text.strip()

    # Cek ban
    if user.id in banned_users:
        await message.reply_text("❌ Kamu sedang dibanned dan tidak bisa mengirim menfess.")
        return

    # Anti spam
    now = time.time()
    last = last_message_time.get(user.id, 0)
    if now - last < SPAM_DELAY:
        sisa = int(SPAM_DELAY - (now - last))
        await message.reply_text(f"🚫 Tunggu {sisa} detik sebelum kirim menfess lagi ya.")
        return
    last_message_time[user.id] = now

    update_stats(user.id)
    uid = str(uuid.uuid4())[:8]

    # ─── #keep ────────────────────────────────────────────────
    if text.lower().startswith("#keep"):
        clean = re.sub(r"^#keep\s*", "", text, flags=re.IGNORECASE).strip()

        if not clean:
            await message.reply_text(
                "Tulis pesannya juga ya 😊\nContoh: #keep aku lagi galau soal ujian"
            )
            return

        if len(clean) > MAX_MSG_LENGTH:
            await message.reply_text(
                f"❌ Pesan terlalu panjang. Maksimal {MAX_MSG_LENGTH} karakter."
            )
            return

        if is_toxic(clean):
            await message.reply_text(
                "❌ Pesan mengandung kata tidak pantas dan tidak bisa dikirim."
            )
            return

        # Kirim ke grup admin
        try:
            sent_msg = await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=(
                    f"🆔 {uid}\n"
                    f"👤 USER ID: {user.id}\n"
                    f"📩 MENFESS KEEP\n\n"
                    f"{clean}"
                ),
                reply_markup=admin_buttons(uid, user.id),
            )
            data_db["messages"][uid] = {
                "user_id": user.id,
                "type": "keep",
                "admin_msg_id": sent_msg.message_id,
            }
            save_data(data_db)
        except Exception as e:
            logging.error(f"Gagal kirim ke admin grup (keep): {e}")
            await message.reply_text(f"❌ Gagal mengirim ke admin. Error: {e}")
            return

        await message.reply_text(
            "✅ Pesan curhatan kamu sudah dikirim ke admin BK secara anonim."
        )
        return

    # ─── #publish ─────────────────────────────────────────────
    elif text.lower().startswith("#publish"):
        clean = re.sub(r"^#publish\s*", "", text, flags=re.IGNORECASE).strip()

        if not clean:
            await message.reply_text(
                "Tulis pesannya juga ya 😊\nContoh: #publish halo semua!"
            )
            return

        if len(clean) > MAX_MSG_LENGTH:
            await message.reply_text(
                f"❌ Pesan terlalu panjang. Maksimal {MAX_MSG_LENGTH} karakter."
            )
            return

        if is_toxic(clean):
            await message.reply_text(
                "❌ Pesan mengandung kata tidak pantas dan tidak bisa dipublish."
            )
            return

        if is_caps_spam(clean):
            await message.reply_text(
                "⚠️ Jangan pakai huruf kapital berlebihan ya. Coba tulis ulang."
            )
            return

        # Step 1: kirim ke channel utama
        try:
            sent_msg = await context.bot.send_message(
                chat_id=MAIN_CHANNEL_ID,
                text=f"🆔 {uid}\n📢 MENFESS\n\n{clean}",
            )
            data_db["messages"][uid] = {
                "user_id": user.id,
                "type": "publish",
                "msg_id": sent_msg.message_id,
            }
            save_data(data_db)
        except Exception as e:
            logging.error(f"Gagal kirim ke channel: {e}")
            await message.reply_text(f"❌ Gagal mengirim ke channel. Error: {e}")
            return

        # Step 2: kirim log ke grup admin (tidak batalkan publish kalau ini gagal)
        try:
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=(
                    f"🆔 {uid}\n"
                    f"👤 USER ID: {user.id}\n"
                    f"📢 MENFESS PUBLISH\n\n"
                    f"{clean}"
                ),
                reply_markup=admin_buttons(uid, user.id),
            )
        except Exception as e:
            # Publish ke channel sudah berhasil, jadi tetap kasih konfirmasi ke user
            # tapi catat error admin di log
            logging.error(f"Gagal kirim log ke admin grup: {e}")

        # Step 3: konfirmasi ke user (selalu jalan selama channel berhasil)
        await message.reply_text("✅ Menfess kamu berhasil dipublish ke channel!")
        return

    # ─── Format tidak dikenal ─────────────────────────────────
    else:
        await message.reply_text(
            "Hmm, format tidak dikenali 🤔\n\n"
            "Gunakan:\n"
            "📩 #keep [pesan] — ke admin BK\n"
            "📢 #publish [pesan] — ke channel"
        )
        return

# =========================
# TOMBOL ADMIN (CALLBACK)
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id not in ADMIN_IDS:
        await query.answer("Kamu bukan admin.", show_alert=True)
        return

    try:
        action, uid = query.data.split(":", 1)
    except ValueError:
        await query.message.reply_text("❌ Format tombol tidak valid.")
        return

    if uid not in data_db["messages"]:
        await query.message.reply_text(
            "❌ Data menfess tidak ditemukan.\n"
            "(Kemungkinan bot baru restart dan data lama hilang.)"
        )
        return

    user_id = data_db["messages"][uid]["user_id"]

    if action == "reply":
        context.chat_data["reply_to"] = uid
        await query.message.reply_text(
            f"✏️ Mode reply aktif untuk menfess ID {uid}\n"
            f"Ketik pesan balasan kamu sekarang."
        )

    elif action == "delete":
        msg_data = data_db["messages"][uid]

        if msg_data["type"] == "publish":
            try:
                await context.bot.delete_message(
                    chat_id=MAIN_CHANNEL_ID,
                    message_id=msg_data["msg_id"],
                )
            except Exception as e:
                logging.warning(f"Gagal hapus pesan di channel: {e}")

        del data_db["messages"][uid]
        save_data(data_db)
        await query.message.reply_text("🗑 Menfess berhasil dihapus.")

    elif action == "ban":
        if user_id not in banned_users:
            banned_users.append(user_id)
            save_banned(banned_users)
        await query.message.reply_text(f"🚫 User {user_id} berhasil dibanned.")
        await query.message.edit_reply_markup(
            reply_markup=admin_buttons(uid, user_id)
        )

    elif action == "unban":
        if user_id in banned_users:
            banned_users.remove(user_id)
            save_banned(banned_users)
        await query.message.reply_text(f"✅ User {user_id} berhasil di-unban.")
        await query.message.edit_reply_markup(
            reply_markup=admin_buttons(uid, user_id)
        )

# =========================
# BALASAN ADMIN → USER
# =========================
async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return

    if "reply_to" not in context.chat_data:
        return

    if not update.message or not update.message.text:
        return

    uid = context.chat_data["reply_to"]

    if uid not in data_db["messages"]:
        await update.message.reply_text("❌ Data menfess tidak ditemukan.")
        context.chat_data.pop("reply_to", None)
        return

    user_id = data_db["messages"][uid]["user_id"]

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📩 Balasan dari Admin:\n\n{update.message.text}",
        )
        await update.message.reply_text("✅ Balasan berhasil dikirim ke pengirim menfess.")
    except Exception as e:
        logging.error(f"Gagal kirim balasan ke user: {e}")
        await update.message.reply_text("❌ Gagal mengirim balasan. Pastikan user masih aktif.")

    context.chat_data.pop("reply_to", None)

# =========================
# ERROR HANDLER
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Terjadi error:", exc_info=context.error)

# =========================
# BERSIHKAN WEBHOOK SAAT START
# =========================
async def post_init(application):
    await application.bot.delete_webhook(drop_pending_updates=True)

# =========================
# JALANKAN BOT
# =========================
app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

app.add_error_handler(error_handler)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("unban", unban_command))

app.add_handler(MessageHandler(
    filters.TEXT & filters.Chat(ADMIN_GROUP_ID) & ~filters.COMMAND,
    handle_admin_reply,
))

app.add_handler(CallbackQueryHandler(button_handler))

app.add_handler(MessageHandler(
    filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
    handle_message,
))

print("Bot running...")
app.run_polling(drop_pending_updates=True)
