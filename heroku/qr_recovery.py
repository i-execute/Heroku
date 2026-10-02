import asyncio
import contextlib
import io
import logging
import os
import struct

import qrcode
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import MemorySession, SQLiteSession
from telethon.tl.types import PeerChannel

from . import main as heroku_main
from .botpm import BotPM

logger = logging.getLogger(__name__)

QR_REFRESH = 15
TOTAL_TIMEOUT = 180


def _qr_bytes(url: str) -> bytes:
    image = qrcode.make(url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _inline_location(value):
    owner_id = getattr(value, "owner_id", None)
    message_id = getattr(value, "id", None)
    if owner_id is not None and message_id is not None:
        peer = PeerChannel(-owner_id) if owner_id < 0 else None
        return peer, message_id
    if message_id is None:
        return None
    try:
        unpacked_id, peer_id = struct.unpack("<ii", struct.pack("<q", message_id))
    except (struct.error, OverflowError):
        return None
    peer = PeerChannel(-peer_id) if peer_id < 0 else None
    return peer, unpacked_id


async def _delete_inline_messages(client, bot: BotPM):
    for value in bot.inline_messages:
        location = _inline_location(value)
        if not location:
            continue
        peer, message_id = location
        with contextlib.suppress(Exception):
            await client.delete_messages(peer, [message_id])
    bot.inline_messages.clear()


async def _save_session(client, me) -> None:
    session = SQLiteSession(
        os.path.join(heroku_main.SESSIONS_DIR, f"heroku-{me.id}")
    )
    session.set_dc(
        client.session.dc_id, client.session.server_address, client.session.port
    )
    session.auth_key = client.session.auth_key
    session.save()
    session.close()


async def _qr_login(client, bot: BotPM):
    await client.connect()
    qr = await client.qr_login()
    await bot.send_photo(
        _qr_bytes(qr.url),
        "Open Telegram > Settings > Devices > Link Desktop Device. The QR code refreshes automatically.",
    )
    elapsed = 0.0
    while elapsed < TOTAL_TIMEOUT:
        try:
            return await asyncio.wait_for(
                qr.wait(), timeout=min(QR_REFRESH, TOTAL_TIMEOUT - elapsed)
            )
        except SessionPasswordNeededError:
            password = await asyncio.wait_for(
                bot.ask("Enter the 2FA password", "Enter password", "🔐"),
                timeout=TOTAL_TIMEOUT,
            )
            await client.sign_in(password=password)
            return await client.get_me()
        except asyncio.TimeoutError:
            elapsed += QR_REFRESH
            if elapsed >= TOTAL_TIMEOUT:
                break
            await qr.recreate()
            await bot.edit_photo(
                _qr_bytes(qr.url),
                "The QR code was refreshed. Scan the new code.",
            )
    return None


async def _phone_login(client, bot: BotPM):
    await client.connect()
    phone = await asyncio.wait_for(
        bot.ask("Enter the phone number in international format", "Enter phone", "📝"),
        timeout=TOTAL_TIMEOUT,
    )
    sent = await client.send_code_request(phone)
    password_required = False
    for _ in range(3):
        code = await asyncio.wait_for(
            bot.ask("Enter the login code", "Enter code", "📝"),
            timeout=TOTAL_TIMEOUT,
        )
        code = code.replace(" ", "").replace("-", "")
        try:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=sent.phone_code_hash,
            )
            return await client.get_me()
        except SessionPasswordNeededError:
            password_required = True
            break
        except Exception as error:
            await bot.send(f"Login code error: {error}")
    if not password_required:
        return None
    for _ in range(3):
        password = await asyncio.wait_for(
            bot.ask("Enter the 2FA password", "Enter password", "🔐"),
            timeout=TOTAL_TIMEOUT,
        )
        try:
            await client.sign_in(password=password)
            return await client.get_me()
        except Exception as error:
            await bot.send(f"Password error: {error}")
    return None


async def send_qr_recovery(api_id: int, api_hash: str) -> bool:
    token = heroku_main.get_config_key("bot_token")
    owner_id = heroku_main.get_config_key("owner_id")
    if not token or not owner_id:
        logging.error("Recovery requires bot_token and owner_id in config.json")
        return False
    bot = BotPM(api_id, api_hash, token)
    client = TelegramClient(
        MemorySession(), api_id, api_hash, connection_retries=None
    )
    try:
        await bot.start()
        await bot.wait_start(expected_id=int(owner_id))
        bot.owner_id = int(owner_id)
        await bot.send("The user session was terminated. Starting recovery.")
        method = await bot.choose_auth()
        user = (
            await _phone_login(client, bot)
            if method == "phone"
            else await _qr_login(client, bot)
        )
        if user is None:
            await bot.send("Login timed out or failed. Restart the userbot and try again.")
            return False
        if user.id != int(owner_id):
            await bot.send("The authorized account does not match the configured owner.")
            return False
        await _delete_inline_messages(client, bot)
        await _save_session(client, user)
        await bot.send("The session was restored. Restarting.")
        return True
    except Exception:
        logger.exception("Recovery failed")
        return False
    finally:
        await client.disconnect()
        await bot.close()


async def run_bot_setup() -> bool:
    api_id = int(heroku_main.get_config_key("api_id"))
    api_hash = heroku_main.get_config_key("api_hash")
    token = heroku_main.get_config_key("bot_token")
    if not token:
        logging.error("Bot token is missing")
        return False
    bot = BotPM(api_id, api_hash, token)
    client = TelegramClient(
        MemorySession(), api_id, api_hash, connection_retries=None
    )
    try:
        me = await bot.start()
        print(f"Open @{me.username} and send /start to get your Telegram ID.")
        bot.start_echo()
        owner_id = int(
            (await asyncio.to_thread(input, "Enter your Telegram ID: ")).strip()
        )
        bot.stop_echo()
        print(f"Send /start to @{me.username} again.")
        await bot.wait_start(owner_id)
        bot.owner_id = owner_id
        method = await bot.choose_auth()
        user = (
            await _phone_login(client, bot)
            if method == "phone"
            else await _qr_login(client, bot)
        )
        if user is None:
            await bot.send("Login timed out or failed. Restart the userbot and try again.")
            return False
        if user.id != owner_id:
            await bot.send("The authorized account does not match the entered Telegram ID.")
            return False
        heroku_main.save_config_key("owner_id", owner_id)
        await _delete_inline_messages(client, bot)
        await _save_session(client, user)
        print(f"Logged in as {user.first_name}. Restarting.")
        await bot.send(f"Logged in as {user.first_name}. Restarting.")
        return True
    except Exception:
        logger.exception("Bot setup failed")
        return False
    finally:
        await client.disconnect()
        await bot.close()
