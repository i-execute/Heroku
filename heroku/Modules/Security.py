import contextlib

from telethon.tl.custom import Message
from telethon.tl.types import User
from telethon.utils import get_display_name

from .. import loader, utils
from ..inline.types import InlineCall


@loader.tds
class Security(loader.Module):
    strings = {
        "name": "Security",
        "title": (
            "<b>Owner access</b>\n"
            "<blockquote>Owners can execute every userbot command and access private data.</blockquote>\n"
            "<b>Accounts:</b> <code>{count}</code>"
        ),
        "detail": (
            "<b>Owner account</b>\n"
            "<blockquote><b>Name:</b> <a href=\"{url}\">{name}</a>\n"
            "<b>ID:</b> <code>{user_id}</code>\n"
            "<b>Role:</b> {role}</blockquote>"
        ),
        "confirm_add": (
            "<b>Grant owner access?</b>\n"
            "<blockquote><a href=\"{url}\">{name}</a> will receive unrestricted access to the userbot and its data.</blockquote>"
        ),
        "confirm_remove": (
            "<b>Remove owner access?</b>\n"
            "<blockquote><a href=\"{url}\">{name}</a> will no longer be able to execute owner commands.</blockquote>"
        ),
        "invalid_user": (
            "<b>User not found</b>\n"
            "<blockquote>Enter a Telegram ID or username.</blockquote>"
        ),
        "self_user": (
            "<b>Primary owner</b>\n"
            "<blockquote>Your own account cannot be added or removed.</blockquote>"
        ),
        "already_owner": (
            "<b>Already an owner</b>\n"
            "<blockquote>This account already has owner access.</blockquote>"
        ),
        "added": "Owner access granted",
        "removed": "Owner access removed",
        "primary": "Primary owner",
        "additional": "Additional owner",
        "add": "Add owner",
        "remove": "Remove owner",
        "confirm": "Confirm",
        "back": "Back",
        "close": "Close",
        "input": "Enter Telegram ID or username",
        "_cmd_doc_owner": "Open owner access management",
        "_cls_doc": "Manage owner access",
    }

    async def _resolve(self, value: str):
        value = value.strip().removeprefix("@")
        if not value:
            return None
        entity = int(value) if value.lstrip("-").isdigit() else value
        with contextlib.suppress(Exception):
            user = await self._client.get_entity(entity, exp=0)
            if isinstance(user, User):
                return user
        return None

    async def _owners(self) -> list[User]:
        ids = [self.tg_id] + list(self._client.dispatcher.security.owner)
        users = []
        for user_id in dict.fromkeys(ids):
            with contextlib.suppress(Exception):
                user = await self._client.get_entity(user_id, exp=0)
                if isinstance(user, User):
                    users.append(user)
        return users

    async def _show(self, call: InlineCall, page: int = 0):
        users = await self._owners()
        page_size = 8
        pages = max(1, (len(users) + page_size - 1) // page_size)
        page = max(0, min(page, pages - 1))
        rows = [
            [
                {
                    "text": get_display_name(user) or str(user.id),
                    "callback": self._detail,
                    "args": (user.id, page),
                    "style": "primary",
                }
            ]
            for user in users[page * page_size : (page + 1) * page_size]
        ]
        navigation = []
        if page > 0:
            navigation.append(
                {
                    "text": "←",
                    "callback": self._show,
                    "args": (page - 1,),
                    "style": "primary",
                }
            )
        if page < pages - 1:
            navigation.append(
                {
                    "text": "→",
                    "callback": self._show,
                    "args": (page + 1,),
                    "style": "primary",
                }
            )
        if navigation:
            rows.append(navigation)
        rows.extend(
            [
                [
                    {
                        "text": self.strings["add"],
                        "input": self.strings["input"],
                        "handler": self._add_input,
                        "style": "success",
                    }
                ],
                [
                    {
                        "text": self.strings["close"],
                        "action": "close",
                        "style": "danger",
                    }
                ],
            ]
        )
        await call.edit(
            self.strings["title"].format(count=len(users)),
            reply_markup=rows,
        )

    async def _detail(self, call: InlineCall, user_id: int, page: int = 0):
        user = await self._resolve(str(user_id))
        if user is None:
            await self._show(call, page)
            return
        role = self.strings["primary"] if user.id == self.tg_id else self.strings["additional"]
        rows = []
        if user.id != self.tg_id:
            rows.append(
                [
                    {
                        "text": self.strings["remove"],
                        "callback": self._remove_confirm,
                        "args": (user.id, page),
                        "style": "danger",
                    }
                ]
            )
        rows.append(
            [
                {
                    "text": self.strings["back"],
                    "callback": self._show,
                    "args": (page,),
                    "style": "primary",
                }
            ]
        )
        await call.edit(
            self.strings["detail"].format(
                url=utils.get_entity_url(user),
                name=utils.escape_html(get_display_name(user)),
                user_id=user.id,
                role=role,
            ),
            reply_markup=rows,
        )

    async def _add_input(self, call: InlineCall, query: str):
        user = await self._resolve(query)
        if user is None:
            await call.edit(
                self.strings["invalid_user"],
                reply_markup=[
                    [
                        {
                            "text": self.strings["back"],
                            "callback": self._show,
                            "style": "primary",
                        }
                    ]
                ],
            )
            return
        if user.id == self.tg_id:
            await call.edit(
                self.strings["self_user"],
                reply_markup=[
                    [
                        {
                            "text": self.strings["back"],
                            "callback": self._show,
                            "style": "primary",
                        }
                    ]
                ],
            )
            return
        if user.id in self._client.dispatcher.security.owner:
            await call.edit(
                self.strings["already_owner"],
                reply_markup=[
                    [
                        {
                            "text": self.strings["back"],
                            "callback": self._show,
                            "style": "primary",
                        }
                    ]
                ],
            )
            return
        await call.edit(
            self.strings["confirm_add"].format(
                url=utils.get_entity_url(user),
                name=utils.escape_html(get_display_name(user)),
            ),
            reply_markup=[
                [
                    {
                        "text": self.strings["confirm"],
                        "callback": self._add,
                        "args": (user.id,),
                        "style": "success",
                    },
                    {
                        "text": self.strings["back"],
                        "callback": self._show,
                        "style": "danger",
                    },
                ]
            ],
        )

    async def _add(self, call: InlineCall, user_id: int):
        owners = self._client.dispatcher.security.owner
        if user_id != self.tg_id and user_id not in owners:
            owners.append(user_id)
            self._client.dispatcher.security._reload_rights(force=True)
        await call.answer(self.strings["added"])
        await self._show(call)

    async def _remove_confirm(self, call: InlineCall, user_id: int, page: int = 0):
        user = await self._resolve(str(user_id))
        if user is None or user.id == self.tg_id:
            await self._show(call, page)
            return
        await call.edit(
            self.strings["confirm_remove"].format(
                url=utils.get_entity_url(user),
                name=utils.escape_html(get_display_name(user)),
            ),
            reply_markup=[
                [
                    {
                        "text": self.strings["confirm"],
                        "callback": self._remove,
                        "args": (user.id,),
                        "style": "danger",
                    },
                    {
                        "text": self.strings["back"],
                        "callback": self._detail,
                        "args": (user.id, page),
                        "style": "primary",
                    },
                ]
            ],
        )

    async def _remove(self, call: InlineCall, user_id: int):
        owners = self._client.dispatcher.security.owner
        if user_id in owners:
            owners.remove(user_id)
            self._client.dispatcher.security._reload_rights(force=True)
        await call.answer(self.strings["removed"])
        await self._show(call)

    @loader.command()
    async def owner(self, message: Message):
        form = await self.inline.form(
            self.strings["title"].format(count=len(await self._owners())),
            message=message,
            reply_markup=[
                [
                    {
                        "text": self.strings["close"],
                        "action": "close",
                        "style": "danger",
                    }
                ]
            ],
        )
        if form:
            await self._show(form)
