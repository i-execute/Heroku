# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

import asyncio
import atexit
import contextlib
import contextvars
import functools
import inspect
import logging
import os
import random
import signal
import sys
import subprocess
from collections.abc import Callable

client_id_ctx: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "heroku_client_id",
    default=None,
)

def get_client_id() -> int | None:
    return client_id_ctx.get()

def set_client_id(client_id: int | None):
    if isinstance(client_id, int):
        client_id_ctx.set(client_id)

def resolve_client_id(instance, path: str) -> int | None:
    value = instance
    for attr in path.split("."):
        value = getattr(value, attr, None)
        if value is None:
            return None

    return value if isinstance(value, int) else None

@contextlib.contextmanager
def client_id_override(client_id: int | None):
    token = client_id_ctx.set(client_id)
    try:
        yield
    finally:
        try:
            client_id_ctx.reset(token)
        except ValueError:
            pass

@contextlib.contextmanager
def client_id_scope(client_id: int | None):
    if not isinstance(client_id, int):
        yield
        return

    with client_id_override(client_id):
        yield

def tag_client_id(path: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(self, *args, **kwargs):
                with client_id_scope(resolve_client_id(self, path)):
                    return await func(self, *args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            with client_id_scope(resolve_client_id(self, path)):
                return func(self, *args, **kwargs)

        return wrapper

    return decorator

_background_tasks: set[asyncio.Task] = set()

def _track_task(task: asyncio.Task) -> asyncio.Task:
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task

def install_task_tracking():
    loop_cls = asyncio.base_events.BaseEventLoop
    if getattr(loop_cls.create_task, "_heroku_tracked", False):
        return

    original_create_task = loop_cls.create_task

    def create_task(self, coro, **kwargs):
        return _track_task(original_create_task(self, coro, **kwargs))

    create_task._heroku_tracked = True
    loop_cls.create_task = create_task

async def fw_protect():
    await asyncio.sleep(random.randint(1000, 2000) / 1000)

def get_startup_callback() -> Callable:
    return lambda *_: os.execl(
        sys.executable,
        sys.executable,
        "-m",
        os.path.relpath(os.path.abspath(os.path.dirname(os.path.abspath(__file__)))),
        *sys.argv[1:],
    )

def die():
    match True:
        case _ if "DOCKER" in os.environ:
            sys.exit(0)
        case _ if sys.platform == "win32":
            sys.exit(0)
        case _:
            os.killpg(os.getpgid(os.getpid()), signal.SIGTERM)

def restart():
    if "HEROKU_DO_NOT_RESTART2" in os.environ:
        sys.exit(0)

    logging.getLogger().setLevel(logging.CRITICAL)

    print(" Restarting...")

    if "HEROKU_DO_NOT_RESTART" not in os.environ:
        os.environ["HEROKU_DO_NOT_RESTART"] = "1"
    else:
        os.environ["HEROKU_DO_NOT_RESTART2"] = "1"

    if "DOCKER" in os.environ or sys.platform == "win32":
        atexit.register(get_startup_callback())
    else:
        signal.signal(signal.SIGTERM, get_startup_callback())
    die()


def get_branch_name(repo_path):
    branch_name = None

    try:
        import git

        with git.Repo(path=repo_path) as repo:
            branch_name = repo.active_branch.name
    except Exception:
        pass

    if not branch_name:
        try:
            head_path = os.path.join(repo_path, ".git", "HEAD")
            with open(head_path, encoding="utf-8") as f:
                content = f.read().strip()
            if content.startswith("ref:"):
                branch_name = content.split("/")[-1]
        except Exception:
            pass

    if not branch_name:
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0:
                candidate = proc.stdout.strip()
                if candidate:
                    branch_name = candidate
        except (subprocess.TimeoutExpired, Exception):
            pass

    if isinstance(branch_name, str):
        branch_name = branch_name.strip().lstrip("refs/heads/")

    return branch_name


