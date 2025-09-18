import os
import logging
import json
import requests
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
    EDIT_POST_CONTENT, ADD_CHANNEL_PROMPT, TEST_CHANNEL_PROMPT = range(20)

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
    'notifications': {'publish': True, 'new_user': True, 'auto_publish': True},
    'linked_channels': {},
    'auto_reply_enabled': False
}
scheduled_post_counter = 0

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
        [InlineKeyboardButton("✏️ تعديل عنوان نص", callback_data='edit_text_title')],
        [InlineKeyboardButton("✏️ تعديل محتوى نص", callback_data='edit_text_content')],
        [InlineKeyboardButton("✏️ تعديل منشور", callback_data='edit_post_prompt')],
        [InlineKeyboardButton("⬅️ رجوع", callback_data='back_to_main')],
    ])

def get_schedule_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ جدولة بعد ساعة", callback_data='schedule_hour')],
        [InlineKeyboardButton("⏰ جدولة بعد يوم", callback_data='schedule_day')],
        [InlineKeyboardButton("⏰ جدولة مخصصة", callback_data='schedule_custom')],
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
                await update.message.reply_text("فشل تثبيت الرسالة، يرجى التأكد من صلاحيات البوت.")
        return MAIN_MENU
    else:
        user_count.add(user.id)
        if update.message:
            await update.message.reply_text(bot_config['welcome_message'])
        return ConversationHandler.END

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == 'back_to_main':
        await query.edit_message_text(
            text="<b>📋 لوحة التحكم الخاصة بالمدير ابو سيف بن ذي يزن </b>",
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return MAIN_MENU
    
    # --- Add again handlers ---
    elif query.data == 'add_text_again':
        await query.edit_message_text("الرجاء إرسال النص الذي تريد إضافته:")
        return ADD_TEXT
    elif query.data == 'add_post_again':
        await query.edit_message_text("الرجاء إرسال المنشور (صورة، فيديو، نص) الذي تريد إضافته:")
        return ADD_POST
    
    # --- Main Menu Handlers ---
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
        except Exception as e:
            await query.edit_message_text(f"حدث خطأ أثناء النشر: {e}")
            LOGGER.error(f"Publish now error: {e}")

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

    # --- Edit Menu Logic ---
    elif query.data == 'edit_text_content':
        await query.edit_message_text("الرجاء إرسال معرف النص الذي تريد تعديل محتواه:")
        return EDIT_CONTENT_PROMPT
    
    # --- Schedule Menu Logic ---
    elif query.data == 'schedule_hour':
        await query.edit_message_text("✅ تم جدولة النشر بعد ساعة من الآن.")
        
    elif query.data == 'schedule_day':
        await query.edit_message_text("✅ تم جدولة النشر بعد يوم من الآن.")

    elif query.data == 'schedule_custom':
        await query.edit_message_text("الرجاء إرسال الوقت المخصص للجدولة (مثال: 2024-12-31 23:59):")
        return SCHEDULE_CUSTOM_PROMPT

    # --- Settings Menu Logic ---
    elif query.data == 'toggle_protection':
        bot_config['protection_enabled'] = not bot_config['protection_enabled']
        await query.edit_message_text(f"حماية البوت الآن: {'✅ مفعل' if bot_config['protection_enabled'] else '❌ غير مفعل'}", reply_markup=get_settings_menu_keyboard())
    elif query.data == 'toggle_auto_reply':
        bot_config['auto_reply_enabled'] = not bot_config['auto_reply_enabled']
        await query.edit_message_text(f"الرد التلقائي الآن: {'✅ مفعل' if bot_config['auto_reply_enabled'] else '❌ غير مفعل'}", reply_markup=get_settings_menu_keyboard())
    elif query.data == 'clear_users_cache':
        user_data.clear()
        await query.edit_message_text("✅ تم مسح الذاكرة المؤقتة لجميع المستخدمين.", reply_markup=get_settings_menu_keyboard())
    elif query.data == 'clear_user_cache_prompt':
        await query.edit_message_text("الرجاء إرسال معرف المستخدم الذي تريد مسح بياناته:")
        return CLEAR_USER_PROMPT
    
    return MAIN_MENU

# --- Message handlers ---
async def add_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text_content = update.message.text
    text_id = len(texts) + 1
    texts[text_id] = text_content
    await update.message.reply_text(f"✅ تم حفظ النص بنجاح برقم: {text_id}")
    await update.message.reply_text("هل تريد إضافة نص آخر؟", reply_markup=get_add_again_keyboard('text'))
    return MAIN_MENU

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
    return MAIN_MENU

async def edit_content_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        text_id = int(update.message.text)
        if text_id in texts:
            context.user_data['edit_id'] = text_id
            await update.message.reply_text(f"أرسل المحتوى الجديد للنص رقم {text_id}:")
            return EDIT_CONTENT_PROMPT
        else:
            await update.message.reply_text("المعرف غير موجود. الرجاء إرسال معرف صالح.")
            return EDIT_CONTENT_PROMPT
    except ValueError:
        await update.message.reply_text("الرجاء إرسال رقم المعرف فقط.")
        return EDIT_CONTENT_PROMPT
    
async def update_content_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text_id = context.user_data.get('edit_id')
    if text_id:
        texts[text_id] = update.message.text
        await update.message.reply_text(f"✅ تم تحديث محتوى النص رقم {text_id}.")
        del context.user_data['edit_id']
    else:
        await update.message.reply_text("حدث خطأ. الرجاء المحاولة مرة أخرى من القائمة الرئيسية.")
    return MAIN_MENU

async def clear_user_cache_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user_to_clear = int(update.message.text)
        if user_to_clear in user_data:
            del user_data[user_to_clear]
            await update.message.reply_text(f"✅ تم مسح الذاكرة المؤقتة للمستخدم {user_to_clear}.", reply_markup=get_settings_menu_keyboard())
        else:
            await update.message.reply_text("المستخدم غير موجود في الذاكرة المؤقتة.", reply_markup=get_settings_menu_keyboard())
    except ValueError:
        await update.message.reply_text("الرجاء إرسال رقم المعرف فقط.", reply_markup=get_settings_menu_keyboard())
    return MAIN_MENU

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_count.add(user_id)

    if bot_config['auto_reply_enabled']:
        query = update.message.text
        if not GEMINI_API_KEY:
            await update.message.reply_text("عذراً، وظيفة الرد التلقائي غير مفعلة. يرجى إخبار المدير بتعيين مفتاح API.")
            return
        
        API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [
                {
                    "parts": [{"text": query}]
                }
            ],
            "tools": [{"google_search": {}}]
        }

        try:
            response = requests.post(API_URL, json=payload)
            response.raise_for_status()
            result = response.json()
            if result.get("candidates") and result["candidates"][0].get("content"):
                ai_response = result["candidates"][0]["content"]["parts"][0]["text"]
                await update.message.reply_text(ai_response)
            else:
                await update.message.reply_text("عذراً، لم أتمكن من إنشاء رد تلقائي الآن. يرجى المحاولة لاحقاً.")
        except Exception as e:
            await update.message.reply_text("حدث خطأ أثناء معالجة طلبك.")
    else:
        await update.message.reply_text(bot_config['welcome_message'])

async def handle_user_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_count.add(user_id)
    await update.message.reply_text(bot_config['media_rejection_message'])

def main() -> None:
    if not TELEGRAM_BOT_TOKEN or not MANAGER_ID:
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            MAIN_MENU: [CallbackQueryHandler(handle_callback)],
            ADD_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_text_handler)],
            ADD_POST: [MessageHandler(filters.ALL & ~filters.COMMAND, add_post_handler)],
            EDIT_MENU: [CallbackQueryHandler(handle_callback)],
            SCHEDULE_MENU: [CallbackQueryHandler(handle_callback)],
            SETTINGS_MENU: [CallbackQueryHandler(handle_callback)],
            EDIT_CONTENT_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_content_handler)],
            CLEAR_USER_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, clear_user_cache_handler)],
        },
        fallbacks=[CommandHandler("start", start_command)],
    )

    application.add_handler(conv_handler)
    
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
