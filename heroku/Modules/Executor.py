# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

import asyncio
import contextlib
import itertools
import logging
import os
import time
import typing
from collections.abc import Callable
from io import StringIO
from types import ModuleType

from telethon.errors.rpcerrorlist import MessageIdInvalidError, MessageNotModifiedError
from telethon.tl.types import Message
from meval import meval

from .. import loader, main, utils

logger = logging.getLogger(__name__)


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




class MessageEditor:
    def __init__(self, message, command, strings):
        self.message = message
        self.command = command
        self.stdout = ""
        self.stderr = ""
        self.rc = None
        self.strings = strings
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




@loader.tds
class Executor(loader.Module):

    strings = {
        "name": "Executor",
        "running": "<b>Execution:</b> <code>{}</code>\n",
        "finished": "<b>With code:</b> <code>{}</code>",
        "stdout": "\n<pre><code class=\"language-stdout\">",
        "stderr": "</code></pre>\n<pre><code class=\"language-stderr\">",
        "end": "</code></pre>",
        "time_exec": "<b>Time:</b> <code>{}s</code>",
        "err": (
            "<b>Error</b>\n"
            "<blockquote>{}</blockquote>"
        ),
        "eval_py": (
            "<b>Code</b>\n"
            "<blockquote><code>{}</code></blockquote>\n"
        ),
        "eval_result": (
            "<b>Result</b>\n"
            "<pre><code class=\"language-python\">{}</code></pre>\n"
        ),
        "print_outp": (
            "<b>Print</b>\n"
            "<pre><code class=\"language-stdout\">{}</code></pre>\n"
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
        "exec_error": (
            "<b>Error</b>\n"
            "<blockquote>{}</blockquote>"
        ),
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

    async def client_ready(self, client, db):
        self._client = client
        self._db = db


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



    @loader.command()
    async def exec(self, message: Message):
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

        editor = MessageEditor(message, cmd, self.strings)
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
                    utils.escape_html(args),
                ) + (
                    self.strings["eval_result"].format(
                        utils.escape_html(str(result)),
                    ) if result or not print_output else ""
                ) + (
                    self.strings["print_outp"].format(
                        utils.escape_html(print_output),
                    ) if print_output else ""
                ) + self.strings["time_exec"].format(round(exec_time, 2)),
            )

    @loader.command()
    async def kill(self, message: Message):
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
