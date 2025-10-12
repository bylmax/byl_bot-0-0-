# bot_video_manager.py
import os
import sqlite3
import logging
import sys
import time

import telebot
from telebot import types, apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import random

# ---------------- Config / Logging ----------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# توکن ربات برای اتصال به API تلگرام
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")
CHANNEL_ID = "-1002984288636"
CHANNEL_LINK = "https://t.me/channelforfrinds"

bot = telebot.TeleBot(API_TOKEN)

# لیست دسته‌بندی‌های ثابت برای ویدیوها - برای جلوگیری از تزریق کد و حفظ ساختار مشخص
CATEGORIES = [
    "mylf", "step sis", "step mom", "work out", "russian",
    "big ass", "big tits", "free us", "Sweetie Fox R", "foot fetish", "arab", "asian", "anal", "BBC", "None"
]

# دیکشنری‌های موقت برای مدیریت وضعیت کاربران - جایگزین دیتابیس برای داده‌های موقت
user_categories = {}  # ذخیره دسته‌بندی انتخاب شده هر کاربر
user_pagination = {}  # مدیریت صفحه‌بندی نتایج برای هر کاربر
user_lucky_search = {}  # ذخیره نتایج جستجوی شانسی کاربر


# ---------- Database ----------
def create_connection():
    # مسیر دیتابیس از متغیر محیطی خوانده می‌شود یا از فایل محلی استفاده می‌کند
    db_path = os.getenv("BOT_DB_PATH", "videos.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return conn


def create_table():
    conn = create_connection()
    cursor = conn.cursor()
    # ایجاد لیست دسته‌بندی‌ها برای constraint در دیتابیس
    cat_list_sql = ",".join([f"'{c}'" for c in CATEGORIES])
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS videos
        (
            video_id TEXT PRIMARY KEY,
            user_id INTEGER,
            category TEXT CHECK(category IN ({cat_list_sql})),
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


# ---------- Helpers for callback-safe category codes ----------
def encode_category_for_callback(cat_text: str) -> str:
    # حذف فاصله‌ها برای ایجاد رشته ایمن در callback
    return cat_text.replace(" ", "")


def decode_category_from_callback(cat_code: str) -> str:
    # اضافه کردن فاصله بعد از "cat" برای بازیابی فرمت اصلی (نگهداری سازگاری با نسخه‌ی قبلی)
    if cat_code.startswith("cat") and len(cat_code) > 3:
        return cat_code[:3] + " " + cat_code[3:]
    return cat_code


# ---------- Channel join helpers ----------
def is_member(user_id):
    """
    بررسی میکند که کاربر در کانال عضو هست یا نه
    بازگردانی True در صورت عضویت (creator, administrator, member)
    """
    try:
        user_info = bot.get_chat_member(CHANNEL_ID, user_id)
        return user_info.status in ['creator', 'administrator', 'member']
    except Exception as e:
        logger.error(f"Error checking membership for user {user_id}: {e}")
        return False


def create_join_channel_keyboard():
    """
    ایجاد کیبورد اینلاین برای دعوت به کانال
    """
    markup = InlineKeyboardMarkup(row_width=1)
    join_button = InlineKeyboardButton(
        '📢 عضویت در کانال',
        url=CHANNEL_LINK
    )
    check_button = InlineKeyboardButton(
        '✅ بررسی عضویت',
        callback_data='check_membership'
    )
    markup.add(join_button, check_button)
    return markup


# ---------- Start / Home ----------
@bot.message_handler(commands=['start'])
def start_handler(message):
    """
    هندلر استارت یکپارچه: اگر عضو کانال نیست، کیبورد عضویت نشان می‌دهد،
    در غیر این صورت منوی اصلی (همان send_welcome) را نمایش می‌دهد.
    """
    user_id = message.from_user.id

    if not is_member(user_id):
        bot.send_message(
            message.chat.id,
            '👋 سلام!\n\n'
            'برای استفاده از ربات، لطفاً در کانال ما عضو شوید:\n'
            'پس از عضویت، دکمه "بررسی عضویت" را بزنید.',
            reply_markup=create_join_channel_keyboard()
        )
        return

    # اگر کاربر عضو است: نمایش منوی اصلی
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('تماشای فیلم ها 🎥', '🎲 تماشای شانسی', '/home 🏠')
    bot.send_message(message.chat.id, "سلام 👋\nبه ربات بهشتی موویس خوش اومدی ", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == 'check_membership')
def check_membership_callback(call):
    """
    هندلر بررسی عضویت از طریق دکمه اینلاین
    """
    user_id = call.from_user.id

    if is_member(user_id):
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=(
                    '🎉 عالی!\n\n'
                    '✅ عضویت شما تأیید شد.\n'
                    'اکنون میتوانید از امکانات ربات استفاده کنید.'
                )
            )
        except Exception as e:
            # ممکن است پیام قبلاً ویرایش یا پاک شده باشد
            logger.warning(f"Couldn't edit message for membership check: {e}")

        # ارسال پیام خوش آمدگویی جدید
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('تماشای فیلم ها 🎥', '🎲 تماشای شانسی', '/home 🏠')
        bot.send_message(
            call.message.chat.id,
            'خوش آمدید! از امکانات ربات لذت ببرید. 😊',
            reply_markup=markup
        )
    else:
        bot.answer_callback_query(
            call.id,
            '❌ هنوز در کانال عضو نشدید! لطفاً ابتدا عضو شوید.',
            show_alert=True
        )


@bot.message_handler(commands=['home', 'home 🏠'])
def home(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('تماشای فیلم ها 🎥', '🎲 تماشای شانسی', '/home 🏠')
    bot.send_message(message.chat.id, "به خانه خوش آمدید", reply_markup=markup)


def home_from_id(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('تماشای فیلم ها 🎥', '🎲 تماشای شانسی', '/home 🏠')
    bot.send_message(chat_id, "به خانه خوش آمدید", reply_markup=markup)


# ---------- Lucky (random) ----------
@bot.message_handler(func=lambda message: message.text == '🎲 تماشای شانسی')
def lucky_search(message):
    user_id = message.from_user.id
    if not is_member(user_id):
        bot.send_message(
            message.chat.id,
            '⚠️ برای استفاده از این قابلیت باید در کانال عضو باشید.',
            reply_markup=create_join_channel_keyboard()
        )
        return

    random_videos = get_random_videos(5)  # دریافت ۵ ویدیوی تصادفی
    if not random_videos:
        bot.reply_to(message, "❌ هنوز هیچ ویدیویی در سیستم وجود ندارد!")
        return

    # ذخیره وضعیت جستجوی شانسی کاربر
    user_lucky_search[user_id] = {'current_videos': random_videos, 'message_ids': []}

    # ارسال ویدیوهای تصادفی به کاربر
    for i, video in enumerate(random_videos):
        try:
            sent_msg = bot.send_video(message.chat.id, video[0], caption=f"ویدیو شانسی {i + 1}")
            user_lucky_search[user_id]['message_ids'].append(sent_msg.message_id)
        except Exception as e:
            logger.error(f"خطا در ارسال ویدیو: {e}")

    # دکمه برای درخواست ویدیوهای تصادفی جدید
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎲 شانس مجدد", callback_data="lucky_again"))
    sent_msg = bot.send_message(message.chat.id, "۵ ویدیوی تصادفی برای شما نمایش داده شد!", reply_markup=markup)
    user_lucky_search[user_id]['message_ids'].append(sent_msg.message_id)


@bot.callback_query_handler(func=lambda call: call.data == "lucky_again")
def handle_lucky_again(call):
    user_id = call.from_user.id
    if not is_member(user_id):
        bot.answer_callback_query(call.id, "⚠️ باید ابتدا در کانال عضو شوید.", show_alert=True)
        return

    # حذف پیام‌های قبلی
    if user_id in user_lucky_search:
        for msg_id in user_lucky_search[user_id]['message_ids']:
            try:
                bot.delete_message(call.message.chat.id, msg_id)
            except Exception as e:
                logger.debug(f"خطا در حذف پیام: {e}")

    # دریافت ویدیوهای تصادفی جدید
    random_videos = get_random_videos(5)
    if not random_videos:
        bot.answer_callback_query(call.id, "❌ هیچ ویدیویی در سیستم وجود ندارد!")
        return

    # ذخیره وضعیت جدید و ارسال ویدیوها
    user_lucky_search[user_id] = {'current_videos': random_videos, 'message_ids': []}
    for i, video in enumerate(random_videos):
        try:
            sent_msg = bot.send_video(call.message.chat.id, video[0], caption=f"ویدیو شانسی {i + 1}")
            user_lucky_search[user_id]['message_ids'].append(sent_msg.message_id)
        except Exception as e:
            logger.error(f"خطا در ارسال ویدیو: {e}")

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎲 شانس مجدد", callback_data="lucky_again"))
    sent_msg = bot.send_message(call.message.chat.id, "۵ ویدیوی تصادفی جدید برای شما نمایش داده شد!",
                                reply_markup=markup)
    user_lucky_search[user_id]['message_ids'].append(sent_msg.message_id)
    bot.answer_callback_query(call.id)


def get_random_videos(limit=5):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT video_id FROM videos ORDER BY RANDOM() LIMIT ?', (limit,))
    videos = cursor.fetchall()
    conn.close()
    return videos


# ---------- Upload flow ----------
@bot.message_handler(func=lambda message: message.text == '📤 ارسال ویدیو')
def request_video(message):
    user_id = message.from_user.id
    if not is_member(user_id):
        bot.send_message(
            message.chat.id,
            '⚠️ برای ارسال ویدیو باید در کانال عضو باشید.',
            reply_markup=create_join_channel_keyboard()
        )
        return

    if user_id in user_categories:
        category = user_categories[user_id]
        bot.reply_to(message, f"دسته‌بندی فعلی: {category}. لطفاً ویدیوی خود را ارسال کنید:")
    else:
        show_category_selection(message)  # اگر دسته‌بندی انتخاب نشده


@bot.message_handler(func=lambda message: message.text == '🔄 تغییر دسته‌بندی')
def change_category(message):
    show_category_selection(message)


def show_category_selection(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(*CATEGORIES)  # اضافه کردن تمام دسته‌بندی‌ها به کیبورد
    markup.add('/home')
    msg = bot.reply_to(message, "لطفاً دسته‌بندی ویدیو را انتخاب کنید:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_category_selection)  # ثبت هندلر مرحله بعد


def process_category_selection(message):
    if message.text == '/home':
        home(message)
        return

    chosen = message.text
    if chosen in CATEGORIES:
        user_categories[message.from_user.id] = chosen  # ذخیره در حافظه موقت
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('🔄 تغییر دسته‌بندی', '/home 🏠')
        bot.send_message(message.chat.id,
                         f"✅ دسته‌بندی {chosen} انتخاب شد. اکنون می‌توانید ویدیوهای خود را ارسال کنید.",
                         reply_markup=markup)
    else:
        bot.reply_to(message, "❌ دسته‌بندی نامعتبر است. لطفاً یکی از گزینه‌های موجود را انتخاب کنید:")
        show_category_selection(message)  # نمایش مجدد در صورت انتخاب نامعتبر


# ---------- Viewing videos (with pagination) ----------
@bot.message_handler(func=lambda message: message.text == 'تماشای فیلم ها 🎥')
def show_my_videos(message):
    user_id = message.from_user.id
    if not is_member(user_id):
        bot.send_message(
            message.chat.id,
            '⚠️ برای مشاهده ویدیوها باید در کانال عضو باشید.',
            reply_markup=create_join_channel_keyboard()
        )
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(*CATEGORIES)
    markup.add('📋 همه ویدیوها', '/home')
    msg = bot.reply_to(message, "لطفاً دسته‌بندی مورد نظر برای مشاهده ویدیوها را انتخاب کنید:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_category_for_viewing)


def process_category_for_viewing(message):
    if message.text == '/home':
        home(message)
        return

    user_id = message.from_user.id
    user_pagination[user_id] = {'page': 0, 'category': None, 'all_videos': False}  # مقداردهی اولیه صفحه‌بندی

    if message.text == '📋 همه ویدیوها':
        user_pagination[user_id]['all_videos'] = True
        videos = get_user_videos(user_id)
        if videos:
            send_videos_paginated(user_id, message.chat.id, videos, page=0, page_size=10)  # نمایش ۱۰ تایی
        else:
            bot.reply_to(message, "❌ هنوز ویدیویی ارسال نکرده‌اید")
            home(message)
    else:
        chosen = message.text
        if chosen in CATEGORIES:
            user_pagination[user_id]['category'] = chosen
            videos = get_user_videos_by_category(user_id, chosen)
            if videos:
                send_videos_paginated(user_id, message.chat.id, videos, page=0, page_size=3,
                                      category=chosen)  # نمایش ۳ تایی
            else:
                bot.reply_to(message, f"❌ ویدیویی در دسته‌بندی {chosen} ندارید")
                home(message)
        else:
            bot.reply_to(message, "❌ لطفاً یکی از دسته‌بندی‌های موجود را انتخاب کنید:")
            show_my_videos(message)


def send_videos_paginated(user_id, chat_id, videos, page=0, page_size=10, category=None):
    if not videos:
        return

    total_videos = len(videos)
    total_pages = (total_videos + page_size - 1) // page_size  # محاسبه تعداد صفحات
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total_videos)

    # ارسال ویدیوهای صفحه جاری
    for i in range(start_idx, end_idx):
        video_info = videos[i]
        if isinstance(video_info, tuple):
            video_id = video_info[0]
            video_category = video_info[1] if len(video_info) > 1 else (category or "N/A")
        else:
            video_id = video_info
            video_category = category or "N/A"

        try:
            bot.send_video(chat_id, video_id, caption=f"دسته‌بندی: {video_category}")
        except Exception as e:
            logger.error(f"خطا در ارسال ویدیو: {e}")
            bot.send_message(chat_id, f"خطا در نمایش ویدیو: {video_id}")

    # نمایش دکمه صفحه بعد در صورت وجود
    if end_idx < total_videos:
        markup = types.InlineKeyboardMarkup()
        if category:
            encoded = encode_category_for_callback(category)
            next_cb = f"next_{encoded}_{page + 1}"
            next_button = types.InlineKeyboardButton("➡️ 3 تای بعدی", callback_data=next_cb)
        else:
            next_cb = f"next_all_{page + 1}"
            next_button = types.InlineKeyboardButton("➡️ 10 تای بعدی", callback_data=next_cb)
        markup.add(next_button)

        page_info = f"\n\nصفحه {page + 1} از {total_pages} - نمایش {start_idx + 1} تا {end_idx} از {total_videos} ویدیو"
        if category:
            bot.send_message(chat_id, f"ویدیوهای دسته‌بندی {category}{page_info}", reply_markup=markup)
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add('تماشای فیلم ها 🎥', '🎲 تماشای شانسی', '/home 🏠')
            bot.send_message(chat_id, "🎬", reply_markup=kb)
        else:
            bot.send_message(chat_id, f"همه ویدیوهای شما{page_info}", reply_markup=markup)
    else:
        page_info = f"\n\nصفحه {page + 1} از {total_pages} - نمایش {start_idx + 1} تا {end_idx} از {total_videos} ویدیو"
        if category:
            bot.send_message(chat_id, f"✅ تمام ویدیوهای دسته‌بندی {category} نمایش داده شد.{page_info}")
        else:
            bot.send_message(chat_id, f"✅ تمام ویدیوهای شما نمایش داده شد.{page_info}")
        home_from_id(chat_id)  # بازگشت به خانه پس از اتمام


@bot.callback_query_handler(func=lambda call: call.data.startswith('next_'))
def handle_next_button(call):
    user_id = call.from_user.id
    parts = call.data.split('_', 2)
    if len(parts) < 3:
        bot.answer_callback_query(call.id, "داده نامعتبر.")
        return

    _, category_code, page_str = parts
    try:
        page = int(page_str)
    except ValueError:
        bot.answer_callback_query(call.id, "داده نامعتبر.")
        return

    if user_id not in user_pagination:
        user_pagination[user_id] = {}

    user_pagination[user_id]['page'] = page

    if category_code == 'all':
        videos = get_user_videos(user_id)
        user_pagination[user_id]['all_videos'] = True
        user_pagination[user_id]['category'] = None
        send_videos_paginated(user_id, call.message.chat.id, videos, page=page, page_size=10)
    else:
        category = decode_category_from_callback(category_code)
        if category not in CATEGORIES:
            bot.answer_callback_query(call.id, "دسته‌بندی نامعتبر.")
            return
        videos = get_user_videos_by_category(user_id, category)
        user_pagination[user_id]['all_videos'] = False
        user_pagination[user_id]['category'] = category
        send_videos_paginated(user_id, call.message.chat.id, videos, page=page, page_size=3, category=category)

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)  # حذف پیام صفحه‌بندی قبلی
    except Exception:
        pass
    bot.answer_callback_query(call.id)


# ---------- Video content handler ----------
@bot.message_handler(content_types=['video'])
def get_video(message):
    user_id = message.from_user.id
    if not is_member(user_id):
        bot.send_message(
            message.chat.id,
            '⚠️ برای ارسال ویدیو باید در کانال عضو باشید.',
            reply_markup=create_join_channel_keyboard()
        )
        return

    video_id = message.video.file_id  # شناسه یکتای ویدیو در تلگرام

    if user_id in user_categories:
        category = user_categories[user_id]
        if save_video_to_db(user_id, video_id, category):
            current_category = user_categories.get(user_id, "تعیین نشده")
            bot.reply_to(
                message,
                f"✅ ویدیو در دسته‌بندی {category} ذخیره شد!\n\n"
                f"دسته‌بندی فعلی: {current_category}\n"
                f"برای تغییر دسته‌بندی از دکمه '🔄 تغییر دسته‌بندی' استفاده کنید."
            )
        else:
            bot.reply_to(message, "❌ خطا در ذخیره‌سازی ویدیو")
    else:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('تماشای فیلم ها 🎥', '🎲 تماشای شانسی', '/home 🏠')
        bot.send_message(message.chat.id, "❌ لطفاً ابتدا دسته‌بندی مورد نظر را انتخاب کنید.", reply_markup=markup)
        show_category_selection(message)


def save_video_to_db(user_id, video_id, category):
    try:
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO videos (video_id, user_id, category)
            VALUES (?, ?, ?)
        ''', (video_id, user_id, category))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"خطا در ذخیره‌سازی: {e}")
        return False


# ---------- DB query helpers ----------
def get_videos_by_category(category):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT video_id, user_id FROM videos WHERE category = ?', (category,))
    videos = cursor.fetchall()
    conn.close()
    return videos


def get_user_videos(user_id):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT video_id, category FROM videos WHERE user_id = ?', (user_id,))
    videos = cursor.fetchall()
    conn.close()
    return videos


def get_user_videos_by_category(user_id, category):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT video_id, category FROM videos WHERE user_id = ? AND category = ?', (user_id, category))
    videos = cursor.fetchall()
    conn.close()
    return videos


def get_video_info(video_id):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, category FROM videos WHERE video_id = ?', (video_id,))
    video = cursor.fetchone()
    conn.close()
    return video


# ---------- Admin ----------
@bot.message_handler(commands=['admin_control_for_manage_videos_and_more_text_for_Prevention_Access_normal_user'])
def admin(message):
    # TODO: در صورت نیاز محدودیت بر اساس user_id اضافه شود (تنها ادمین)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('📤 ارسال ویدیو', '🔄 تغییر دسته‌بندی')
    bot.send_message(message.chat.id, "به ربات مدیریت ویدیو خوش آمدید!", reply_markup=markup)


# ---------- Generic "catch-all" message handler ----------
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """
    هندلر کلی برای تمام پیام‌ها
    توجه: برخی هندلرهای اختصاصی بالاتر قادر به رسیدگی به پیام‌ها هستند؛
    این هندلر برای پیام‌های دیگر استفاده می‌شود و چک عضویت را انجام می‌دهد.
    """
    user_id = message.from_user.id
    if not is_member(user_id):
        bot.send_message(
            message.chat.id,
            '⚠️ برای استفاده از ربات باید در کانال عضو باشید.',
            reply_markup=create_join_channel_keyboard()
        )
        return

    # پردازش پیام‌های معمولی کاربران عضو
    # (در صورت نیاز می‌توانید پیام‌های عمومی را اینجا پردازش کنید)
    bot.send_message(
        message.chat.id,
        f'پیام شما دریافت شد: {message.text}'
    )


# ----------------- بوت راه‌اندازی -----------------
create_table()


def main():
    try:
        logger.info("Starting bot...")
        print("🤖 ربات فعال شد!")

        # برای Render - polling با هندل کردن خطاهای اتصال
        while True:
            try:
                bot.infinity_polling(timeout=60, long_polling_timeout=60)
            except Exception as e:
                logger.error(f"Polling error: {e}")
                print(f"🔁 تلاش مجدد پس از 15 ثانیه... خطا: {e}")
                time.sleep(15)

    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        print(f"❌ خطا در اجرای ربات: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
