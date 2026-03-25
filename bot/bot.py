import asyncio
import json
import logging
import os
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ContentType, ParseMode
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
# Support both `bot/.env` and repository-root `.env` for local development.
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env", override=True)

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-hashpay-miniapp.vercel.app")
BOT_TOKEN = os.getenv("BOT_TOKEN")

dp = Dispatcher()


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


def sanitize_text(value: object, fallback: str) -> str:
    """Escape user-provided data before sending it as HTML."""
    if value in (None, ""):
        return fallback
    return escape(str(value))


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    """Send welcome message with a button that launches the Mini App."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Launch HashPay",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ]
        ],
        resize_keyboard=True,
        input_field_placeholder="Tap the button below to open HashPay",
    )

    text = (
        "<b>HASHPAY // DARK BRIDGE</b>\n"
        "Secure P2P settlement rail for resellers and travelers.\n\n"
        "• Escrow-backed exchange flow\n"
        "• Top up Alipay / Papara / foreign cards\n"
        "• Fast KYC tiers for different turnover sizes\n\n"
        "Open the Mini App and submit your request."
    )
    await message.answer(text, reply_markup=keyboard)


@dp.message(F.content_type == ContentType.WEB_APP_DATA)
async def web_app_data_handler(message: Message) -> None:
    """Receive JSON payload from Telegram Mini App and confirm the request."""
    raw_data = message.web_app_data.data if message.web_app_data else ""

    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        await message.answer(
            "Не удалось обработать заявку: Mini App прислал некорректные данные."
        )
        return

    amount_rub = format_rub(payload.get("amount_rub"))
    tier = sanitize_text(payload.get("kyc_tier"), "Tier 1")
    target_currency = sanitize_text(payload.get("target_currency"), "CNY")
    converted_amount = sanitize_text(payload.get("target_amount"), "0")
    phone = sanitize_text(payload.get("phone"), "не указан")
    payout_method = sanitize_text(payload.get("payout_method"), "manual settlement")

    response = (
        f"Заявка на <b>{amount_rub} RUB</b> принята.\n"
        f"Статус верификации: <b>{tier}</b>\n"
        f"Валюта получения: <b>{target_currency}</b> ({converted_amount})\n"
        f"Контакт: <b>{phone}</b>\n"
        f"Маршрут: <b>{payout_method}</b>"
    )

    if tier == "Tier 2":
        passport_name = sanitize_text(payload.get("passport_file_name"), "не прикреплен")
        selfie_name = sanitize_text(payload.get("selfie_file_name"), "не прикреплен")
        response += (
            f"\nПаспорт: <b>{passport_name}</b>"
            f"\nСелфи: <b>{selfie_name}</b>"
        )
    elif tier == "Tier 3":
        response += "\nМенеджер HashPay свяжется с вами для high-volume онбординга."

    await message.answer(response)


async def main() -> None:
    """Run bot polling."""
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required")

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
