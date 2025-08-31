import os
import logging
import datetime

from flask import Flask, request
from pymongo import MongoClient
from telegram import Update, Bot
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)

# ---------- Logging ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------- Env Vars ----------
BOT_TOKEN = os.environ["BOT_TOKEN"]
MONGO_URI = os.environ["MONGO_URI"]
ADMIN_ID = int(os.environ["ADMIN_ID"])  # e.g. 123456789
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")  # optional extra security

# ---------- Globals (reused across invocations) ----------
bot = Bot(BOT_TOKEN)

# DB connect once and reuse
codes_collection = None
users_collection = None
try:
    client = MongoClient(MONGO_URI)
    # If your URI includes a default DB name, this will use it
    db = client.get_database()
    codes_collection = db["response_codes"]
    users_collection = db["users"]
    logger.info("MongoDB connected and collections ready")
except Exception as e:
    logger.error(f"MongoDB connection failed: {e}")

# Dispatcher without Updater (webhook style)
dispatcher = Dispatcher(bot, update_queue=None, workers=0)

# ---------- Handlers (same behavior as your polling bot) ----------

def start_command(update: Update, context: CallbackContext):
    if users_collection is None:
        update.message.reply_text("❌ Database connection failed. Please check MongoDB setup.")
        return

    user = update.effective_user
    users_collection.update_one(
        {"user_id": user.id},
        {
            "$set": {
                "username": user.username or "",
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "first_joined": datetime.datetime.now(),
            }
        },
        upsert=True,
    )
    update.message.reply_text("👋 Welcome! Send any code to get response.")


def handle_message(update: Update, context: CallbackContext):
    if codes_collection is None or users_collection is None:
        update.message.reply_text("❌ Database connection failed. Please check MongoDB setup.")
        return

    user_message = update.message.text
    user = update.effective_user

    users_collection.update_one(
        {"user_id": user.id},
        {
            "$set": {
                "username": user.username or "",
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "last_active": datetime.datetime.now(),
            }
        },
        upsert=True,
    )

    code_data = codes_collection.find_one({"code": user_message})
    if code_data:
        update.message.reply_text(code_data["response"])
    else:
        update.message.reply_text("❌ Code not found!")


def add_code(update: Update, context: CallbackContext):
    if codes_collection is None:
        update.message.reply_text("❌ Database connection failed. Please check MongoDB setup.")
        return

    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Only admin can use this command!")
        return

    if len(context.args) < 2:
        update.message.reply_text("📝 Usage: /addcode CODE RESPONSE")
        return

    code = context.args[0]
    response = " ".join(context.args[1:])

    now = datetime.datetime.now()
    codes_collection.update_one(
        {"code": code},
        {"$set": {"response": response, "created_at": now, "updated_at": now}},
        upsert=True,
    )

    update.message.reply_text(f"✅ Code '{code}' added/updated successfully!")


def delete_code(update: Update, context: CallbackContext):
    if codes_collection is None:
        update.message.reply_text("❌ Database connection failed. Please check MongoDB setup.")
        return

    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Only admin can use this command!")
        return

    if not context.args:
        update.message.reply_text("📝 Usage: /deletecode CODE")
        return

    code = context.args[0]
    result = codes_collection.delete_one({"code": code})

    if result.deleted_count > 0:
        update.message.reply_text(f"✅ Code '{code}' deleted successfully!")
    else:
        update.message.reply_text("❌ Code not found!")


def list_codes(update: Update, context: CallbackContext):
    if codes_collection is None:
        update.message.reply_text("❌ Database connection failed. Please check MongoDB setup.")
        return

    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Only admin can use this command!")
        return

    codes = list(codes_collection.find({}, {"_id": 0, "code": 1}))
    if codes:
        code_list = "\n".join([f"• {c['code']}" for c in codes])
        update.message.reply_text(f"📋 Available codes ({len(codes)}):\n{code_list}")
    else:
        update.message.reply_text("📭 No codes added yet!")


# Register handlers
dispatcher.add_handler(CommandHandler("start", start_command))
dispatcher.add_handler(CommandHandler("addcode", add_code))
dispatcher.add_handler(CommandHandler("deletecode", delete_code))
dispatcher.add_handler(CommandHandler("listcodes", list_codes))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

# ---------- Flask app (Vercel Serverless) ----------
app = Flask(__name__)

@app.route("/", methods=["GET"])
def health():
    return "OK", 200

@app.route("/", methods=["POST"])
def webhook():
    # Optional security: verify Telegram secret header if you set one
    if WEBHOOK_SECRET:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if header != WEBHOOK_SECRET:
            logger.warning("Forbidden: wrong secret token header")
            return "Forbidden", 403

    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return "Bad Request", 400
        update = Update.de_json(data, bot)
        dispatcher.process_update(update)
    except Exception as e:
        logger.exception(f"Error handling update: {e}")
        return "Internal Server Error", 500

    return "OK", 200
