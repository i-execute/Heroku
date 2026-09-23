# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

import asyncio
import contextlib
import inspect
import io
import linecache
import logging
import re
import sys
import traceback
import typing
import functools
from collections.abc import Coroutine

import telethon
from telethon.errors import PersistentTimestampOutdatedError, TimeoutError
from telethon.errors.rpcbaseerrors import ServerError, RPCError
from telethon.errors.rpcerrorlist import FloodWaitError

from . import utils
from ._internal import get_client_id
from .tl_cache import CustomTelegramClient
from .types import BotInlineCall, Module, CoreOverwriteError

INTERNET_ERRORS = (
    TimeoutError,
    asyncio.exceptions.TimeoutError,
    ServerError,
    PersistentTimestampOutdatedError,
)
COMMON_ERRORS = (
    "InputPeerEmpty() does not have any entity type",
    "https://docs.telethon.dev/en/stable/concepts/entities.html",
)
old = linecache.getlines

def getlines(filename: str, module_globals=None) -> str:
    try:
        if filename.startswith("<") and filename.endswith(">"):
            module = filename[1:-1].split(maxsplit=1)[-1]
            if (module.startswith("heroku.Modules")) and module in sys.modules:
                return list(
                    map(
                        lambda x: f"{x}\n",
                        sys.modules[module].__loader__.get_source().splitlines(),
                    )
                )
    except Exception:
        logging.debug("Can't get lines for %s", filename, exc_info=True)

    return old(filename, module_globals)

linecache.getlines = getlines

def override_text(exception: Exception) -> str | None:
    match exception:
        case TimeoutError() | asyncio.exceptions.TimeoutError():
            return (
                " <b>You have problems with internet connection on your server.</b>"
            )

        case PersistentTimestampOutdatedError():
            return " <b>Telegram has problems with their datacenters.</b>"

        case CoreOverwriteError():
            return f" {str(exception)}"

        case ServerError():
            return " <b>Telegram servers are currently experiencing issues. Please try again later.</b>"

        case RPCError() if "TRANSLATION_TIMEOUT" in str(exception):
            return " <b>Telegram translation service timed out. Please try again later.</b>"

        case ModuleNotFoundError():
            return f" {traceback.format_exception_only(type(exception), exception)[0].split(':')[1].strip()}"

        case FloodWaitError():
            return f" <b>Bot is hitting limits and got {exception.seconds} seconds floodwait</b>"

        case _:
            return None

class HerokuException:
    def __init__(
        self,
        message: str,
        full_stack: str,
        sysinfo: None | (tuple[object, Exception, traceback.TracebackException]) = None,
    ):
        self.message = message
        self.full_stack = full_stack
        self.sysinfo = sysinfo
        self.debug_url = None

    @classmethod
    def from_exc_info(
        cls,
        exc_type: object,
        exc_value: Exception,
        tb: traceback.TracebackException,
        stack: list[inspect.FrameInfo] | None = None,
        comment: typing.Any | None = None,
    ) -> "HerokuException":
        def to_hashable(dictionary: dict) -> dict:
            dictionary = dictionary.copy()
            for key, value in dictionary.items():
                match value:
                    case dict():
                        dictionary[key] = to_hashable(value)
                    case _ if (
                        getattr(getattr(value, "__class__", None), "__name__", None)
                        == "Database"
                    ):
                        dictionary[key] = "<Database>"
                    case telethon.TelegramClient() | CustomTelegramClient():
                        dictionary[key] = f"<{value.__class__.__name__}>"
                    case _:
                        try:
                            if len(str(value)) > 512:
                                dictionary[key] = f"{str(value)[:512]}..."
                            else:
                                dictionary[key] = str(value)
                        except Exception:
                            dictionary[key] = f"<{value.__class__.__name__}>"

            return dictionary

        full_traceback = traceback.format_exc().replace(
            "Traceback (most recent call last):\n",
            "",
        )

        line_regex = re.compile(r'  File "(.*?)", line ([0-9]+), in (.+)')

        def format_line(line: str) -> str:
            filename_, lineno_, name_ = line_regex.search(line).groups()

            return (
                f" <code>{utils.escape_html(filename_)}:{lineno_}</code> <b>in</b>"
                f" <code>{utils.escape_html(name_)}</code>"
            )

        filename, lineno, name = next(
            (
                line_regex.search(line).groups()
                for line in reversed(full_traceback.splitlines())
                if line_regex.search(line)
            ),
            (None, None, None),
        )

        full_traceback = "\n".join(
            [
                (
                    format_line(line)
                    if line_regex.search(line)
                    else f"<code>{utils.escape_html(line)}</code>"
                )
                for line in full_traceback.splitlines()
            ]
        )

        caller = utils.find_caller(stack or inspect.stack())

        return cls(
            message=override_text(exc_value)
            or (
                "{}<b> Source:</b> <code>{}:{}</code><b> in"
                ' </b><code>{}</code>\n<b> Error:</b> <pre><code class="language-python">{}</code></pre>{}'
            ).format(
                (
                    (
                        " <b>Cause: method </b><code>{}</code><b> of"
                        " </b><code>{}</code>\n\n"
                    ).format(
                        utils.escape_html(caller.__name__),
                        utils.escape_html(caller.__self__.__class__.__name__),
                    )
                    if (
                        caller
                        and hasattr(caller, "__self__")
                        and hasattr(caller, "__name__")
                    )
                    else ""
                ),
                utils.escape_html(filename),
                lineno,
                utils.escape_html(name),
                utils.escape_html(
                    "".join(
                        traceback.format_exception_only(exc_type, exc_value)
                    ).strip()
                ),
                (
                    "\n <b>Message:</b>"
                    f" <code>{utils.escape_html(str(comment))}</code>"
                    if comment
                    else ""
                ),
            ),
            full_stack=full_traceback,
            sysinfo=(exc_type, exc_value, tb),
        )

class TelegramLogsHandler(logging.Handler):
    def __init__(self, targets: list, capacity: int):
        super().__init__(0)
        self.buffer = []
        self.handledbuffer = []
        self._queue = []
        self._mod = None
        self.tg_buff = []
        self.force_send_all = False
        self.tg_level = 40
        self.ignore_common = True
        self.targets = targets
        self.capacity = capacity
        self.lvl = logging.NOTSET
        self._send_lock = asyncio.Lock()

    def install_tg_log(self, mod: Module):
        if getattr(self, "_task", False):
            self._task.cancel()

        self._mod = mod

        self._task = asyncio.ensure_future(self.queue_poller())

    async def queue_poller(self):
        while True:
            with contextlib.suppress(Exception):
                await self.sender()
            await asyncio.sleep(3)

    def setLevel(self, level: int):
        self.lvl = level

    def _min_tg_level(self) -> int:
        return self.tg_level

    def _common_ignored(self) -> bool:
        return self.ignore_common

    def _receives(self, item: tuple) -> bool:
        _, caller, levelno, common = item

        if levelno < self.tg_level:
            return False

        if common and self.ignore_common:
            return False

        return caller is None or self.force_send_all

    def dump(self):
        return self.handledbuffer + self.buffer

    def dumps(self, lvl: int = 0) -> list[str]:
        return [
            self.targets[0].format(record)
            for record in (self.buffer + self.handledbuffer)
            if record.levelno >= lvl
        ]

    async def _show_full_trace(
        self,
        call: BotInlineCall,
        bot,
        item: HerokuException,
    ):
        chunks = (
            item.message
            + "\n\n<b> Full traceback:</b>\n"
            + f'<pre><code class="language-python">{item.full_stack}</code></pre>'
        )

        chunks = list(utils.smart_split(*telethon.extensions.html.parse(chunks), 4096))

        await call.edit(chunks[0])

        thread_id = call.message.message_thread_id

        for chunk in chunks[1:]:
            await bot.send_message(
                chat_id=call.chat_id, text=chunk, message_thread_id=thread_id
            )

    @property
    def mod(self):
        return self._mod

    async def get_logs_topic_id(self) -> int | None:
        topic_id = await utils.get_topic_id(self._mod.db, "Logs")
        if not topic_id:
            topic = await utils.asset_forum_topic(
                self._mod.client,
                self._mod.db,
                self._mod.logchat,
                "Logs",
                " Inline logs and error reports will be stored here",
                5877307202888273539,
            )
            topic_id = topic.id
        return topic_id

    async def sender(self):
        async with self._send_lock:
            mod = self._mod
            if mod is None:
                return

            queue = utils.chunks(
                utils.escape_html(
                    "".join(
                        item[0]
                        for item in self.tg_buff
                        if isinstance(item[0], str) and self._receives(item)
                    )
                ),
                4096,
            )

            topic_id = await self.get_logs_topic_id()

            funcs = []
            for item in self.tg_buff:
                if not isinstance(item[0], HerokuException):
                    continue
                if not self._receives(item):
                    continue
                if isinstance(item[0].sysinfo[1], INTERNET_ERRORS) and getattr(
                    mod.lookup("tester"), "config", {}
                ).get("disable_internet_warn", False):
                    continue

                funcs.append(
                    functools.partial(
                        mod.inline.bot.send_message,
                        mod.logchat,
                        item[0].message,
                        reply_markup=mod.inline.generate_markup(
                            [
                                {
                                    "text": " Full traceback",
                                    "callback": self._show_full_trace, "style": "primary",
                                    "args": (
                                        mod.inline.bot,
                                        item[0],
                                    ),
                                    "disable_security": True,
                                },
                            ],
                        ),
                        message_thread_id=topic_id,
                    )
                )

            await self._exc_sender(*funcs)

            self.tg_buff = []

            if len(queue) > 5:
                logfile = io.BytesIO("".join(queue).encode("utf-8"))
                logfile.name = "heroku-logs.txt"
                logfile.seek(0)
                await mod.inline.bot.send_document(
                    mod.logchat,
                    logfile,
                    caption=(
                        "<b> Journals are too big to be sent as separate"
                        " messages</b>"
                    ),
                    message_thread_id=await self.get_logs_topic_id(),
                )

                return

            while queue:
                if chunk := queue.pop(0):
                    asyncio.ensure_future(
                        mod.inline.bot.send_message(
                            mod.logchat,
                            f"<code>{chunk}</code>",
                            disable_notification=True,
                            message_thread_id=await self.get_logs_topic_id(),
                        )
                    )

    async def _exc_sender(self, *funcs: typing.Callable[..., Coroutine]):
        for func in funcs:
            attempt = 0
            while attempt < 2:
                try:
                    await func()
                    break
                except FloodWaitError as e:
                    attempt += 1
                    await asyncio.sleep(e.seconds)
                except RuntimeError:
                    logging.debug(
                        "RuntimeError in sender, probably event loop is closed, skipping",
                        exc_info=True,
                    )
                    break
                except Exception:
                    logging.debug("Failed to send log message", exc_info=True)
                    break
            if attempt > 2:
                logging.debug(
                    "Failed to send log message after retries, skipping",
                    exc_info=True,
                )

    @staticmethod
    def _legacy_caller() -> int | None:
        frame = sys._getframe(1)

        while frame:
            tag = frame.f_locals.get("_heroku_client_id_logging_tag")
            if isinstance(tag, int):
                return tag

            frame = frame.f_back

        return None

    def emit(self, record: logging.LogRecord):
        try:
            caller = get_client_id()

            if caller is None:
                caller = self._legacy_caller()
        except Exception:
            caller = None

        record.heroku_caller = caller

        if record.levelno >= self._min_tg_level():
            if record.exc_info:
                try:
                    if record.args:
                        comment = record.msg % record.args
                    else:
                        comment = str(record.msg)
                except Exception:
                    comment = f"{record.msg} {record.args}"

                exc = HerokuException.from_exc_info(
                    *record.exc_info,
                    stack=record.__dict__.get("stack", None),
                    comment=comment,
                )

                common = any(field in exc.message for field in COMMON_ERRORS)

                if not common or not self._common_ignored():
                    self.tg_buff += [(exc, caller, record.levelno, common)]
            else:
                self.tg_buff += [
                    (
                        _tg_formatter.format(record),
                        caller,
                        record.levelno,
                        False,
                    )
                ]

        if len(self.buffer) + len(self.handledbuffer) >= self.capacity:
            if self.handledbuffer:
                del self.handledbuffer[0]
            else:
                del self.buffer[0]

        self.buffer.append(record)

        if record.levelno >= self.lvl >= 0:
            self.acquire()
            try:
                for precord in self.buffer:
                    for target in self.targets:
                        if record.levelno >= target.level:
                            target.handle(precord)

                self.handledbuffer = (
                    self.handledbuffer[-(self.capacity - len(self.buffer)) :]
                    + self.buffer
                )
                self.buffer = []
            finally:
                self.release()


_secrets: set[str] = set()


def register_secret(value) -> None:
    if value and len(str(value)) >= 8:
        _secrets.add(str(value))


def redact(text: str) -> str:
    text = str(text)
    for secret in sorted(_secrets.copy(), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        "[REDACTED PRIVATE KEY]", text, flags=re.S,
    )
    text = re.sub(r"\b\d{5,16}:[A-Za-z0-9_-]{30,}\b", "[REDACTED]", text)
    text = re.sub(r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{16,}\b", "[REDACTED]", text)
    text = re.sub(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9+/_.=-]+", r"\1 [REDACTED]", text)
    text = re.sub(r"(\w+://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    text = re.sub(
        r"(?i)([\"']?(?:[\w.-]*(?:token|password|passwd|secret|api_key|api_hash|"
        r"auth_key|session_string|basic_auth))[\"']?\s*[:=]\s*)"
        r"(?:\"[^\"]*\"|'[^']*'|[^\s&,;<>]+)",
        r"\1[REDACTED]", text,
    )
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


_main_formatter = RedactingFormatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    style="%",
)
_tg_formatter = RedactingFormatter(
    fmt="[%(levelname)s] %(name)s: %(message)s\n",
    datefmt=None,
    style="%",
)


def init():
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(_main_formatter)
    logging.getLogger().handlers = []
    logging.getLogger().addHandler(TelegramLogsHandler((handler,), 7000))
    logging.getLogger().setLevel(logging.NOTSET)
