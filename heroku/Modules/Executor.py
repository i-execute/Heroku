# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

import asyncio
import contextlib
import itertools
import logging
import os
import sys
import time
import typing
from collections.abc import Callable
from io import StringIO
from types import ModuleType

from telethon.errors.rpcerrorlist import MessageIdInvalidError, MessageNotModifiedError
from telethon.sessions import StringSession
from telethon.tl.types import Message
from meval import meval

from .. import loader, main, utils

logger = logging.getLogger(__name__)

BANNER_OK = "https://raw.githubusercontent.com/i-execute/Heroku/main/Storage/TerminalOK.png"
BANNER_BAD = "https://raw.githubusercontent.com/i-execute/Heroku/main/Storage/TerminalBad.png"


def hash_msg(message):
    return f"{str(utils.get_chat_id(message))}/{str(message.id)}"


async def read_stream(func: Callable, stream, delay: float):
    last_task = None
    data = b""
    while True:
        dat = await stream.read(1)
        if not dat:
            if last_task:
                last_task.cancel()
                await func(data.decode())
            break
        data += dat
        if last_task:
            last_task.cancel()
        last_task = asyncio.ensure_future(_sleep_for_task(func, data, delay))


async def _sleep_for_task(func: Callable, data: bytes, delay: float):
    await asyncio.sleep(delay)
    await func(data.decode())


class _ShellSession:
    def __init__(self):
        self.process: asyncio.subprocess.Process | None = None
        self.stdout = ""
        self.last_cmd: str | None = None
        self._stream_task: asyncio.Task | None = None

    async def start(self):
        shell = os.environ.get("SHELL", "/bin/bash")
        self.process = await asyncio.create_subprocess_exec(
            shell,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=utils.get_base_dir(),
            env={**os.environ, "TERM": "dumb", "PS1": "$ ", "PS2": ""},
        )
        self.stdout = ""

    def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def send(self, cmd: str):
        if not self.is_alive():
            await self.start()
        self.last_cmd = cmd
        self.process.stdin.write(cmd.strip().encode() + b"\n")
        await self.process.stdin.drain()

    def send_signal(self, sig: int):
        if self.is_alive():
            with contextlib.suppress(Exception):
                self.process.send_signal(sig)

    async def send_eof(self):
        if self.is_alive():
            with contextlib.suppress(Exception):
                self.process.stdin.write(b"\x04")
                await self.process.stdin.drain()

    async def kill(self):
        if self._stream_task:
            self._stream_task.cancel()
            self._stream_task = None
        if self.process:
            with contextlib.suppress(Exception):
                self.process.kill()
            self.process = None

    def append_output(self, data: str):
        self.stdout += data
        if len(self.stdout) > 8000:
            self.stdout = self.stdout[-8000:]


class MessageEditor:
    def __init__(self, message, command, config, strings, request_message):
        self.message = message
        self.command = command
        self.stdout = ""
        self.stderr = ""
        self.rc = None
        self.config = config
        self.strings = strings
        self.request_message = request_message
        self.start_time = time.time()

    async def update_stdout(self, stdout):
        self.stdout = stdout
        await self.redraw()

    async def update_stderr(self, stderr):
        self.stderr = stderr
        await self.redraw()

    async def redraw(self):
        text = self.strings["running"].format(utils.escape_html(self.command))

        if self.rc is not None:
            text += self.strings["finished"].format(utils.escape_html(str(self.rc)))

        stdout = utils.escape_html(self.stdout[max(len(self.stdout) - 2048, 0):])
        stderr = utils.escape_html(self.stderr[max(len(self.stderr) - 1024, 0):])

        text += self.strings["stdout"]
        text += stdout
        text += (self.strings["stderr"] + stderr) if stderr else ""
        text += self.strings["end"]

        if self.rc is not None:
            exec_time = time.time() - self.start_time
            text += self.strings["time_exec"].format(round(exec_time, 2))

        with contextlib.suppress(MessageNotModifiedError):
            try:
                self.message = await utils.answer(self.message, text)
            except Exception as e:
                logger.error(e)

    async def cmd_ended(self, rc):
        self.rc = rc
        await self.redraw()

    def update_process(self, process):
        pass


class InlineShellEditor:
    def __init__(self, form, session: "_ShellSession", strings, config):
        self.form = form
        self.session = session
        self.strings = strings
        self.config = config

    async def run_cmd(self, cmd: str, uid: str):
        if self.session._stream_task and not self.session._stream_task.done():
            self.session._stream_task.cancel()

        self.session.stdout = ""
        await self.session.send(cmd)
        await self.redraw(uid)

        self.session._stream_task = asyncio.ensure_future(
            self._stream_output(uid)
        )

    async def _stream_output(self, uid: str):
        buf = b""
        while self.session.is_alive():
            try:
                chunk = await asyncio.wait_for(
                    self.session.process.stdout.read(256),
                    timeout=0.3,
                )
                if not chunk:
                    break
                buf += chunk
                self.session.append_output(buf.decode(errors="replace"))
                buf = b""
                await self.redraw(uid)
                await asyncio.sleep(self.config["FLOOD_WAIT_PROTECT"])
            except asyncio.TimeoutError:
                if buf:
                    self.session.append_output(buf.decode(errors="replace"))
                    buf = b""
                    await self.redraw(uid)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[Executor] stream error: {e}")
                break

    async def redraw(self, uid: str):
        cmd = self.session.last_cmd or ""
        out = self.session.stdout
        text = (
            self.strings["shell_running"].format(utils.escape_html(cmd))
            + '<pre><code class="language-stdout">'
            + utils.escape_html(out[max(len(out) - 3000, 0):])
            + "</code></pre>"
        )
        with contextlib.suppress(Exception):
            await self.form.edit(text, reply_markup=self._markup(uid))

    def _markup(self, uid: str) -> list:
        return [
            [
                {"text": "Ctrl+C", "data": f"executor/sig/int/{uid}"},
                {"text": "Ctrl+Z", "data": f"executor/sig/tstp/{uid}"},
                {"text": "Ctrl+D", "data": f"executor/sig/eof/{uid}"},
                {"text": "Ctrl+\\", "data": f"executor/sig/quit/{uid}"},
            ],
            [
                {
                    "text": self.strings["btn_continue"],
                    "input": self.strings["btn_continue"],
                    "handler": None,
                    "data": f"executor/input/{uid}",
                }
            ],
            [
                {
                    "text": self.strings["btn_kill"],
                    "data": f"executor/kill/{uid}",
                    "style": "danger",
                }
            ],
        ]


@loader.tds
class Executor(loader.Module):
    """Python evaluator and interactive terminal"""

    strings = {
        "name": "Executor",
        "running": "<b>Execution:</b> <code>{}</code>\n",
        "finished": "<b>With code:</b> <code>{}</code>",
        "stdout": "\n<pre><code class=\"language-stdout\">",
        "stderr": "</code></pre>\n<pre><code class=\"language-stderr\">",
        "end": "</code></pre>",
        "time_exec": "\n<b>Time:</b> <code>{}s</code>",
        "err": (
            "<b>Error</b>\n"
            "<blockquote>{}</blockquote>"
        ),
        "eval_py": (
            "<b>Code</b>\n"
            "<blockquote><code>{2}</code></blockquote>\n"
        ),
        "eval_result": (
            "<b>Result</b>\n"
            "<pre><code class=\"language-python\">{1}</code></pre>\n"
        ),
        "print_outp": (
            "<b>Print</b>\n"
            "<pre><code class=\"language-stdout\">{1}</code></pre>\n"
        ),
        "what_to_kill": (
            "<b>Error</b>\n"
            "<blockquote>Reply to a running command message</blockquote>"
        ),
        "no_cmd": (
            "<b>Error</b>\n"
            "<blockquote>No active command found in reply</blockquote>"
        ),
        "killed": (
            "<b>Killed</b>\n"
            "<blockquote>Process terminated</blockquote>"
        ),
        "kill_fail": (
            "<b>Error</b>\n"
            "<blockquote>Failed to kill process</blockquote>"
        ),
        "dangerous_command": (
            "<b>Blocked</b>\n"
            "<blockquote>Dangerous command: <code>{}</code></blockquote>"
        ),
        "no_args": (
            "<b>Error</b>\n"
            "<blockquote>No code provided</blockquote>"
        ),
        "shell_running": "<b>Shell:</b> <code>{}</code>\n\n",
        "shell_killed": "<b>Shell session killed</b>",
        "exec_confirm": (
            "<b>Execute</b>\n"
            "<blockquote><code>{}</code></blockquote>"
        ),
        "exec_running": "<b>Shell starting...</b>",
        "exec_error": (
            "<b>Error</b>\n"
            "<blockquote>{}</blockquote>"
        ),
        "inline_hint": "exec",
        "inline_hint_desc": "Type command after exec",
        "btn_execute": "Execute",
        "btn_continue": "Command:",
        "btn_kill": "Kill",
        "fw_protect": "Flood wait protection delay in seconds",
        "command_protect": "Block dangerous commands",
    }

    COMMAND_PROTECT = "command_protect"
    DANGEROUS_RM_TARGETS = {
        "/", "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64",
        "/opt", "/proc", "/root", "/sbin", "/sys", "/usr", "/var",
    }
    DANGEROUS_COMMANDS = [
        r"dd\s+.*if=.*of=/dev/",
        r"mkfs\.",
        r"fdisk\s+\/dev/",
        r"chmod\s+.*000\s+.*\/",
        r":\(\)\s*\{\s*:\|:&\s*\}\s*;\s*:",
        r"curl\s+.*\|\s*(sh|bash|zsh|dash|ksh)",
        r"wget\s+.*-O\s*-\s*\|\s*(sh|bash|zsh|dash|ksh)",
        r"nc\s+.*-e\s+(sh|bash|zsh)",
        r"python[23]?\s+-c\s+[\"']import\s+os",
        r"kill\s+-9\s+1\b",
        r"shred\s+",
    ]

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "FLOOD_WAIT_PROTECT",
                2,
                lambda: self.strings["fw_protect"],
                validator=loader.validators.Integer(minimum=0),
            ),
            loader.ConfigValue(
                self.COMMAND_PROTECT,
                True,
                lambda: self.strings["command_protect"],
                validator=loader.validators.Boolean(),
            ),
        )
        self.activecmds: dict = {}
        self._inline_pending: dict = {}
        self._shell_sessions: dict = {}
        self._shell_editors: dict = {}

    async def client_ready(self, client, db):
        self._client = client
        self._db = db

    async def on_unload(self):
        for session in self._shell_sessions.values():
            await session.kill()

    def _is_dangerous(self, cmd: str) -> bool:
        if not self.config[self.COMMAND_PROTECT]:
            return False
        import re
        import shlex
        try:
            tokens = list(shlex.shlex(cmd, posix=True, punctuation_chars=True))
        except ValueError:
            tokens = []
        rm_names = {"rm", "/bin/rm", "/usr/bin/rm"}
        separators = {";", "&&", "||", "|", "&"}
        for idx, tok in enumerate(tokens):
            if tok not in rm_names:
                continue
            for target in tokens[idx + 1:]:
                if target in separators:
                    break
                if target == "--":
                    continue
                if os.path.normpath(target.rstrip()) in self.DANGEROUS_RM_TARGETS:
                    return True
        for pattern in self.DANGEROUS_COMMANDS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True
        return False

    def _register_inline_unit(self, uid: str, inline_message_id: str):
        self.inline._units[uid] = {
            "type": "form",
            "text": self.strings["exec_running"],
            "buttons": [],
            "caller": None,
            "chat": None,
            "message_id": None,
            "top_msg_id": None,
            "uid": uid,
            "inline_message_id": inline_message_id,
        }

    async def _get_or_create_shell(self, uid: str) -> _ShellSession:
        if uid not in self._shell_sessions or not self._shell_sessions[uid].is_alive():
            session = _ShellSession()
            await session.start()
            self._shell_sessions[uid] = session
        return self._shell_sessions[uid]

    @loader.command()
    async def exec(self, message: Message):
        """Run a shell command"""
        cmd = utils.get_args_raw(message)
        reply = await message.get_reply_message()
        if not cmd and reply and reply.text:
            cmd = reply.message
        if not cmd:
            await utils.answer(message, self.strings["no_args"])
            return
        if self._is_dangerous(cmd):
            await utils.answer(
                message,
                self.strings["dangerous_command"].format(utils.escape_html(cmd)),
            )
            return
        await self._run_cmd(message, cmd)

    async def _run_cmd(self, message: Message, cmd: str):
        shell = os.environ.get("SHELL", "/bin/sh")
        utils.ensure_child_watcher()
        try:
            sproc = await asyncio.create_subprocess_exec(
                shell, "-c", cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=utils.get_base_dir(),
                preexec_fn=os.setsid,
            )
        except Exception as e:
            await utils.answer(
                message,
                self.strings["exec_error"].format(utils.escape_html(str(e))),
            )
            return

        editor = MessageEditor(message, cmd, self.config, self.strings, message)
        editor.update_process(sproc)
        self.activecmds[hash_msg(message)] = sproc

        await editor.redraw()
        await asyncio.gather(
            read_stream(editor.update_stdout, sproc.stdout, self.config["FLOOD_WAIT_PROTECT"]),
            read_stream(editor.update_stderr, sproc.stderr, self.config["FLOOD_WAIT_PROTECT"]),
        )
        await editor.cmd_ended(await sproc.wait())
        self.activecmds.pop(hash_msg(message), None)

    @loader.command()
    async def e(self, message: Message):
        """Evaluate Python code"""
        args = utils.get_args_raw(message)
        reply = await message.get_reply_message()
        if not args and reply and reply.text:
            args = reply.message
        if not args:
            await utils.answer(message, self.strings["no_args"])
            return

        args = args.replace("\xa0", "\x20")
        skip_output = args.startswith(("-so ", "--skip-output "))
        if skip_output:
            args = args.split(" ", 1)[1]

        output_print = StringIO()

        try:
            start_time = time.time()
            with contextlib.redirect_stdout(output_print):
                result = await meval(args, globals(), **await self._getattrs(message))
            print_output = output_print.getvalue()
        except Exception:
            import traceback
            print_output = output_print.getvalue()
            tb = traceback.format_exc()
            await utils.answer(
                message,
                self.strings["err"].format(utils.escape_html(tb))
                + (
                    self.strings["print_outp"].format(
                        "python",
                        utils.escape_html(print_output),
                    ) if print_output else ""
                ),
            )
            return

        if skip_output:
            return

        if callable(getattr(result, "stringify", None)):
            with contextlib.suppress(Exception):
                result = str(result.stringify())

        exec_time = time.time() - start_time

        with contextlib.suppress(MessageIdInvalidError):
            await utils.answer(
                message,
                self.strings["eval_py"].format(
                    None, None, utils.escape_html(args),
                ) + (
                    self.strings["eval_result"].format(
                        "python",
                        utils.escape_html(str(result)),
                    ) if result or not print_output else ""
                ) + (
                    self.strings["print_outp"].format(
                        "python",
                        utils.escape_html(print_output),
                    ) if print_output else ""
                ) + self.strings["time_exec"].format(round(exec_time, 2)),
            )

    @loader.command()
    async def kill(self, message: Message):
        """Kill a running command - reply to its message"""
        if not message.is_reply:
            await utils.answer(message, self.strings["what_to_kill"])
            return
        reply = await message.get_reply_message()
        if not reply:
            await utils.answer(message, self.strings["no_cmd"])
            return
        process = self.activecmds.get(hash_msg(reply))
        if process is None:
            await utils.answer(message, self.strings["no_cmd"])
            return
        import signal
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except Exception:
            await utils.answer(message, self.strings["kill_fail"])
        else:
            await utils.answer(message, self.strings["killed"])

    @loader.inline_handler()
    async def exec_inline_handler(self, query):
        """Start an interactive shell session"""
        raw = query.query.strip()
        if raw.lower().startswith("exec"):
            raw = raw[4:].strip()

        def short(cmd: str) -> str:
            return cmd[:20] + "..." if len(cmd) > 20 else cmd

        if not raw:
            await query.answer(
                [
                    await query.builder.article(
                        title=self.strings["inline_hint"],
                        description=self.strings["inline_hint_desc"],
                        text=self.strings["inline_hint"],
                        parse_mode="HTML",
                        thumb=self.inline._web_document(BANNER_OK, width=640, height=640),
                        id="hint",
                    )
                ],
                cache_time=0,
                private=True,
            )
            return

        if self._is_dangerous(raw):
            await query.answer(
                [
                    await query.builder.article(
                        title="Blocked",
                        description=short(raw),
                        text=self.strings["dangerous_command"].format(utils.escape_html(raw)),
                        parse_mode="HTML",
                        thumb=self.inline._web_document(BANNER_BAD, width=640, height=640),
                        id="dangerous",
                    )
                ],
                cache_time=0,
                private=True,
            )
            return

        uid = utils.rand(8)
        self._inline_pending[uid] = raw

        await query.answer(
            [
                await query.builder.article(
                    title=self.strings["inline_hint"],
                    description=short(raw),
                    text=self.strings["exec_confirm"].format(utils.escape_html(raw)),
                    parse_mode="HTML",
                    thumb=self.inline._web_document(BANNER_OK, width=640, height=640),
                    buttons=self.inline.generate_markup([
                        [{"text": self.strings["btn_execute"], "data": f"executor/exec/{uid}"}]
                    ]),
                    id=uid,
                )
            ],
            cache_time=0,
            private=True,
        )

    @loader.callback_handler()
    async def executor_callback(self, call):
        """Handle executor inline callbacks"""
        data = call.data

        if data.startswith("executor/exec/"):
            uid = data.split("/")[2]
            cmd = self._inline_pending.pop(uid, None)
            if not cmd:
                await call.answer("Expired", show_alert=True)
                return
            if self._is_dangerous(cmd):
                await call.answer("Blocked", show_alert=True)
                return

            self._register_inline_unit(uid, call.inline_message_id)

            from ..inline.types import InlineMessage
            form = InlineMessage(
                inline_manager=self.inline,
                unit_id=uid,
                inline_message_id=call.inline_message_id,
            )

            session = await self._get_or_create_shell(uid)
            editor = InlineShellEditor(form, session, self.strings, self.config)
            self._shell_editors[uid] = editor

            asyncio.ensure_future(editor.run_cmd(cmd, uid))
            return

        if data.startswith("executor/sig/"):
            parts = data.split("/")
            sig_name = parts[2]
            uid = parts[3]
            session = self._shell_sessions.get(uid)
            if not session:
                await call.answer("No session", show_alert=True)
                return
            import signal
            sig_map = {
                "int": signal.SIGINT,
                "tstp": signal.SIGTSTP,
                "quit": signal.SIGQUIT,
            }
            if sig_name == "eof":
                await session.send_eof()
            else:
                sig = sig_map.get(sig_name)
                if sig:
                    session.send_signal(sig)
            await call.answer()
            return

        if data.startswith("executor/kill/"):
            uid = data.split("/")[2]
            session = self._shell_sessions.pop(uid, None)
            editor = self._shell_editors.pop(uid, None)
            if session:
                await session.kill()
            if editor:
                with contextlib.suppress(Exception):
                    await editor.form.edit(self.strings["shell_killed"], reply_markup=[])
            else:
                await call.answer("Killed", show_alert=True)
            return

        if data.startswith("executor/input/"):
            uid = data.split("/")[2]
            editor = self._shell_editors.get(uid)
            if not editor:
                await call.answer("No session", show_alert=True)
                return
            await call.answer()
            return

    async def inline__continue_input(self, call, query: str, uid: str):
        """Continue shell session with next command"""
        editor = self._shell_editors.get(uid)
        if not editor:
            return
        cmd = query.strip()
        if not cmd:
            return
        if self._is_dangerous(cmd):
            with contextlib.suppress(Exception):
                await editor.form.edit(
                    self.strings["dangerous_command"].format(utils.escape_html(cmd)),
                    reply_markup=editor._markup(uid),
                )
            return
        asyncio.ensure_future(editor.run_cmd(cmd, uid))

    async def _getattrs(self, message: Message) -> dict:
        reply = await message.get_reply_message()
        return {
            "message": message,
            "client": self._client,
            "reply": reply,
            "r": reply,
            "event": message,
            "chat": message.to_id,
            "telethon": __import__("telethon"),
            "utils": utils,
            "main": main,
            "loader": loader,
            "c": self._client,
            "m": message,
            "lookup": self.lookup,
            "self": self,
            "db": self.db,
            **self._get_sub(__import__("telethon").tl.functions),
            **self._get_sub(__import__("telethon").tl.types),
        }

    def _get_sub(self, obj: typing.Any, _depth: int = 1) -> dict:
        return {
            **dict(filter(
                lambda x: x[0][0] != "_" and x[0][0].upper() == x[0][0] and callable(x[1]),
                obj.__dict__.items(),
            )),
            **dict(itertools.chain.from_iterable([
                self._get_sub(y[1], _depth + 1).items()
                for y in filter(
                    lambda x: x[0][0] != "_"
                    and isinstance(x[1], ModuleType)
                    and x[1] != obj
                    and x[1].__package__.rsplit(".", _depth)[0] == "telethon.tl",
                    obj.__dict__.items(),
                )
            ])),
        }