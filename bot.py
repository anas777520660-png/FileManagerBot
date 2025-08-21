# -*- coding: utf-8 -*-
import os
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# توكن بوتك (سِرّي)
BOT_TOKEN = "8212407202:AAGyyXEtedXFfFHYU7NLs7CfKUM3PoAsoa4"

# مجلد الجذر على جهازك
ROOT_DIR = Path(r"D:\العقود")  # غيّره إذا لزم

# الإعدادات
PAGE_SIZE = 10  # عدد العناصر في الصفحة (مجلدات + ملفات)

# ====== توليد معرّفات قصيرة للأزرار ======
ID2PATH: dict[str, str] = {}
PATH2ID: dict[str, str] = {}
_id_counter = 0

def short_id_for(rel_path: str) -> str:
    """
    يأخذ مسارًا نسبيًا (POSIX) ويعيد معرّفًا قصيرًا ثابتًا خلال تشغيل البوت.
    الشكل: p1, p2, ...
    """
    global _id_counter
    if rel_path in PATH2ID:
        return PATH2ID[rel_path]
    _id_counter += 1
    sid = f"p{_id_counter}"
    PATH2ID[rel_path] = sid
    ID2PATH[sid] = rel_path
    return sid

def get_path_from_id(sid: str) -> str | None:
    return ID2PATH.get(sid)

# ---------- أدوات أمان ومساعِدة ----------
def safe_join(base: Path, *parts) -> Path:
    """يمنع الخروج خارج مجلد الجذر."""
    p = (base.joinpath(*parts)).resolve()
    if not str(p).startswith(str(base.resolve())):
        raise ValueError("مسار غير مسموح")
    return p

def list_dirs(path: Path):
    return sorted([p for p in path.iterdir() if p.is_dir()], key=lambda x: x.name.lower())

def list_files(path: Path):
    return sorted([p for p in path.iterdir() if p.is_file()], key=lambda x: x.name.lower())

def build_keyboard(rel: str, page: int = 0) -> InlineKeyboardMarkup:
    """
    rel: مسار نسبي داخل ROOT_DIR ('.' للجذر)
    يجمع المجلدات ثم الملفات ويقسّمها صفحات.
    نضع في callback_data معرّفات قصيرة فقط لتفادي تجاوز 64 بايت.
    """
    base = safe_join(ROOT_DIR, rel)
    dirs = list_dirs(base)
    files = list_files(base)

    # عناصر القائمة: أولاً مجلدات ثم ملفات
    items = [("dir", d.name) for d in dirs] + [("file", f.name) for f in files]

    # تقسيم صفحات
    total = len(items)
    start, end = page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE
    page_items = items[start:end]

    rows = []
    for kind, name in page_items:
        rel_path = (Path(rel) / name).as_posix()
        sid = short_id_for(rel_path)
        if kind == "dir":
            # "o:" = open, ثم id، ثم الصفحة (قصيرة جدًا)
            rows.append([InlineKeyboardButton(f"📁 {name}", callback_data=f"o:{sid}:{0}")])
        else:
            # "s:" = send
            rows.append([InlineKeyboardButton(f"📄 {name}", callback_data=f"s:{sid}")])

    # أزرار التنقل بين الصفحات
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("« السابق", callback_data=f"pg:{short_id_for(rel)}:{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton("التالي »", callback_data=f"pg:{short_id_for(rel)}:{page+1}"))
    if nav:
        rows.append(nav)

    # زر رجوع للأعلى إن لم نكن في الجذر
    if Path(rel) != Path("."):
        parent = Path(rel).parent.as_posix()
        rows.append([InlineKeyboardButton("⬅️ رجوع للمجلد الأعلى", callback_data=f"o:{short_id_for(parent or '.')}:{0}")])

    # زر تحديث
    rows.append([InlineKeyboardButton("🔄 تحديث", callback_data=f"o:{short_id_for(rel)}:{page}")])

    return InlineKeyboardMarkup(rows or [[InlineKeyboardButton("— لا توجد عناصر —", callback_data="noop")]])

# ---------- الأوامر ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 أهلاً بك! اكتب /browse لتصفّح ملفاتك.")

async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ROOT_DIR.exists():
        await update.message.reply_text(f"⚠️ لم أجد المجلد: {ROOT_DIR}")
        return
    await update.message.reply_text("اختر مجلدًا أو ملفًا:", reply_markup=build_keyboard(".", 0))

# ---------- التعامل مع الأزرار ----------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    try:
        # فتح مجلد: "o:<sid>:<page>"
        if data.startswith("o:"):
            _, sid, page_str = data.split(":", 2)
            rel = get_path_from_id(sid) or "."
            await q.message.edit_text(
                f"📂 {rel if rel!='.' else 'الجذر'}",
                reply_markup=build_keyboard(rel, int(page_str))
            )
            return

        # تغيير صفحة: "pg:<sid>:<page>"
        if data.startswith("pg:"):
            _, sid, page_str = data.split(":", 2)
            rel = get_path_from_id(sid) or "."
            await q.message.edit_text(
                f"📂 {rel if rel!='.' else 'الجذر'}",
                reply_markup=build_keyboard(rel, int(page_str))
            )
            return

        # إرسال ملف: "s:<sid>"
        if data.startswith("s:"):
            _, sid = data.split(":", 1)
            rel_file = get_path_from_id(sid)
            if not rel_file:
                await q.message.reply_text("❌ لم أتعرف على الملف.")
                return
            file_path = safe_join(ROOT_DIR, rel_file)
            if not file_path.exists() or not file_path.is_file():
                await q.message.reply_text("❌ الملف غير موجود.")
                return
            with open(file_path, "rb") as f:
                await q.message.reply_document(f, caption=file_path.name)
            return

    except Exception as e:
        await q.message.reply_text(f"حدث خطأ: {e}")

# ---------- رد بسيط على النصوص ----------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip().lower()
    if text in {"مرحبا", "اهلا", "أهلا", "السلام عليكم", "hi", "hello"}:
        await update.message.reply_text("وعليكم السلام 👋 — اكتب /browse لتصفّح الملفات.")
    else:
        await update.message.reply_text("استخدم /browse لتصفّح الملفات أو /start للمساعدة.")

# ---------- التشغيل ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("browse", browse))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🟢 البوت يعمل — افتح تليجرام وأرسل /browse")
    app.run_polling()

if __name__ == "__main__":
    main()
