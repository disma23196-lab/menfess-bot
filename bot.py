import json
import uuid
import time
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import re

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
})

BAD_WORDS = [
    "anjing", "anjir", "njir", "bjir",
    "bangsat", "bajingan", "sialan",
    "goblok", "tolol", "bego", "idiot",
    "kampret", "keparat",
    "kontol", "kntl", "memek", "mmk",
    "tai", "tahi", "setan", "iblis",
    "shit", "fuck", "fck", "fak", "damn", "hell",
    "bastard", "asshole", "bitch", "motherfucker",
    "cunt", "dick", "pussy", "wtf", "stfu",
    "bullshit", "kocak", "gila",
    "asu", "jancok", "jancuk", "cok", "cuk",
    "ndasmu", "matamu", "raimu",
    "bangke", "bangkean", "gendeng", "cringe",
]

def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.translate(LEET_MAP)

    # ubah simbol jadi spasi
    text = re.sub(r"[^a-z0-9]", " ", text)

    # huruf berulang dipendekkan: gobloooook -> goblok
    text = re.sub(r"(.)\1{2,}", r"\1", text)

    # rapikan spasi
    text = re.sub(r"\s+", " ", text).strip()
    return text

def is_toxic(text: str) -> bool:
    normal = normalize_text(text)
    joined = normal.replace(" ", "")

    for bad in BAD_WORDS:
        if bad in normal:
            return True
        if bad in joined:
            return True

    return False


# =========================
# FILTER CAPSLOCK BERLEBIHAN
# =========================
def is_caps_spam(text: str) -> bool:
    if not text:
        return False

    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False

    upper = sum(1 for c in letters if c.isupper())
    ratio = upper / len(letters)

    # lebih fleksibel: caps pendek karena excited masih boleh
    return ratio > 0.8 and len(text) > 20

from config import *

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =========================
# FILE BANTU
# =========================
def load_data():
    try:
        with open("data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"messages": {}, "stats": {}}

def save_data(data):
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_banned():
    try:
        with open("banned.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_banned(data):
    with open("banned.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data_db = load_data()
banned_users = load_banned()

last_message_time = {}
SPAM_DELAY = 100  # detik

def admin_buttons(uid, user_id):
    if user_id in banned_users:
        ban_button = InlineKeyboardButton("✅ Unban", callback_data=f"unban:{uid}")
    else:
        ban_button = InlineKeyboardButton("🚫 Ban", callback_data=f"ban:{uid}")

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 Reply", callback_data=f"reply:{uid}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{uid}"),
            ban_button
        ]
    ])

def update_stats(user_id):
    user_id = str(user_id)
    if "stats" not in data_db:
        data_db["stats"] = {}
    if user_id not in data_db["stats"]:
        data_db["stats"][user_id] = 0
    data_db["stats"][user_id] += 1
    save_data(data_db)

# =========================
# COMMAND
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! siswa dan siswi SMPN 54 Surabaya👋\n\n"
        "Kamu bisa gunakan format berikut untuk mengirim menfess:\n"
        "#keep untuk menfess curhatan yang akan terkirim secara anonim ke admin BK SMPN 54 Surabaya\n"
        "#publish untuk menfess yang akan terkirim ke channel utama\n\n"
        "Mohon untuk memperhatikan bahasa dan kalimat yang akan di gunakan"
    )

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    if not context.args:
        await update.message.reply_text("Format: /unban ID_USER")
        return

    try:
        user_id = int(context.args[0])
        if user_id in banned_users:
            banned_users.remove(user_id)
            save_banned(banned_users)
            await update.message.reply_text("✅ User berhasil di-unban")
        else:
            await update.message.reply_text("User itu tidak sedang diban")
    except:
        await update.message.reply_text("Format: /unban ID_USER")

# =========================
# HANDLE PESAN USER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ⬇️ TARUH DI SINI (PALING ATAS)
    if update.effective_chat.type != "private":
        return

    user = update.effective_user
    message = update.message

    if not message or not message.text:
        return

    text = message.text.strip()

    if update.effective_chat.id == ADMIN_GROUP_ID:
        return

    user = update.effective_user
    message = update.message

    if not message or not message.text:
        return

    text = message.text.strip()

    # cek ban
    if user.id in banned_users:
        await message.reply_text("❌ Kamu sedang dibanned.")
        return

    # anti spam
    now = time.time()
    if user.id in last_message_time:
        if now - last_message_time[user.id] < SPAM_DELAY:
            await message.reply_text("🚫 Jangan spam ya, tunggu sebentar.")
            return
    last_message_time[user.id] = now

    # update statistik
    update_stats(user.id)

    uid = str(uuid.uuid4())[:8]

    # ================= KEEP =================
    if "#keep" in text.lower():
        clean = text.replace("#keep", "").strip()

        if not clean:
            await message.reply_text("Tulis pesannya juga ya. Contoh:\n#keep aku lagi capek")
            return

        sent_msg = await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=(
                f"🆔 {uid}\n"
                f"👤 USER ID: {user.id}\n"
                f"📩 MENFESS KEEP\n\n"
                f"{clean}"
            ),
            reply_markup=admin_buttons(uid, user.id)
        )

        data_db["messages"][uid] = {
            "user_id": user.id,
            "type": "keep",
            "admin_msg_id": sent_msg.message_id
        }
        save_data(data_db)

        await message.reply_text("✅ Pesan rahasia kamu sudah dikirim ke admin Menfess.")
        return

    # ================= PUBLISH =================
    elif text.lower().startswith("#publish"):
        clean = re.sub(r"#publish", "", text, flags=re.IGNORECASE).strip()

    if not clean:
        await message.reply_text("Tulis pesannya juga ya. Contoh:\n#publish halo semua")
        return

    if is_toxic(clean):
        await message.reply_text("❌ Pesan mengandung kata tidak pantas.")
        return

    if is_caps_spam(clean):
        await message.reply_text("⚠️ Jangan pakai huruf kapital berlebihan ya.")
        return

    sent_msg = await context.bot.send_message(
        chat_id=MAIN_CHANNEL_ID,
        text=f"🆔 {uid}\n📢 MENFESS\n\n{clean}"
    )

    data_db["messages"][uid] = {
        "user_id": user.id,
        "type": "publish",
        "msg_id": sent_msg.message_id
    }
    save_data(data_db)

    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=(
            f"🆔 {uid}\n"
            f"👤 USER ID: {user.id}\n"
            f"📢 MENFESS PUBLISH\n\n"
            f"{clean}"
        ),
        reply_markup=admin_buttons(uid, user.id)
    )
    await message.reply_text("✅ Menfess kamu berhasil dipublish.")
    return

# =========================
# TOMBOL ADMIN
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id not in ADMIN_IDS:
        await query.message.reply_text("Kamu bukan admin.")
        return

    action, uid = query.data.split(":")

    if uid not in data_db["messages"]:
        await query.message.reply_text("❌ Data tidak ditemukan.")
        return

    user_id = data_db["messages"][uid]["user_id"]

    if action == "reply":
        context.chat_data["reply_to"] = uid
        await query.message.reply_text(f"✏️ Balas untuk ID {uid}")

    elif action == "delete":
        msg_data = data_db["messages"][uid]

        if msg_data["type"] == "publish":
            try:
                await context.bot.delete_message(
                    chat_id=MAIN_CHANNEL_ID,
                    message_id=msg_data["msg_id"]
                )
            except:
                pass

        del data_db["messages"][uid]
        save_data(data_db)

        await query.message.reply_text("🗑 Menfess berhasil dihapus.")

    elif action == "ban":
        if user_id not in banned_users:
            banned_users.append(user_id)
            save_banned(banned_users)

        await query.message.reply_text("🚫 User berhasil dibanned.")

        await query.message.edit_reply_markup(
            reply_markup=admin_buttons(uid, user_id)
        )

    elif action == "unban":
        if user_id in banned_users:
            banned_users.remove(user_id)
            save_banned(banned_users)

        await query.message.reply_text("✅ User berhasil di-unban.")

        await query.message.edit_reply_markup(
            reply_markup=admin_buttons(uid, user_id)
        )
        
# =========================
# BALASAN ADMIN KE USER
# =========================
async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return

    if "reply_to" not in context.chat_data:
        return

    uid = context.chat_data["reply_to"]

    if uid not in data_db["messages"]:
        await update.message.reply_text("❌ Data tidak ditemukan.")
        context.chat_data.pop("reply_to", None)
        return

    user_id = data_db["messages"][uid]["user_id"]

    await context.bot.send_message(
        chat_id=user_id,
        text=f"📩 Balasan Admin:\n\n{update.message.text}"
    )

    await update.message.reply_text("✅ Balasan berhasil dikirim ke sender.")
    context.chat_data.pop("reply_to", None)

# =========================
# ERROR HANDLER
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Terjadi error:", exc_info=context.error)

# =========================
# BERSIHKAN WEBHOOK
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
    handle_admin_reply
))

app.add_handler(CallbackQueryHandler(button_handler))

app.add_handler(MessageHandler(
    filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
    handle_message
))
print("Bot running...")
app.run_polling(drop_pending_updates=True)
