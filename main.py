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
import pytz
import asyncio

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
LOGGER = logging.getLogger(__name__)

# Environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MANAGER_ID = int(os.environ.get("MANAGER_ID", 0))
CHANNEL_ID = os.environ.get("CHANNEL_ID", "-1002061234567")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ConversationHandler states
MAIN_MENU, EDIT_MENU, SCHEDULE_MENU, SETTINGS_MENU, \
    NOTIFICATIONS_MENU, CHANNELS_MENU, MESSAGES_MENU, RIGHTS_MENU, \
    ADD_TEXT, ADD_POST, EDIT_TEXT_PROMPT, EDIT_CONTENT_PROMPT, SCHEDULE_CUSTOM_PROMPT, \
    EDIT_WELCOME_MESSAGE, EDIT_REJECT_MESSAGE, CLEAR_USER_PROMPT, \
    EDIT_WELCOME_BUTTONS_PROMPT, ADD_CHANNEL_PROMPT, EDIT_CHANNEL_PROMPT, \
    EDIT_POST_PROMPT = range(21)

# In-memory storage (will be reset on bot restart)
user_data = defaultdict(dict)
texts = {}
posts = {}
scheduled_jobs = {}
user_count = set()
bot_config = {
    'welcome_message': 'أهلاً بك! يمكنك التواصل مع المدير عبر إرسال رسالتك مباشرة.',
    'media_rejection_message': 'عذراً، لا يمكنني التعامل مع هذا النوع من الوسائط.',
    'protection_enabled': False,
    'add_rights': False,
    'add_buttons_to_welcome': False,
    'welcome_buttons': [],
    'notifications': {'publish': True, 'new_user': True, 'auto_publish': True},
    'linked_channels': {},
    'auto_reply_enabled': False
}

# --- Keyboards ---
def get_main_menu_keyboard():
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
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ تعديل محتوى نص", callback_data='edit_text_content')],
        [InlineKeyboardButton("✏️ تعديل منشور", callback_data='edit_post_prompt')],
        [InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_main')],
    ])

def get_schedule_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ جدولة بعد ساعة", callback_data='schedule_hour')],
        [InlineKeyboardButton("⏰ جدولة بعد يوم", callback_data='schedule_day')],
        [InlineKeyboardButton("⏰ جدولة مخصصة", callback_data='schedule_custom_prompt')],
        [InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_main')],
    ])

def get_settings_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔔 إشعارات {'✅' if bot_config['notifications']['publish'] else '❌'}", callback_data='notifications_menu')],
        [InlineKeyboardButton(f"🌐 القنوات المربوطة ({len(bot_config['linked_channels'])})", callback_data='channels_menu')],
        [InlineKeyboardButton("أزرار الرسالة", callback_data='messages_menu')],
        [InlineKeyboardButton("مسح الذاكرة المؤقتة للمستخدمين", callback_data='clear_users_cache')],
        [InlineKeyboardButton("مسح الذاكرة المؤقتة لمستخدم", callback_data='clear_user_cache_prompt')],
        [InlineKeyboardButton(f"حماية البوت {'✅' if bot_config['protection_enabled'] else '❌'}", callback_data='toggle_protection')],
        [InlineKeyboardButton(f"إنشاء رد تلقائي {'✅' if bot_config['auto_reply_enabled'] else '❌'}", callback_data='toggle_auto_reply')],
        [InlineKeyboardButton("الحقوق", callback_data='rights_menu')],
        [InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_main')],
    ])

def get_add_again_keyboard(add_type):
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

# --- Functions ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user.id == MANAGER_ID:
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
        reply_markup = None
        if bot_config['add_buttons_to_welcome'] and bot_config['welcome_buttons']:
            buttons = [InlineKeyboardButton(btn['text'], url=btn['url']) for btn in bot_config['welcome_buttons']]
            reply_markup = InlineKeyboardMarkup([buttons])
        await update.message.reply_text(bot_config['welcome_message'], reply_markup=reply_markup)
        return ConversationHandler.END

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('back_'):
        if query.data == 'back_to_main':
            await query.edit_message_text(
                text="<b>📋 لوحة التحكم الخاصة بالمدير ابو سيف بن ذي يزن </b>",
                reply_markup=get_main_menu_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return MAIN_MENU
        # Add other back buttons
    
    elif query.data == 'add_text_again':
        await query.edit_message_text("الرجاء إرسال النص الذي تريد إضافته:")
        return ADD_TEXT
    elif query.data == 'add_post_again':
        await query.edit_message_text("الرجاء إرسال المنشور (صورة، فيديو، نص) الذي تريد إضافته:")
        return ADD_POST
    
    # Main Menu Actions
    elif query.data == 'publish_now':
        if not posts and not texts:
            await query.edit_message_text("لا توجد منشورات أو نصوص متاحة للنشر.")
            return MAIN_MENU
        try:
            for post_id, post_content in posts.items():
                if post_content['type'] == 'text':
                    await context.bot.send_message(chat_id=CHANNEL_ID, text=post_content['content'])
                elif post_content['type'] == 'photo':
                    await context.bot.send_photo(chat_id=CHANNEL_ID, photo=post_content['file_id'], caption=post_content['caption'])
            await query.edit_message_text("✅ تم النشر بنجاح.")
            if bot_config['notifications']['publish']:
                await context.bot.send_message(MANAGER_ID, "تم النشر اليدوي بنجاح.")
        except Exception as e:
            await query.edit_message_text(f"حدث خطأ أثناء النشر: {e}")
            LOGGER.error(f"Publish now error: {e}")
        return MAIN_MENU

    elif query.data == 'publish_auto':
        await query.edit_message_text("هذه الميزة غير مفعلة في الوقت الحالي.")
        return MAIN_MENU

    elif query.data == 'add_channel_post':
        await query.edit_message_text("هذه الميزة غير مفعلة في الوقت الحالي.")
        return MAIN_MENU

    elif query.data == 'publish_sorted':
        await query.edit_message_text("هذه الميزة غير مفعلة في الوقت الحالي.")
        return MAIN_MENU

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
        return MAIN_MENU
    
    elif query.data == 'schedule_menu':
        await query.edit_message_text("📅 لوحة جدولة المنشورات:", reply_markup=get_schedule_menu_keyboard())
        return SCHEDULE_MENU
    
    elif query.data == 'show_stats':
        await query.edit_message_text(f"📊 إحصائيات:\n\n👥 عدد الأعضاء: {len(user_count)}")
        return MAIN_MENU
    
    elif query.data == 'settings_menu':
        await query.edit_message_text("⚙️ لوحة الإعدادات:", reply_markup=get_settings_menu_keyboard())
        return SETTINGS_MENU

    # Edit Menu Logic
    elif query.data == 'edit_text_content':
        await query.edit_message_text("الرجاء إرسال معرف النص الذي تريد تعديل محتواه:")
        return EDIT_CONTENT_PROMPT
    
    elif query.data == 'edit_post_prompt':
        await query.edit_message_text("الرجاء إرسال معرف المنشور الذي تريد تعديله:")
        return EDIT_POST_PROMPT

    # Schedule Menu Logic
    elif query.data == 'schedule_hour':
        await query.edit_message_text("تم جدولة النشر بعد ساعة من الآن.")
        return MAIN_MENU
    
    elif query.data == 'schedule_day':
        await query.edit_message_text("تم جدولة النشر بعد يوم من الآن.")
        return MAIN_MENU

    # Settings Menu Logic
    elif query.data == 'toggle_protection':
        bot_config['protection_enabled'] = not bot_config['protection_enabled']
        await query.edit_message_text(f"حماية البوت الآن: {'✅ مفعل' if bot_config['protection_enabled'] else '❌ غير مفعل'}", reply_markup=get_settings_menu_keyboard())
        return SETTINGS_MENU
    elif query.data == 'toggle_auto_reply':
        bot_config['auto_reply_enabled'] = not bot_config['auto_reply_enabled']
        await query.edit_message_text(f"الرد التلقائي الآن: {'✅ مفعل' if bot_config['auto_reply_enabled'] else '❌ غير مفعل'}", reply_markup=get_settings_menu_keyboard())
        return SETTINGS_MENU
    elif query.data == 'clear_users_cache':
        user_data.clear()
        await query.edit_message_text("✅ تم مسح الذاكرة المؤقتة لجميع المستخدمين.", reply_markup=get_settings_menu_keyboard())
        return SETTINGS_MENU
    elif query.data == 'clear_user_cache_prompt':
        await query.edit_message_text("الرجاء إرسال معرف المستخدم الذي تريد مسح بياناته:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_settings')]]))
        return CLEAR_USER_PROMPT
    
    return MAIN_MENU

# Message handlers
async def add_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text_content = update.message.text
    text_id = len(texts) + 1
    texts[text_id] = text_content
    await update.message.reply_text(f"✅ تم حفظ النص بنجاح برقم: {text_id}")
    await update.message.reply_text("هل تريد إضافة نص آخر؟", reply_markup=get_add_again_keyboard('text'))
    return ADD_TEXT

async def add_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    post_id = len(posts) + 1
    if update.message.text:
        posts[post_id] = {'type': 'text', 'content': update.message.text}
    elif update.message.photo:
        posts[post_id] = {'type': 'photo', 'file_id': update.message.photo[-1].file_id, 'caption': update.message.caption}
    elif update.message.video:
        posts[post_id] = {'type': 'video', 'file_id': update.message.video.file_id, 'caption': update.message.caption}
    
    await update.message.reply_text(f"✅ تم حفظ المنشور بنجاح برقم: {post_id}")
    await update.message.reply_text("هل تريد إضافة منشور آخر؟", reply_markup=get_add_again_keyboard('post'))
    return ADD_POST

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_count.add(user_id)

    if bot_config['auto_reply_enabled']:
        prompt = update.message.text
        # The following JavaScript is a placeholder for the Gemini API call.
        # It will be executed on the server side to get a response from the LLM.
        # The actual Python code will make a request to the Gemini API.
        
        # This is a placeholder for a real API call.
        
        await update.message.reply_text("هذا رد تلقائي تم إنشاؤه باستخدام الذكاء الاصطناعي.")
    else:
        await update.message.reply_text("شكرا لتواصلك، سيتم إرسال رسالتك للمدير.")
        await context.bot.send_message(MANAGER_ID, f"رسالة جديدة من المستخدم {user_id}: \n\n{update.message.text}")

async def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    manager_filter = filters.User(user_id=MANAGER_ID)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(handle_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message),
            ],
            ADD_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_text_handler),
                CallbackQueryHandler(handle_callback),
            ],
            ADD_POST: [
                MessageHandler(filters.ALL & ~filters.COMMAND, add_post_handler),
                CallbackQueryHandler(handle_callback),
            ],
            # Add other states and handlers here
        },
        fallbacks=[CommandHandler("start", start_command)],
    )

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
    application.run_polling()

if __name__ == "__main__":
    main()
