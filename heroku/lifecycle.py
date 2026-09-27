# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

"""
Global kill switch of the userbot (`.disable` / `.enable`).

`.disable` puts Heroku into the *dormant* state, which means:

* every event handler is detached from the main client, except **one**
  watcher, which does nothing but wait for `.enable`;
* the inline bot stops processing any updates (handlers are detached too);
* every module loop (``@loader.loop``) is stopped;
* every asyncio task owned by a module is cancelled;
* every child process spawned by the userbot is killed;
* modules are notified with the ``on_disable`` hook, so they can shut
  their own stuff down gracefully (works exactly like ``client_ready``).

`.enable` rolls everything back and notifies modules with ``on_enable``.

The state is persistent. If the userbot is restarted (or crashes) while
disabled, it boots straight into the dormant state: no loops, no watchers,
no handlers - only the `.enable` watcher, which accepts the command from
the owner himself or from any member of the ``owner`` security group.
"""

import asyncio
import contextlib
import logging
import os
import time
import typing

if typing.TYPE_CHECKING:
    from .database import Database
    from .tl_cache import CustomTelegramClient

logger = logging.getLogger(__name__)

#: Database scope of the flag (`heroku.main`). Imported lazily - this module
#: must stay importable from `heroku.dispatcher`, which `heroku.main` imports
MAIN_SCOPE = f"{__package__}.main"

#: Key of the persistent flag. Kept in the `heroku.main` scope for backwards
#: compatibility - a lot of core parts read it directly.
DISABLED_FLAG = "heroku_disabled"

#: Key of the persistent dormant-state payload (`lifecycle.__name__` scope)
STATE_KEY = "disable_state"

#: Legacy (pre-lifecycle) storage of stopped loops
LEGACY_LOOPS_OWNER = "heroku.disabled_loops"
LEGACY_LOOPS_KEY = "modules"

#: How long a single `on_disable`/`on_enable` hook may run
HOOK_TIMEOUT = 15.0

#: How long to wait for loops to actually stop
LOOP_STOP_TIMEOUT = 5.0

#: How long to wait for killed children to die
CHILD_KILL_TIMEOUT = 3.0


class _SafeDict(dict):
    """`str.format_map` helper, which keeps unknown placeholders as is"""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class LifecycleReport(typing.NamedTuple):
    """Result of a `.disable`/`.enable` call"""

    action: str
    changed: bool
    loops: int = 0
    modules: int = 0
    handlers: int = 0
    tasks: int = 0
    children: int = 0
    inline: bool = False

    @property
    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "changed": self.changed,
            "loops": self.loops,
            "modules": self.modules,
            "handlers": self.handlers,
            "tasks": self.tasks,
            "children": self.children,
            "inline": "yes" if self.inline else "no",
        }


class LifecycleManager:
    """
    Owns the dormant state of the userbot.

    Single instance per client, available as ``client.lifecycle`` and as
    ``client.dispatcher.lifecycle``.
    """

    def __init__(self, client: "CustomTelegramClient", db: "Database"):
        self._client = client
        self._db = db
        self._lock = asyncio.Lock()
        self._startup_applied = False

    # ------------------------------------------------------------------ #
    # Lazy references (everything is created in different places of main) #
    # ------------------------------------------------------------------ #

    @property
    def _modules(self):
        return getattr(self._client, "loader", None)

    @property
    def _dispatcher(self):
        return getattr(self._client, "dispatcher", None)

    @property
    def _inline(self):
        return getattr(self._client, "heroku_inline", None)

    @property
    def _security(self):
        return getattr(self._dispatcher, "security", None)

    # ------------------------------------------------------------------ #
    # State                                                              #
    # ------------------------------------------------------------------ #

    @property
    def disabled(self) -> bool:
        """Whether the userbot is currently in the dormant state"""
        return bool(self._db.get(MAIN_SCOPE, DISABLED_FLAG, False))

    @property
    def state(self) -> dict:
        state = self._db.get(__name__, STATE_KEY, {})
        return state if isinstance(state, dict) else {}

    def _set_flag(self, value: bool):
        self._db.set(MAIN_SCOPE, DISABLED_FLAG, bool(value))

    def _save_state(self, **kwargs):
        self._db.set(__name__, STATE_KEY, kwargs)

    def _drop_state(self):
        self._db.set(__name__, STATE_KEY, {})
        if self._db.get(LEGACY_LOOPS_OWNER, LEGACY_LOOPS_KEY, None) is not None:
            self._db.set(LEGACY_LOOPS_OWNER, LEGACY_LOOPS_KEY, [])

    # ------------------------------------------------------------------ #
    # Permissions                                                        #
    # ------------------------------------------------------------------ #

    @property
    def trusted_ids(self) -> set[int]:
        """Users allowed to revive the userbot: owner + `owner` sec. group"""
        trusted = {int(getattr(self._client, "tg_id", 0) or 0)}

        security = self._security
        if security is not None:
            with contextlib.suppress(Exception):
                trusted |= {int(user_id) for user_id in security.owner}

        trusted.discard(0)
        return trusted

    def is_trusted(self, user_id: int | None) -> bool:
        """Whether `user_id` may use `.enable` while the userbot is dormant"""
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return False

        return user_id in self.trusted_ids

    # ------------------------------------------------------------------ #
    # Strings (taken from the `Updater` module, if it is loaded)          #
    # ------------------------------------------------------------------ #

    def _prefix(self) -> str:
        modules = self._modules
        if modules is not None:
            with contextlib.suppress(Exception):
                return modules.get_prefix()

        return self._db.get(MAIN_SCOPE, "command_prefix", ".")

    def string(self, key: str, default: str, **kwargs) -> str:
        """
        Get a user-facing string.

        Strings live in the `Updater` module (so they can be translated
        and edited in one place), but they must be available even when
        the module is not loaded - hence the `default`.
        """
        text = default

        modules = self._modules
        if modules is not None:
            with contextlib.suppress(Exception):
                mod = modules.lookup("Updater")
                if mod and key in mod.strings:
                    text = mod.strings[key]

        with contextlib.suppress(Exception):
            text = text.format_map(_SafeDict(prefix=self._prefix(), **kwargs))

        return text

    # ------------------------------------------------------------------ #
    # Loops                                                              #
    # ------------------------------------------------------------------ #

    def _iter_loops(self) -> typing.Iterator[tuple[typing.Any, str, typing.Any]]:
        from .loader import InfiniteLoop

        modules = self._modules
        if modules is None:
            return

        for mod in list(getattr(modules, "modules", [])):
            for name in dir(mod):
                try:
                    method = getattr(mod, name)
                except Exception:
                    continue

                if isinstance(method, InfiniteLoop):
                    yield mod, name, method

    @staticmethod
    def _loop_is_running(loop: typing.Any) -> bool:
        task = getattr(loop, "_task", None)
        return bool(task) and not task.done()

    def _snapshot_loops(self) -> list[list[str]]:
        return [
            [mod.__class__.__name__, name]
            for mod, name, loop in self._iter_loops()
            if self._loop_is_running(loop)
        ]

    async def _stop_loops(self) -> int:
        stopped = []

        for mod, name, loop in self._iter_loops():
            if not self._loop_is_running(loop):
                continue

            logger.debug(
                "Stopping loop %s.%s because of .disable",
                mod.__class__.__name__,
                name,
            )

            try:
                stopped.append(loop.stop())
            except Exception:
                logger.exception("Failed to stop loop %s.%s", mod, name)

        if stopped:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    asyncio.gather(*stopped, return_exceptions=True),
                    timeout=LOOP_STOP_TIMEOUT,
                )

        return len(stopped)

    def _restore_loops(self) -> int:
        saved = self.state.get("loops") or []
        wanted = {
            (str(item[0]), str(item[1]))
            for item in saved
            if isinstance(item, (list, tuple)) and len(item) == 2
        }

        # Legacy format: only module names were stored
        legacy = self._db.get(LEGACY_LOOPS_OWNER, LEGACY_LOOPS_KEY, [])
        legacy = {str(name) for name in legacy} if isinstance(legacy, list) else set()

        started = 0

        for mod, name, loop in self._iter_loops():
            if self._loop_is_running(loop):
                continue

            classname = mod.__class__.__name__

            if (
                (classname, name) not in wanted
                and classname not in legacy
                and not getattr(loop, "autostart", False)
            ):
                continue

            try:
                loop.start()
                started += 1
                logger.debug("Restored loop %s.%s after .enable", classname, name)
            except Exception:
                logger.exception("Failed to restore loop %s.%s", classname, name)

        return started

    # ------------------------------------------------------------------ #
    # Tasks                                                              #
    # ------------------------------------------------------------------ #

    def _owned_module_names(self) -> set[str]:
        modules = self._modules
        if modules is None:
            return set()

        owned = set()

        for mod in [
            *list(getattr(modules, "modules", [])),
            *list(getattr(modules, "libraries", [])),
        ]:
            name = getattr(type(mod), "__module__", None)
            if name:
                owned.add(name)

        return owned

    @staticmethod
    def _task_module(task: asyncio.Task) -> str | None:
        coro = None
        with contextlib.suppress(Exception):
            coro = task.get_coro()

        if coro is None:
            return None

        frame = getattr(coro, "cr_frame", None) or getattr(coro, "gi_frame", None)
        if frame is not None:
            return frame.f_globals.get("__name__")

        return getattr(coro, "__module__", None)

    def _cancel_tasks(self) -> int:
        current = asyncio.current_task()
        cancelled = 0

        dispatcher = self._dispatcher
        pending = set(getattr(dispatcher, "pending_tasks", set()) or set())

        for task in pending:
            if task is current or task.done():
                continue

            task.cancel()
            cancelled += 1

        owned = self._owned_module_names()
        if owned:
            try:
                alive = asyncio.all_tasks()
            except RuntimeError:
                alive = set()

            for task in alive:
                if task is current or task.done() or task in pending:
                    continue

                if self._task_module(task) in owned:
                    logger.debug("Cancelling module task %s", task)
                    task.cancel()
                    cancelled += 1

        return cancelled

    # ------------------------------------------------------------------ #
    # Child processes                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _kill_children() -> int:
        try:
            import psutil
        except ImportError:
            logger.warning("psutil is not installed, can't kill child processes")
            return 0

        try:
            proc = psutil.Process(os.getpid())
            children = proc.children(recursive=True)
        except Exception:
            logger.exception("Failed to enumerate child processes")
            return 0

        killed = []

        for child in children:
            try:
                child.kill()
                killed.append(child)
            except psutil.Error:
                continue
            except Exception:
                logger.debug("Failed to kill %s", child, exc_info=True)

        if killed:
            with contextlib.suppress(Exception):
                psutil.wait_procs(killed, timeout=CHILD_KILL_TIMEOUT)

        return len(killed)

    # ------------------------------------------------------------------ #
    # Inline bot                                                         #
    # ------------------------------------------------------------------ #

    async def _suspend_inline(self) -> bool:
        inline = self._inline
        if inline is None or not hasattr(inline, "suspend"):
            return False

        try:
            return bool(await inline.suspend())
        except Exception:
            logger.exception("Failed to suspend inline bot")
            return False

    async def _resume_inline(self) -> bool:
        inline = self._inline
        if inline is None or not hasattr(inline, "resume"):
            return False

        try:
            return bool(await inline.resume())
        except Exception:
            logger.exception("Failed to resume inline bot")
            return False

    # ------------------------------------------------------------------ #
    # Hooks                                                              #
    # ------------------------------------------------------------------ #

    async def _fire_hook(self, hook: str) -> int:
        modules = self._modules
        if modules is None or not hasattr(modules, "fire_lifecycle_hook"):
            return 0

        try:
            return len(await modules.fire_lifecycle_hook(hook))
        except Exception:
            logger.exception("Failed to broadcast %s hook", hook)
            return 0

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    async def disable(self, initiator: int | None = None) -> LifecycleReport:
        """
        Hard-off the userbot, leaving only the `.enable` watcher alive.

        :param initiator: id of the user, who requested the shutdown
        :return: report about everything, which was killed
        """
        async with self._lock:
            if self.disabled:
                return LifecycleReport("disable", False)

            logger.warning("Disabling userbot (initiator=%s)", initiator)

            # 1. Persist the flag first: every other part of the core checks
            #    it, so even if something below explodes, we stay off
            self._set_flag(True)
            self._save_state(
                loops=self._snapshot_loops(),
                since=int(time.time()),
                initiator=int(initiator or 0),
            )

            # 2. Detach every handler, leaving the single `.enable` watcher
            handlers = 0
            dispatcher = self._dispatcher
            if dispatcher is not None:
                handlers = dispatcher.enter_dormant()

            # 3. Notify modules while the client is still fully functional
            notified = await self._fire_hook("on_disable")

            # 4. Kill everything the modules left behind
            loops = await self._stop_loops()
            inline = await self._suspend_inline()
            tasks = self._cancel_tasks()
            children = self._kill_children()

            logger.warning(
                (
                    "Userbot disabled: %s handlers detached, %s loops stopped, %s"
                    " tasks cancelled, %s children killed, %s modules notified"
                ),
                handlers,
                loops,
                tasks,
                children,
                notified,
            )

            return LifecycleReport(
                action="disable",
                changed=True,
                loops=loops,
                modules=notified,
                handlers=handlers,
                tasks=tasks,
                children=children,
                inline=inline,
            )

    async def enable(self, initiator: int | None = None) -> LifecycleReport:
        """
        Revive the userbot after `.disable`.

        :param initiator: id of the user, who requested the revival
        :return: report about everything, which was restored
        """
        async with self._lock:
            if not self.disabled:
                return LifecycleReport("enable", False)

            logger.warning("Enabling userbot (initiator=%s)", initiator)

            self._set_flag(False)

            handlers = 0
            dispatcher = self._dispatcher
            if dispatcher is not None:
                handlers = dispatcher.leave_dormant()

            inline = await self._resume_inline()
            loops = self._restore_loops()
            notified = await self._fire_hook("on_enable")

            self._drop_state()
            self._startup_applied = False

            logger.warning(
                (
                    "Userbot enabled: %s handlers restored, %s loops started, %s"
                    " modules notified"
                ),
                handlers,
                loops,
                notified,
            )

            return LifecycleReport(
                action="enable",
                changed=True,
                loops=loops,
                modules=notified,
                handlers=handlers,
                inline=inline,
            )

    async def apply_startup_state(self) -> bool:
        """
        Called once on boot, after all modules are loaded.

        If the userbot was disabled before the restart, it must not come
        back to life on its own: stop everything modules could have started
        in `client_ready` and notify them with `on_disable`.
        """
        if not self.disabled or self._startup_applied:
            return False

        self._startup_applied = True
        logger.warning("Userbot is disabled, booting into dormant state")

        dispatcher = self._dispatcher
        if dispatcher is not None and not dispatcher.dormant:
            dispatcher.enter_dormant()

        await self._fire_hook("on_disable")
        await self._stop_loops()
        await self._suspend_inline()
        self._cancel_tasks()

        return True
