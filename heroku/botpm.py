# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

import asyncio
import contextlib
import io

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.custom.button import Button
from telethon.tl.types import InputMediaPhoto, UpdateBotInlineSend

from .utils.other import rand as utils_rand


class BotPM:
    """MTProto bot client for owner PM (setup + QR recovery).

    Standalone client: it owns its own inline handler, so the switch_inline
    button it renders is answered by the same bot that drew the message.
    The picked article comes back as UpdateBotInlineSend, not a PM message.
    """

    def __init__(self, api_id: int, api_hash: str, token: str):
        self.token = token
        self.client = TelegramClient(
            StringSession(), api_id, api_hash, connection_retries=None
        )
        self.chat_id: int | None = None
        self.owner_id: int | None = None
        self._inbox: asyncio.Queue = asyncio.Queue()
        self._ask_state: tuple | None = None
        self._qr_msg = None

    async def start(self):
        await self.client.start(bot_token=self.token)
        self.client.add_event_handler(
            self._on_msg, events.NewMessage(incoming=True)
        )
        self.client.add_event_handler(self._on_iq, events.InlineQuery())
        self.client.add_event_handler(
            self._on_inline_send, events.Raw(types=UpdateBotInlineSend)
        )
        return await self.client.get_me()

    async def _on_msg(self, event):
        if self.chat_id and event.chat_id == self.chat_id:
            self._inbox.put_nowait(event.raw_text)

    async def _on_iq(self, event):
        """Answer the switch_inline query.

        Telegram hands us `@bot <token> <value>`. The article `id` must be the
        WHOLE query — that is what comes back in UpdateBotInlineSend.query,
        and what the chosen-inline handler matches against.
        """
        state = self._ask_state
        if not state:
            return

        token, fut = state
        if self.owner_id and event.query.user_id != self.owner_id:
            return

        text = event.text or ""
        parts = text.split(maxsplit=1)
        if not parts or parts[0] != token:
            return

        await event.answer(
            [
                await event.builder.article(
                    "Tap to send",
                    description="password",
                    text="Enter your 2FA password:",
                    parse_mode=None,
                    id=text,
                )
            ],
            cache_time=0,
            private=True,
        )

    async def _on_inline_send(self, update):
        """The picked article: UpdateBotInlineSend.query carries `token value`."""
        state = self._ask_state
        if not state:
            return

        token, fut = state
        if fut.done():
            return

        query = getattr(update, "query", "") or ""
        parts = query.split(maxsplit=1)
        if len(parts) < 2 or parts[0] != token:
            return

        fut.set_result(parts[1].strip())

    def _bind_owner_id(self, expected_id: int | None) -> None:
        """Owner binding: only /start from expected_id (or anyone if None)."""
        waiter = asyncio.get_running_loop().create_future()

        @self.client.on(events.NewMessage(pattern=r"^/start"))
        async def _on_start(event):
            if expected_id and event.sender_id != expected_id:
                with contextlib.suppress(Exception):
                    await event.reply("Not for you.")
                return
            if not waiter.done():
                self.chat_id = event.chat_id
                waiter.set_result(event.chat_id)

        self._waiter = waiter

    def start_echo(self):
        """Echo mode: reply to any /start with sender's Telegram ID."""
        @self.client.on(events.NewMessage(pattern=r"^/start"))
        async def _echo(event):
            with contextlib.suppress(Exception):
                await event.reply(f"This is your id – {event.sender_id}")

        self._echo_handler = _echo

    def stop_echo(self):
        if getattr(self, "_echo_handler", None):
            self.client.remove_event_handler(self._echo_handler)
            self._echo_handler = None

    async def wait_start(self, expected_id: int | None = None) -> int:
        """Bind owner: only /start from expected_id (setup input) or first
        /start when unknown (QR-recovery with configured owner_id)."""
        self._bind_owner_id(expected_id)
        return await self._waiter

    async def send(self, text: str, button: bool = False):
        await self.client.send_message(
            self.chat_id,
            text,
            buttons=Button.force_reply() if button else Button.clear(),
        )

    async def ask(self, prompt: str) -> str:
        """Ask via switch_inline.

        The button prefills `@bot <token> ` into the input field; the value the
        user types lands in UpdateBotInlineSend.query as `token value`.
        """
        token = utils_rand(10)
        await self.client.send_message(
            self.chat_id,
            prompt,
            buttons=Button.switch_inline(
                "Enter password", query=token, same_peer=True
            ),
        )
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._ask_state = (token, fut)
        try:
            return await fut
        finally:
            self._ask_state = None

    async def send_photo(self, png: bytes, caption: str):
        bio = io.BytesIO(png)
        bio.name = "qr.png"
        msg = await self.client.send_file(
            self.chat_id, file=bio, caption=caption, force_document=False
        )
        if self._qr_msg is None:
            self._qr_msg = msg
        else:
            # replace previous QR message, keep the chat clean
            with contextlib.suppress(Exception):
                await self._qr_msg.delete()
            self._qr_msg = msg
        return msg

    async def edit_photo(self, png: bytes, caption: str):
        """Replace QR in the same message instead of sending a new one."""
        if self._qr_msg is None:
            return await self.send_photo(png, caption)

        bio = io.BytesIO(png)
        bio.name = "qr.png"
        uploaded = await self.client.upload_file(bio)
        try:
            await self.client.edit_message(
                self.chat_id,
                self._qr_msg,
                text=caption,
                file=InputMediaPhoto(uploaded),
            )
        except Exception:
            # edit refused — fall back to a fresh message, the chat still
            # keeps exactly one QR
            await self.send_photo(png, caption)

    async def close(self):
        await self.client.disconnect()
