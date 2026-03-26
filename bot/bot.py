import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from secrets import token_hex

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ContentType, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "hashpay.sqlite3"

# Support both `bot/.env` and repository-root `.env` for local development.
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env", override=True)

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-hashpay-miniapp.vercel.app")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

STATUS_NEW = "Новая"
STATUS_IN_PROGRESS = "В работе"
STATUS_DONE = "Закрыта"
STATUS_CANCELLED = "Отменена"

dp = Dispatcher()


def init_db() -> None:
    """Create the local SQLite database for manual-order tracking."""
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                username TEXT,
                full_name TEXT,
                amount_rub TEXT,
                target_currency TEXT,
                target_amount TEXT,
                payout_method TEXT,
                payout_destination TEXT,
                recipient_name TEXT,
                contact TEXT,
                note TEXT,
                kyc_tier TEXT,
                status TEXT NOT NULL,
                passport_file_name TEXT,
                selfie_file_name TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def format_rub(amount: str | int | float | None) -> str:
    """Return a user-friendly RUB amount string."""
    if amount in (None, ""):
        return "0"

    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        return str(amount)

    normalized = value.quantize(Decimal("1")) if value == value.to_integral() else value.normalize()
    return f"{normalized:,}".replace(",", " ")


def sanitize_text(value: object, fallback: str = "не указано") -> str:
    """Escape user-provided data before sending it as HTML."""
    if value in (None, ""):
        return fallback
    return escape(str(value))


def generate_application_id() -> str:
    """Create a short, operator-friendly application identifier."""
    return f"HP-{datetime.now():%y%m%d}-{token_hex(2).upper()}"


def is_admin_message(message: Message) -> bool:
    """Check whether the incoming message belongs to the configured admin chat."""
    return bool(ADMIN_CHAT_ID) and str(message.chat.id) == str(ADMIN_CHAT_ID)


def create_application_record(message: Message, payload: dict[str, object]) -> dict[str, object]:
    """Persist a new manual order request and return the created record."""
    application = {
        "id": generate_application_id(),
        "user_id": message.from_user.id if message.from_user else 0,
        "chat_id": message.chat.id,
        "username": message.from_user.username if message.from_user else "",
        "full_name": message.from_user.full_name if message.from_user else "",
        "amount_rub": str(payload.get("amount_rub", "")),
        "target_currency": str(payload.get("target_currency", "")),
        "target_amount": str(payload.get("target_amount", "")),
        "payout_method": str(payload.get("payout_method", "")),
        "payout_destination": str(payload.get("payout_destination", "")),
        "recipient_name": str(payload.get("recipient_name", "")),
        "contact": str(payload.get("phone", "")),
        "note": str(payload.get("note", "")),
        "kyc_tier": str(payload.get("kyc_tier", "Tier 1")),
        "status": STATUS_NEW,
        "passport_file_name": str(payload.get("passport_file_name", "")),
        "selfie_file_name": str(payload.get("selfie_file_name", "")),
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO applications (
                id, user_id, chat_id, username, full_name, amount_rub, target_currency,
                target_amount, payout_method, payout_destination, recipient_name, contact,
                note, kyc_tier, status, passport_file_name, selfie_file_name, created_at
            ) VALUES (
                :id, :user_id, :chat_id, :username, :full_name, :amount_rub, :target_currency,
                :target_amount, :payout_method, :payout_destination, :recipient_name, :contact,
                :note, :kyc_tier, :status, :passport_file_name, :selfie_file_name, :created_at
            )
            """,
            application,
        )

    return application


def get_application(application_id: str) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM applications WHERE id = ?",
            (application_id,),
        ).fetchone()


def get_recent_applications(limit: int = 10) -> list[sqlite3.Row]:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT id, amount_rub, target_currency, target_amount, status, created_at
            FROM applications
            ORDER BY rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def update_application_status(application_id: str, status: str) -> sqlite3.Row | None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE applications SET status = ? WHERE id = ?",
            (status, application_id),
        )
        return connection.execute(
            "SELECT * FROM applications WHERE id = ?",
            (application_id,),
        ).fetchone()


def format_application_message(application: sqlite3.Row | dict[str, object], *, admin_view: bool) -> str:
    """Render a readable HTML message for user and admin chats."""
    application_id = sanitize_text(application["id"])
    amount_rub = format_rub(application["amount_rub"])
    target_currency = sanitize_text(application["target_currency"])
    target_amount = sanitize_text(application["target_amount"])
    payout_method = sanitize_text(application["payout_method"])
    payout_destination = sanitize_text(application["payout_destination"])
    recipient_name = sanitize_text(application["recipient_name"], "не указано")
    contact = sanitize_text(application["contact"], "не указан")
    note = sanitize_text(application["note"], "без комментария")
    kyc_tier = sanitize_text(application["kyc_tier"], "Tier 1")
    status = sanitize_text(application["status"], STATUS_NEW)
    created_at = sanitize_text(application["created_at"])

    text = (
        f"<b>Заявка {application_id}</b>\n"
        f"Статус: <b>{status}</b>\n"
        f"Создана: <b>{created_at}</b>\n\n"
        f"Сумма: <b>{amount_rub} RUB</b>\n"
        f"Получение: <b>{target_amount}</b>\n"
        f"Маршрут: <b>{payout_method}</b>\n"
        f"Реквизиты получателя: <b>{payout_destination}</b>\n"
        f"Имя получателя: <b>{recipient_name}</b>\n"
        f"Контакт: <b>{contact}</b>\n"
        f"KYC: <b>{kyc_tier}</b>\n"
        f"Комментарий: <b>{note}</b>"
    )

    if admin_view:
        username = sanitize_text(application["username"], "без username")
        full_name = sanitize_text(application["full_name"], "без имени")
        passport_name = sanitize_text(application["passport_file_name"], "не прикреплен")
        selfie_name = sanitize_text(application["selfie_file_name"], "не прикреплен")
        user_id = sanitize_text(application["user_id"], "0")

        text += (
            f"\n\nПользователь: <b>{full_name}</b>"
            f"\nUsername: <b>{username}</b>"
            f"\nTelegram ID: <b>{user_id}</b>"
            f"\nПаспорт: <b>{passport_name}</b>"
            f"\nСелфи: <b>{selfie_name}</b>"
            f"\n\nКоманды:"
            f"\n/take {application_id}"
            f"\n/done {application_id}"
            f"\n/cancel {application_id}"
        )

    return text


def extract_application_id(message: Message) -> str | None:
    """Read an application ID from an admin command like `/take HP-123`."""
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[1].strip().upper()


async def notify_admin(bot: Bot, application: dict[str, object]) -> None:
    """Send a structured application card to the configured admin chat."""
    if not ADMIN_CHAT_ID:
        logging.warning("ADMIN_CHAT_ID is not configured; skipping admin notification")
        return

    await bot.send_message(
        chat_id=int(ADMIN_CHAT_ID),
        text=format_application_message(application, admin_view=True),
    )


async def notify_user_status_change(bot: Bot, application: sqlite3.Row) -> None:
    """Inform the user that the manual order status was updated by the operator."""
    await bot.send_message(
        chat_id=int(application["chat_id"]),
        text=(
            f"Статус заявки <b>{sanitize_text(application['id'])}</b> обновлен.\n"
            f"Новый статус: <b>{sanitize_text(application['status'])}</b>"
        ),
    )


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    """Send welcome message with a button that launches the Mini App."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Открыть HashPay",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ]
        ],
        resize_keyboard=True,
        input_field_placeholder="Нажмите кнопку ниже, чтобы открыть HashPay",
    )

    text = (
        "<b>HASHPAY // DARK BRIDGE</b>\n"
        "Сервис заявок для ручного пополнения зарубежных сервисов.\n\n"
        "• Расчет суммы и комиссии\n"
        "• Заявка на Alipay / Papara\n"
        "• Ручная обработка менеджером\n\n"
        "Откройте Mini App и создайте заявку."
    )
    await message.answer(text, reply_markup=keyboard)


@dp.message(Command("myid"))
async def my_id_handler(message: Message) -> None:
    """Show the current private chat ID so it can be copied into ADMIN_CHAT_ID."""
    await message.answer(f"Ваш chat ID: <b>{message.chat.id}</b>")


@dp.message(Command("orders"))
async def orders_handler(message: Message) -> None:
    """Show recent applications to the admin."""
    if not is_admin_message(message):
        await message.answer("Эта команда доступна только администратору.")
        return

    orders = get_recent_applications()
    if not orders:
        await message.answer("Пока нет заявок.")
        return

    lines = ["<b>Последние заявки</b>"]
    for order in orders:
        lines.append(
            f"{sanitize_text(order['id'])} | "
            f"{format_rub(order['amount_rub'])} RUB -> "
            f"{sanitize_text(order['target_amount'])} | "
            f"{sanitize_text(order['status'])}"
        )
    await message.answer("\n".join(lines))


async def handle_status_command(message: Message, status: str) -> None:
    """Common handler for admin status updates."""
    if not is_admin_message(message):
        await message.answer("Эта команда доступна только администратору.")
        return

    application_id = extract_application_id(message)
    if not application_id:
        await message.answer("Укажите ID заявки. Пример: /take HP-250326-AB12")
        return

    application = update_application_status(application_id, status)
    if not application:
        await message.answer("Заявка не найдена.")
        return

    await message.answer(
        f"Статус заявки <b>{sanitize_text(application_id)}</b> обновлен: <b>{sanitize_text(status)}</b>"
    )
    await notify_user_status_change(message.bot, application)


@dp.message(Command("take"))
async def take_handler(message: Message) -> None:
    await handle_status_command(message, STATUS_IN_PROGRESS)


@dp.message(Command("done"))
async def done_handler(message: Message) -> None:
    await handle_status_command(message, STATUS_DONE)


@dp.message(Command("cancel"))
async def cancel_handler(message: Message) -> None:
    await handle_status_command(message, STATUS_CANCELLED)


@dp.message(F.content_type == ContentType.WEB_APP_DATA)
async def web_app_data_handler(message: Message) -> None:
    """Receive JSON payload from Telegram Mini App, store it, and notify admin."""
    raw_data = message.web_app_data.data if message.web_app_data else ""

    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        await message.answer(
            "Не удалось обработать заявку: Mini App прислал некорректные данные."
        )
        return

    application = create_application_record(message, payload)

    await message.answer(
        f"Заявка <b>{sanitize_text(application['id'])}</b> создана.\n"
        f"Статус: <b>{STATUS_NEW}</b>\n"
        "Менеджер проверит данные и свяжется с вами вручную."
    )

    await notify_admin(message.bot, application)


async def main() -> None:
    """Run bot polling."""
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(main())
