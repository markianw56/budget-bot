import os
import re
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import gspread
from google.oauth2.service_account import Credentials

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TOKEN")
SHEET_ID  = os.environ.get("SHEET_ID",  "YOUR_SHEET_ID")
CREDS_FILE = "credentials.json"
SHEET_TAB  = "Expenses"
# ─────────────────────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


def get_sheet():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)
    try:
        worksheet = spreadsheet.worksheet(SHEET_TAB)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=SHEET_TAB, rows=1000, cols=10)
        worksheet.append_row(["Date", "Time", "Amount", "Store", "Category", "Notes"])
    return worksheet


def parse_expense(text):
    pattern = r"^(\d+(?:[.,]\d{1,2})?)\s+(\S+)\s+(\S+)(?:\s+(.+))?$"
    match = re.match(pattern, text.strip(), re.IGNORECASE)
    if not match:
        raise ValueError("Format not recognised")
    amount = float(match.group(1).replace(",", "."))
    store    = match.group(2).strip()
    category = match.group(3).strip()
    notes    = (match.group(4) or "").strip()
    return amount, store, category, notes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Budget Bot ready!\n\n"
        "Send an expense like this:\n"
        "AMOUNT STORE CATEGORY\n\n"
        "Examples:\n"
        "  1700 ATB Food\n"
        "  25.50 Starbucks Coffee\n"
        "  1200 Uber Transport work trip\n\n"
        "/summary — totals by category this month"
    )


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ws = get_sheet()
        rows = ws.get_all_records()
        now = datetime.now()
        totals = {}
        count = 0
        for row in rows:
            try:
                row_date = datetime.strptime(str(row["Date"]), "%Y-%m-%d")
            except (ValueError, KeyError):
                continue
            if row_date.year == now.year and row_date.month == now.month:
                cat = str(row.get("Category", "Other")).capitalize()
                totals[cat] = totals.get(cat, 0) + float(row.get("Amount", 0))
                count += 1

        if not totals:
            await update.message.reply_text("No expenses recorded this month yet.")
            return

        grand_total = sum(totals.values())
        lines = [f"📊 {now.strftime('%B %Y')} Summary ({count} transactions)\n"]
        for cat, total in sorted(totals.items(), key=lambda x: -x[1]):
            pct = total / grand_total * 100
            lines.append(f"  {cat}: {total:,.2f} ({pct:.0f}%)")
        lines.append(f"\n💰 Total: {grand_total:,.2f}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logging.error(e)
        await update.message.reply_text(f"❌ Error: {e}")


async def handle_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    try:
        amount, store, category, notes = parse_expense(text)
    except ValueError:
        await update.message.reply_text(
            "⚠️ Use this format:\nAMOUNT STORE CATEGORY\n\nExample: 1700 ATB Food"
        )
        return
    try:
        ws = get_sheet()
        now = datetime.now()
        ws.append_row([
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M"),
            amount,
            store.capitalize(),
            category.capitalize(),
            notes,
        ])
        reply = (
            f"✅ Logged!\n"
            f"  💵 Amount:   {amount:,.2f}\n"
            f"  🏪 Store:    {store.capitalize()}\n"
            f"  🏷️ Category: {category.capitalize()}"
        )
        if notes:
            reply += f"\n  📝 Note: {notes}"
        await update.message.reply_text(reply)
    except Exception as e:
        logging.error(e)
        await update.message.reply_text(f"❌ Failed to save: {e}")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("help",    start))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expense))
    logging.info("Bot is running…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
