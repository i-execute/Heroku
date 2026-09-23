# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

import asyncio
import io
import logging

import qrcode

from . import main as heroku_main
from .botpm import BotPM

logger = logging.getLogger(__name__)

QR_REFRESH = 15
TOTAL_TIMEOUT = 180


def _qr_bytes(url: str) -> bytes:
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _save_session(client, me) -> None:
    from telethon.sessions import SQLiteSession
    import os

    session = SQLiteSession(
        os.path.join(heroku_main.SESSIONS_DIR, f"heroku-{me.id}")
    )
    session.set_dc(
        client.session.dc_id, client.session.server_address, client.session.port
    )
    session.auth_key = client.session.auth_key
    session.save()


async def send_qr_recovery(api_id: int, api_hash: str) -> bool:
    """Session died. Send QR to owner PM, wait for scan, restore session."""
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
    from telethon.sessions import MemorySession

    token = heroku_main.get_config_key("bot_token")
    owner_id = heroku_main.get_config_key("owner_id")

    if not token or not owner_id:
        logging.error("QR recovery skipped: no bot_token/owner_id in config.json")
        return False

    bot = BotPM(api_id, api_hash, token)
    client = TelegramClient(
        MemorySession(), api_id, api_hash, connection_retries=None
    )

    try:
        await bot.start()
        await bot.wait_start(expected_id=owner_id)
        bot.owner_id = owner_id
        await bot.send("Session terminated. Starting QR recovery...")
        await client.connect()
        qr = await client.qr_login()

        await bot.send_photo(
            _qr_bytes(qr.url),
            "Session terminated. Scan: Telegram → Settings → Devices →"
            " Link Desktop Device. QR refreshes automatically.",
        )

        user = None
        elapsed = 0.0
        while elapsed < TOTAL_TIMEOUT and user is None:
            try:
                user = await asyncio.wait_for(
                    qr.wait(), timeout=min(QR_REFRESH, TOTAL_TIMEOUT - elapsed)
                )
            except SessionPasswordNeededError:
                try:
                    password = await asyncio.wait_for(
                        bot.ask(
                            "2FA password required — press the button, type it"
                            " and tap send:",
                        ),
                        timeout=TOTAL_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    await bot.send("2FA password not provided in time. Aborting.")
                    return False

                try:
                    await client.sign_in(password=password)
                    user = await client.get_me()
                except Exception as e:
                    await bot.send(f"Wrong password: {e}. Aborting.")
                    return False
                break
            except asyncio.TimeoutError:
                elapsed += QR_REFRESH
                await qr.recreate()
                await bot.edit_photo(
                    _qr_bytes(qr.url), "QR refreshed, scan the new one."
                )

        if user is None:
            await bot.send("QR not scanned in time. Restart the userbot.")
            return False

        await _save_session(client, user)
        await bot.send("Session restored! Restarting...")
        return True
    except Exception:
        logger.exception("QR recovery failed")
        return False
    finally:
        await client.disconnect()
        await bot.close()


async def run_bot_setup() -> bool:
    """Fresh install via owner PM: token in terminal, rest via bot."""
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
    from telethon.sessions import MemorySession

    print("\nNo session found.")
    choice = input("Do you want to continue with bot? [y/n] ").strip().lower()
    if choice not in ("y", "yes", "д"):
        return False

    api_id = int(heroku_main.get_config_key("api_id"))
    api_hash = heroku_main.get_config_key("api_hash")
    token = input("Bot token: ").strip()

    heroku_main.save_config_key("bot_token", token)

    bot = BotPM(api_id, api_hash, token)
    client = TelegramClient(
        MemorySession(), api_id, api_hash, connection_retries=None
    )

    try:
        me = await bot.start()
        print(
            f"\nBot @{me.username} started. Send /start to it —"
            " it will reply with your Telegram ID."
        )
        bot.start_echo()
        owner_id = int(
            (await asyncio.to_thread(input, "Enter your Telegram ID: ")).strip()
        )
        bot.stop_echo()
        heroku_main.save_config_key("owner_id", owner_id)
        print(f"Waiting for /start from ID {owner_id}...")
        await bot.wait_start(owner_id)
        bot.owner_id = owner_id
        print("Owner bound. Generating QR code...")

        await client.connect()
        qr = await client.qr_login()

        await bot.send_photo(
            _qr_bytes(qr.url),
            "Scan: Telegram → Settings → Devices → Link Desktop Device."
            " QR refreshes automatically.",
        )
        print("QR sent. Waiting for scan...")

        user = None
        elapsed = 0.0
        while elapsed < TOTAL_TIMEOUT and user is None:
            try:
                user = await asyncio.wait_for(
                    qr.wait(), timeout=min(QR_REFRESH, TOTAL_TIMEOUT - elapsed)
                )
            except SessionPasswordNeededError:
                try:
                    password = await asyncio.wait_for(
                        bot.ask(
                            "2FA password required — press the button, type it"
                            " and tap send:",
                        ),
                        timeout=TOTAL_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    await bot.send("2FA password not provided in time. Aborting.")
                    return False

                try:
                    await client.sign_in(password=password)
                    user = await client.get_me()
                except Exception as e:
                    await bot.send(f"Wrong password: {e}. Aborting.")
                    return False
                break
            except asyncio.TimeoutError:
                elapsed += QR_REFRESH
                await qr.recreate()
                await bot.edit_photo(
                    _qr_bytes(qr.url), "QR refreshed, scan the new one."
                )
        if user is None:
            await bot.send("QR not scanned in time. Restart the userbot.")
            return False

        await _save_session(client, user)
        print(f"Logged in as {user.first_name}. Restarting...")
        await bot.send(f"Done! Logged in as {user.first_name}. Restarting...")
        return True
    except Exception:
        logger.exception("Bot setup failed")
        return False
    finally:
        await client.disconnect()
        await bot.close()
