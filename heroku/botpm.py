import asyncio
import contextlib
import hashlib
import io

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.custom.button import Button
from telethon.tl.types import UpdateBotInlineSend

from .utils.other import rand as utils_rand


class BotPM:
    def __init__(self, api_id: int, api_hash: str, token: str):
        self.token = token
        self.client = TelegramClient(
            StringSession(), api_id, api_hash, connection_retries=None
        )
        self.chat_id: int | None = None
        self.owner_id: int | None = None
        self._ask_state: tuple | None = None
        self._choice_state: asyncio.Future | None = None
        self._qr_msg = None
        self.inline_messages = []

    async def start(self):
        await self.client.start(bot_token=self.token)
        self.client.add_event_handler(self._on_iq, events.InlineQuery())
        self.client.add_event_handler(self._on_callback, events.CallbackQuery())
        self.client.add_event_handler(
            self._on_inline_send, events.Raw(types=UpdateBotInlineSend)
        )
        return await self.client.get_me()

    async def _on_iq(self, event):
        state = self._ask_state
        if not state:
            return
        token, _, label, marker = state
        if self.owner_id and event.query.user_id != self.owner_id:
            return
        text = event.text or ""
        parts = text.split(maxsplit=1)
        if not parts or parts[0] != token:
            return
        await event.answer(
            [
                await event.builder.article(
                    label,
                    description=label,
                    text=marker,
                    parse_mode=None,
                    id=hashlib.sha256(text.encode()).hexdigest(),
                )
            ],
            cache_time=0,
            private=True,
        )

    async def _on_inline_send(self, update):
        state = self._ask_state
        if not state:
            return
        token, fut, *_ = state
        if fut.done() or self.owner_id and update.user_id != self.owner_id:
            return
        query = getattr(update, "query", "") or ""
        parts = query.split(maxsplit=1)
        if len(parts) < 2 or parts[0] != token:
            return
        if getattr(update, "msg_id", None) is not None:
            self.inline_messages.append(update.msg_id)
        fut.set_result(parts[1])

    async def _on_callback(self, event):
        if not self._choice_state or self._choice_state.done():
            return
        if self.owner_id and event.sender_id != self.owner_id:
            await event.answer("Not for you", alert=True)
            return
        data = event.data.decode(errors="ignore")
        if data not in {"auth_qr", "auth_phone"}:
            return
        self._choice_state.set_result(data.removeprefix("auth_"))
        await event.answer()
        with contextlib.suppress(Exception):
            await event.delete()

    def _bind_owner_id(self, expected_id: int | None) -> None:
        waiter = asyncio.get_running_loop().create_future()

        @self.client.on(events.NewMessage(pattern=r"^/start"))
        async def _on_start(event):
            if expected_id and event.sender_id != expected_id:
                with contextlib.suppress(Exception):
                    await event.reply("Not for you")
                return
            if not waiter.done():
                self.chat_id = event.chat_id
                waiter.set_result(event.chat_id)

        self._waiter = waiter

    def start_echo(self):
        @self.client.on(events.NewMessage(pattern=r"^/start"))
        async def _echo(event):
            with contextlib.suppress(Exception):
                await event.reply(f"Your Telegram ID is {event.sender_id}")

        self._echo_handler = _echo

    def stop_echo(self):
        if getattr(self, "_echo_handler", None):
            self.client.remove_event_handler(self._echo_handler)
            self._echo_handler = None

    async def wait_start(self, expected_id: int | None = None) -> int:
        self._bind_owner_id(expected_id)
        return await self._waiter

    async def send(self, text: str):
        return await self.client.send_message(
            self.chat_id,
            text,
            buttons=Button.clear(),
        )

    async def choose_auth(self) -> str:
        self._choice_state = asyncio.get_running_loop().create_future()
        await self.client.send_message(
            self.chat_id,
            "Choose the login method",
            buttons=[
                [
                    Button.inline("QR code", b"auth_qr", style="primary"),
                    Button.inline("Phone number", b"auth_phone", style="success"),
                ]
            ],
        )
        try:
            return await self._choice_state
        finally:
            self._choice_state = None

    async def ask(
        self,
        prompt: str,
        label: str = "Enter value",
        marker: str = "📝",
    ) -> str:
        token = utils_rand(10)
        fut = asyncio.get_running_loop().create_future()
        self._ask_state = (token, fut, label, marker)
        await self.client.send_message(
            self.chat_id,
            prompt,
            buttons=Button.switch_inline(
                label, query=token, same_peer=True, style="primary"
            ),
        )
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
        if self._qr_msg is not None:
            with contextlib.suppress(Exception):
                await self._qr_msg.delete()
        self._qr_msg = msg
        return msg

    async def edit_photo(self, png: bytes, caption: str):
        if self._qr_msg is None:
            return await self.send_photo(png, caption)
        bio = io.BytesIO(png)
        bio.name = "qr.png"
        try:
            self._qr_msg = await self.client.edit_message(
                self.chat_id,
                self._qr_msg,
                text=caption,
                file=bio,
            )
            return self._qr_msg
        except Exception:
            return await self.send_photo(png, caption)

    async def close(self):
        await self.client.disconnect()
