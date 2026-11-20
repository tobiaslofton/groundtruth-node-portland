"""Telegram Bot integration for Human-in-the-Loop operator notifications and proof uploads."""
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

from src.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_OPERATOR_CHAT_ID,
    PROOF_DIR,
    BASE_PUBLIC_URL
)
from src.db import (
    get_task,
    update_task_status,
    complete_task,
    get_current_active_task,
    log_demand_research,
    is_operator_available,
    set_operator_available
)
from src.vision import analyze_field_photo

logger = logging.getLogger("ground_truth.telegram")

def extract_exif(image_bytes: bytes) -> Dict[str, Any]:
    """Extract standard EXIF and GPS metadata from uploaded photo bytes."""
    metadata = {}
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            exif_raw = img._getexif()
            if not exif_raw:
                return {"has_exif": False}
            for tag_id, value in exif_raw.items():
                tag_name = TAGS.get(tag_id, str(tag_id))
                if tag_name == "GPSInfo":
                    gps_data = {}
                    for t in value:
                        sub_tag = GPSTAGS.get(t, str(t))
                        gps_data[sub_tag] = str(value[t])
                    metadata["gps"] = gps_data
                elif isinstance(value, (str, int, float)):
                    metadata[tag_name] = value
            metadata["has_exif"] = True
    except Exception as e:
        logger.warning("Error parsing EXIF metadata: %s", e)
        metadata["exif_error"] = str(e)
    return metadata

def build_task_card(task: Dict[str, Any]) -> str:
    """Format structured Telegram message for incoming agent dispatch."""
    questions_fmt = "\n".join([f"  • {q}" for q in task.get("specific_questions", [])]) or "  • General verification"
    return (
        f"🚨 *NEW AGENT DISPATCH REQUEST*\n\n"
        f"*Task ID:* `{task['task_id']}`\n"
        f"*Type:* `{task['task_type']}`\n"
        f"*Location:* {task['location']}\n\n"
        f"*Questions / Checklist:*\n{questions_fmt}\n\n"
        f"*Stated Purpose:* {task.get('stated_purpose') or 'None specified'}\n"
        f"*Expires:* in 15 minutes"
    )

async def send_dispatch_notification(app: Optional[Application], task: Dict[str, Any]) -> None:
    """Send card with inline buttons directly to the operator's Telegram chat."""
    if not TELEGRAM_OPERATOR_CHAT_ID or not TELEGRAM_BOT_TOKEN:
        logger.error("Telegram credentials missing in configuration.")
        return

    keyboard = [
        [
            InlineKeyboardButton("✅ Accept Task", callback_data=f"accept:{task['task_id']}"),
        ],
        [
            InlineKeyboardButton("❌ Decline (Scope)", callback_data=f"decline_scope:{task['task_id']}"),
            InlineKeyboardButton("🚫 Decline (Unsafe)", callback_data=f"decline_unsafe:{task['task_id']}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    card_text = build_task_card(task)

    if app and app.bot:
        try:
            await app.bot.send_message(
                chat_id=TELEGRAM_OPERATOR_CHAT_ID,
                text=card_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            return
        except Exception as e:
            logger.warning("Failed sending via app.bot, falling back to direct HTTP: %s", e)

    # Standalone HTTP fallback (used when running via FastMCP stdio without polling bot)
    try:
        import json
        import urllib.request
        payload = {
            "chat_id": TELEGRAM_OPERATOR_CHAT_ID,
            "text": card_text,
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": "✅ Accept Task", "callback_data": f"accept:{task['task_id']}"}],
                    [
                        {"text": "❌ Decline (Scope)", "callback_data": f"decline_scope:{task['task_id']}"},
                        {"text": "🚫 Decline (Unsafe)", "callback_data": f"decline_unsafe:{task['task_id']}"}
                    ]
                ]
            }
        }
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            logger.info("Direct HTTP Telegram alert sent successfully.")
    except Exception as e:
        logger.error("Direct HTTP Telegram alert failed: %s", e)

async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Accept / Decline inline keyboard taps."""
    query = update.callback_query
    await query.answer()

    data = query.data
    action, task_id = data.split(":", 1)
    task = await get_task(task_id)

    if not task:
        await query.edit_message_text(f"⚠️ Task `{task_id}` not found.")
        return

    if task["status"] not in ("pending_operator_review",):
        await query.edit_message_text(f"ℹ️ Task `{task_id}` is already in status: `{task['status']}`.")
        return

    if action == "accept":
        # Check if another task is already accepted and in-progress
        current_active = await get_current_active_task()
        if current_active and current_active["task_id"] != task_id:
            await query.edit_message_text(
                f"⚠️ Cannot accept Task `{task_id}`. You already have an active task: `{current_active['task_id']}`."
            )
            return

        await update_task_status(task_id, "accepted_in_progress")
        await query.edit_message_text(
            f"✅ *ACCEPTED Task `{task_id}`*\n\n"
            f"📍 *Location:* {task['location']}\n"
            f"Instructions: Drive to site, take your verification photo, and send it directly in this chat.",
            parse_mode="Markdown"
        )
    elif action == "decline_scope":
        reason = "Operator declined: Task is currently outside the Portland pilot operational scope."
        await update_task_status(task_id, "declined", decline_reason=reason)
        log_demand_research({
            "task_id": task_id,
            "decision": "declined_scope",
            "location": task["location"],
            "task_type": task["task_type"],
            "questions": task["specific_questions"]
        })
        await query.edit_message_text(f"❌ *DECLINED Task `{task_id}`* (Marked out of scope).", parse_mode="Markdown")
    elif action == "decline_unsafe":
        reason = "Operator declined: Task violates public-property or personal safety boundaries."
        await update_task_status(task_id, "declined", decline_reason=reason)
        log_demand_research({
            "task_id": task_id,
            "decision": "declined_unsafe",
            "location": task["location"],
            "task_type": task["task_type"],
            "questions": task["specific_questions"]
        })
        await query.edit_message_text(f"🚫 *DECLINED Task `{task_id}`* (Flagged unsafe/prohibited).", parse_mode="Markdown")

async def handle_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle camera photo sent by the operator to fulfill the active task."""
    if update.effective_chat.id != TELEGRAM_OPERATOR_CHAT_ID:
        return

    active_task = await get_current_active_task()
    if not active_task:
        await update.message.reply_text("ℹ️ You currently have no accepted in-progress tasks to fulfill.")
        return

    task_id = active_task["task_id"]
    # Get highest resolution photo from message
    photo = update.message.photo[-1]
    photo_file = await photo.get_file()
    image_bytes = await photo_file.download_as_bytearray()

    # Extract EXIF metadata before stripping
    metadata = extract_exif(image_bytes)

    # Strip all personal EXIF/GPS device metadata to protect operator privacy
    try:
        with Image.open(io.BytesIO(image_bytes)) as pil_img:
            clean_buf = io.BytesIO()
            if pil_img.mode in ("RGBA", "P"):
                pil_img = pil_img.convert("RGB")
            pil_img.save(clean_buf, format="JPEG", quality=92)
            saved_bytes = clean_buf.getvalue()
    except Exception as e:
        logger.warning("EXIF stripping failed, saving raw bytes: %s", e)
        saved_bytes = image_bytes

    # Save sanitized photo to proof directory
    filename = f"{task_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jpg"
    dest_path = PROOF_DIR / filename
    with open(dest_path, "wb") as f:
        f.write(saved_bytes)

    photo_url = f"{BASE_PUBLIC_URL}/proof/{filename}"

    # Run automated Gemini multimodal vision analysis
    analysis = await analyze_field_photo(
        saved_bytes, 
        active_task["location"], 
        active_task.get("specific_questions", [])
    )

    # Extract caption if provided as operator notes
    notes = update.message.caption or "Verified photo captured on-site."
    extracted_answers = {
        "operator_notes": notes,
        "verified_on_site": True,
        "has_gps": "gps" in metadata,
        "vision_analysis": analysis
    }

    # Mark completed in database
    await complete_task(task_id, photo_url, metadata, extracted_answers)

    vision_summary = analysis.get("summary", "Photo stored successfully.")
    await update.message.reply_text(
        f"🎉 *TASK FULFILLED!*\n\n"
        f"*Task ID:* `{task_id}`\n"
        f"*Proof Saved:* `{filename}` (EXIF Stripped)\n"
        f"*AI Vision Finding:* {vision_summary}\n\n"
        f"*Status:* Delivered to AI Agent.",
        parse_mode="Markdown"
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command to display operator status and Chat ID."""
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"🤖 *Portland Ground-Truth Operator Bridge Active*\n\n"
        f"Your Chat ID: `{chat_id}`\n"
        f"Configured Operator: `{TELEGRAM_OPERATOR_CHAT_ID}`\n\n"
        f"Commands:\n"
        f"• `/status` - Check node state and active task\n"
        f"• `/cancel` - Cancel current in-progress task\n"
        f"• `/pause` - Pause node (Off-Duty mode)\n"
        f"• `/resume` - Resume node (On-Duty mode)",
        parse_mode="Markdown"
    )

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pause to put node into off-duty mode."""
    if update.effective_chat.id != TELEGRAM_OPERATOR_CHAT_ID:
        return
    await set_operator_available(False)
    await update.message.reply_text(
        "⏸️ *Node #001 PAUSED (Off-Duty)*\n\n"
        "Incoming agent dispatches will be immediately rejected with an off-duty notice.\n"
        "Send `/resume` when you are back on shift.",
        parse_mode="Markdown"
    )

async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /resume to restore node to active mode."""
    if update.effective_chat.id != TELEGRAM_OPERATOR_CHAT_ID:
        return
    await set_operator_available(True)
    await update.message.reply_text(
        "▶️ *Node #001 RESUMED (Active)*\n\n"
        "Standing by for incoming autonomous agent physical verification dispatches.",
        parse_mode="Markdown"
    )

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cancel to abort the current accepted task and release the node."""
    if update.effective_chat.id != TELEGRAM_OPERATOR_CHAT_ID:
        return
    active_task = await get_current_active_task()
    if not active_task:
        await update.message.reply_text("ℹ️ You currently have no accepted in-progress task to cancel.")
        return
    task_id = active_task["task_id"]
    reason = "Operator cancelled in-progress verification (site inaccessible or abandoned)."
    await update_task_status(task_id, "cancelled_by_operator", decline_reason=reason)
    await update.message.reply_text(
        f"🛑 *CANCELLED Task `{task_id}`*\n\n"
        f"Location: {active_task['location']}\n"
        "Active lock released. Node #001 is now ready for new tasks.",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status to inspect node availability and in-progress tasks."""
    if update.effective_chat.id != TELEGRAM_OPERATOR_CHAT_ID:
        return
    is_avail = await is_operator_available()
    active_task = await get_current_active_task()
    state_str = "🟢 Active (On-Duty)" if is_avail else "⏸️ Paused (Off-Duty)"
    active_str = f"`{active_task['task_id']}` ({active_task['location']})" if active_task else "None"

    await update.message.reply_text(
        f"📊 *Node #001 Operational Status*\n\n"
        f"• *Availability:* {state_str}\n"
        f"• *Active In-Progress Task:* {active_str}\n"
        f"• *Commands:* `/pause`, `/resume`, `/cancel`, `/status`",
        parse_mode="Markdown"
    )

def create_telegram_app() -> Application:
    """Build and configure the python-telegram-bot Application instance."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(handle_button_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_upload))
    return app
