import asyncio
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import MemorySession
from telethon.tl import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from heroku._compat import install_telethon_compat
from telethon.client.messages import MessageMethods

install_telethon_compat()


class Client:
    def __init__(self):
        self.request = None
        self.session = type("Session", (), {"dc_id": 2})()

    async def _parse_message_text(self, text, parse_mode):
        return text, []

    async def _file_to_media(self, file, **kwargs):
        return None, file, False

    async def get_input_entity(self, entity):
        return types.InputPeerSelf()

    def build_reply_markup(self, buttons):
        return None

    async def __call__(self, request):
        self.request = request
        return object()

    def _get_response_message(self, request, result, entity):
        return request


async def main():
    client = Client()
    media = types.InputMediaWebPage("https://example.com/audio.mp3", optional=True)
    native = TelegramClient(MemorySession(), 1, "0" * 32)
    _, converted, _ = await native._file_to_media(media)
    assert converted is media
    request = await MessageMethods.edit_message(
        client,
        "me",
        1,
        "track",
        file=media,
        link_preview=True,
        invert_media=True,
    )
    assert request.invert_media is True
    assert request.no_webpage is False
    assert request.media is media


asyncio.run(main())
