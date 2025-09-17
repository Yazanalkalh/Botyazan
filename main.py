import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)
from collections import defaultdict
import datetime

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

LOGGER = logging.getLogger(__name__)

# Environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MANAGER_ID = int(os.environ.get("MANAGER_ID", 0))
CHANNEL_ID = os.environ.get("CHANNEL_ID", "-1002061234567")

# States for ConversationHandler
MAIN_MENU, EDIT_MENU, SCHEDULE_MENU, SETTINGS_MENU, \
    NOTIFICATIONS_MENU, CHANNELS_MENU, MESSAGES_MENU, RIGHTS_MENU, \
    ADD_TEXT, ADD_POST, EDIT_TITLE, EDIT_CONTENT, SCHEDULE_CUSTOM = range(13)

# In-memory storage (will be reset on bot restart)
user_data = defaultdict(dict)
texts = {}
posts = {}
scheduled_jobs = {}
user_count = set()
bot_config = {
    'welcome_message': 'أهلاً بك في البوت! يمكنك التواصل مع المدير عبر إرسال رسالتك مباشرة.',
    'media_rejection_message': 'عذراً، لا يمكنني التعامل مع هذا النوع من الوسائط.',
    'protection_enabled': False,
    'add_rights': False,
    'add_buttons_to_welcome': False,
    'notifications': {'publish': False, 'new_user': False, 'auto_publish': False},
    'linked_channels': {}
}

def get_main_menu_keyboard():
    """Generates the main menu keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 نشر الآن", callback_data='publish_now'),
         InlineKeyboardButton("نشر تلقائي", callback_data='publish_auto')],
        [InlineKeyboardButton("إضافة منشور للقناة", callback_data='add_channel_post')],
        [InlineKeyboardButton("نشر المنشورات مرتبة", callback_data='publish_sorted')],
        [InlineKeyboardButton("إضافة نص", callback_data='add_text'),
         InlineKeyboardButton("إضافة منشور", callback_data='add_post')],
        [InlineKeyboardButton("📝 تعديل", callback_data='edit_menu'),
         InlineKeyboardButton("❌ حذف", callback_data='delete_data')],
        [InlineKeyboardButton("📅 جدولة منشور للقناة", callback_data='schedule_menu')],
        [InlineKeyboardButton("📊 إحصائيات", callback_data='show_stats')],
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data='settings_menu')],
    ])

def get_edit_menu_keyboard():
    """Generates the edit sub-menu keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ تعديل عنوان نص", callback_data='edit_text_title')],
        [InlineKeyboardButton("✏️ تعديل محتوى نص", callback_data='edit_text_content')],
        [InlineKeyboardButton("✏️ تعديل منشور", callback_data='edit_post')],
        [InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_main')],
    ])

def get_schedule_menu_keyboard():
    """Generates the schedule sub-menu keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ جدولة بعد ساعة", callback_data='schedule_hour')],
        [InlineKeyboardButton("⏰ جدولة بعد يوم", callback_data='schedule_day')],
        [InlineKeyboardButton("⏰ جدولة مخصصة", callback_data='schedule_custom')],
        [InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_main')],
    ])

def get_settings_menu_keyboard():
    """Generates the settings sub-menu keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 إشعارات", callback_data='notifications_menu')],
        [InlineKeyboardButton("🌐 القنوات المربوطة", callback_data='channels_menu')],
        [InlineKeyboardButton("أزرار الرسالة", callback_data='messages_menu')],
        [InlineKeyboardButton("مسح الذاكرة المؤقتة للمستخدمين", callback_data='clear_users_cache')],
        [InlineKeyboardButton("مسح الذاكرة المؤقتة لمستخدم", callback_data='clear_user_cache')],
        [InlineKeyboardButton("الحقوق", callback_data='rights_menu')],
        [InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_main')],
    ])

def get_add_again_keyboard(add_type):
    """Generates the 'add again' and 'back' keyboard."""
    if add_type == 'text':
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("إضافة نص مرة ثانية", callback_data='add_text_again')],
            [InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_main')]
        ])
    elif add_type == 'post':
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("إضافة منشور مرة ثانية", callback_data='add_post_again')],
            [InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_main')]
        ])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for the bot, displays main menu and pins the message."""
    user = update.effective_user
    if user.id == MANAGER_ID:
        if update.message:
            message = await update.message.reply_html(
                "<b>📋 لوحة التحكم الخاصة بالمدير ابو سيف بن ذي يزن </b>",
                reply_markup=get_main_menu_keyboard()
            )
            try:
                await context.bot.pin_chat_message(
                    chat_id=update.effective_chat.id,
                    message_id=message.message_id,
                    disable_notification=True
                )
            except Exception as e:
                LOGGER.error(f"Failed to pin message: {e}")
                await update.message.reply_text("فشل تثبيت الرسالة، يرجى التأكد من صلاحيات البوت.")
        return MAIN_MENU
    else:
        user_count.add(user.id)
        if update.message:
            await update.message.reply_text(bot_config['welcome_message'])
        return ConversationHandler.END

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles callback queries from InlineKeyboard buttons."""
    query = update.callback_query
    await query.answer()
    
    # Back button logic
    if query.data == 'back_to_main':
        await query.edit_message_text(
            text="<b>📋 لوحة التحكم الخاصة بالمدير ابو سيف بن ذي يزن </b>",
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return MAIN_MENU
    
    # "Add again" logic
    elif query.data == 'add_text_again':
        await query.edit_message_text("الرجاء إرسال النص الذي تريد إضافته:")
        return ADD_TEXT
    elif query.data == 'add_post_again':
        await query.edit_message_text("الرجاء إرسال المنشور (صورة، فيديو، نص) الذي تريد إضافته:")
        return ADD_POST
    
    # --- Main Menu Buttons Logic ---
    if query.data == 'publish_now':
        await query.edit_message_text("✅ تم النشر بنجاح.")
    elif query.data == 'add_text':
        await query.edit_message_text("الرجاء إرسال النص الذي تريد إضافته:")
        return ADD_TEXT
    elif query.data == 'add_post':
        await query.edit_message_text("الرجاء إرسال المنشور (صورة، فيديو، نص) الذي تريد إضافته:")
        return ADD_POST
    elif query.data == 'edit_menu':
        await query.edit_message_text("📝 لوحة تعديل النصوص والمنشورات:", reply_markup=get_edit_menu_keyboard())
        return EDIT_MENU
    elif query.data == 'delete_data':
        texts.clear()
        posts.clear()
        await query.edit_message_text("❌ تم حذف جميع النصوص والمنشورات المؤقتة.")
    elif query.data == 'schedule_menu':
        await query.edit_message_text("📅 لوحة جدولة المنشورات:", reply_markup=get_schedule_menu_keyboard())
        return SCHEDULE_MENU
    elif query.data == 'show_stats':
        await query.edit_message_text(f"📊 إحصائيات:\n\n👥 عدد الأعضاء: {len(user_count)}")
    elif query.data == 'settings_menu':
        await query.edit_message_text("⚙️ لوحة الإعدادات:", reply_markup=get_settings_menu_keyboard())
        return SETTINGS_MENU

    return MAIN_MENU

async def add_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles adding a text from the manager."""
    text_content = update.message.text
    text_id = len(texts) + 1
    texts[text_id] = text_content
    await update.message.reply_text(f"✅ تم حفظ النص بنجاح برقم: {text_id}")
    await update.message.reply_text("هل تريد إضافة نص آخر؟", reply_markup=get_add_again_keyboard('text'))
    return MAIN_MENU

async def add_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles adding a post (text, photo, etc.) from the manager."""
    post_id = len(posts) + 1
    if update.message.text:
        posts[post_id] = {'type': 'text', 'content': update.message.text}
    elif update.message.photo:
        posts[post_id] = {'type': 'photo', 'file_id': update.message.photo[-1].file_id, 'caption': update.message.caption}
    elif update.message.video:
        posts[post_id] = {'type': 'video', 'file_id': update.message.video.file_id, 'caption': update.message.caption}
    
    await update.message.reply_text(f"✅ تم حفظ المنشور بنجاح برقم: {post_id}")
    await update.message.reply_text("هل تريد إضافة منشور آخر؟", reply_markup=get_add_again_keyboard('post'))
    return MAIN_MENU

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles messages from regular users."""
    user_id = update.effective_user.id
    user_count.add(user_id)
    await update.message.reply_text(bot_config['welcome_message'])

async def handle_user_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles media messages from regular users."""
    user_id = update.effective_user.id
    user_count.add(user_id)
    await update.message.reply_text(bot_config['media_rejection_message'])


def main() -> None:
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN or not MANAGER_ID:
        LOGGER.error("TELEGRAM_BOT_TOKEN or MANAGER_ID environment variable is not set.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Conversation handler for manager's menu
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            MAIN_MENU: [CallbackQueryHandler(handle_callback)],
            ADD_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_text)],
            ADD_POST: [MessageHandler(filters.ALL & ~filters.COMMAND, add_post)],
            EDIT_MENU: [CallbackQueryHandler(handle_callback, pattern='^back_to_main$')],
            SCHEDULE_MENU: [CallbackQueryHandler(handle_callback, pattern='^back_to_main$')],
            SETTINGS_MENU: [CallbackQueryHandler(handle_callback, pattern='^back_to_main$')],
        },
        fallbacks=[CommandHandler("start", start_command)],
    )

    application.add_handler(conv_handler)
    
    # Message handlers for regular users
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.User(user_id=~MANAGER_ID),
        handle_user_message
    ))
    application.add_handler(MessageHandler(
        (filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.ATTACHMENT) & filters.User(user_id=~MANAGER_ID),
        handle_user_media
    ))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

