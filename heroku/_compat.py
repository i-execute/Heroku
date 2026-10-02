# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka




import inspect
import sys
import types


async def _edit_message(
    self,
    entity,
    message=None,
    text=None,
    *,
    parse_mode=(),
    attributes=None,
    formatting_entities=None,
    link_preview=True,
    file=None,
    thumb=None,
    invert_media=False,
    force_document=False,
    buttons=None,
    supports_streaming=False,
    schedule=None,
):
    from telethon import functions, utils
    from telethon.tl import types as tl_types

    if isinstance(
        entity,
        (tl_types.InputBotInlineMessageID, tl_types.InputBotInlineMessageID64),
    ):
        text = text or message
        message = entity
    elif isinstance(entity, tl_types.Message):
        text = message
        message = entity
        entity = entity.peer_id
    if formatting_entities is None:
        text, formatting_entities = await self._parse_message_text(text, parse_mode)
    _, media, _ = await self._file_to_media(
        file,
        supports_streaming=supports_streaming,
        thumb=thumb,
        attributes=attributes,
        force_document=force_document,
    )
    if isinstance(
        entity,
        (tl_types.InputBotInlineMessageID, tl_types.InputBotInlineMessageID64),
    ):
        request = functions.messages.EditInlineBotMessageRequest(
            id=entity,
            message=text,
            no_webpage=not link_preview,
            invert_media=invert_media,
            entities=formatting_entities,
            media=media,
            reply_markup=self.build_reply_markup(buttons),
        )
        if self.session.dc_id != entity.dc_id:
            sender = await self._borrow_exported_sender(entity.dc_id)
            try:
                return await self._call(sender, request)
            finally:
                await self._return_exported_sender(sender)
        return await self(request)
    entity = await self.get_input_entity(entity)
    request = functions.messages.EditMessageRequest(
        peer=entity,
        id=utils.get_message_id(message),
        message=text,
        no_webpage=not link_preview,
        invert_media=invert_media,
        entities=formatting_entities,
        media=media,
        reply_markup=self.build_reply_markup(buttons),
        schedule_date=schedule,
    )
    return self._get_response_message(request, await self(request), entity)


def install_telethon_compat():
    from telethon.client.messages import MessageMethods

    if "invert_media" not in inspect.signature(MessageMethods.edit_message).parameters:
        MessageMethods.edit_message = _edit_message


class _HerokutlModule(types.ModuleType):
    def __getattr__(self, name: str):
        import telethon

        try:
            real = getattr(telethon, name)
        except AttributeError:
            raise AttributeError(f"module 'herokutl' has no attribute '{name}'") from None

        setattr(self, name, real)
        return real


def _install() -> None:
    if "herokutl" in sys.modules:
        return

    herokutl = _HerokutlModule("herokutl")
    herokutl.__path__ = []
    sys.modules["herokutl"] = herokutl


def _install_submodule(name: str) -> types.ModuleType:
    import telethon

    real = telethon
    for part in name.split("."):
        real = getattr(real, part)

    mod = sys.modules.get(f"herokutl.{name}")
    if mod is not None and type(mod) is _HerokutlModule:
        return mod

    mod = _HerokutlModule(f"herokutl.{name}")
    mod.__dict__.update(
        {k: v for k, v in vars(real).items() if not k.startswith("__")}
    )
    sys.modules[f"herokutl.{name}"] = mod
    return mod


_install()

for _path in (
    "errors",
    "errors.common",
    "errors.rpcerrorlist",
    "network",
    "network.requeststate",
    "tl",
    "tl.tlobject",
    "tl.types",
    "types",
):
    _install_submodule(_path)

install_telethon_compat()
