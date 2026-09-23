# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

__version__ = (2, 1, 3)
# meta developer: Execute_forge.t.me
# meta banner: https://raw.githubusercontent.com/i-execute/Modules/main/Storage/Info/MetaBanner.jpeg

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

import contextlib

from telethon.custom import Message
from telethon.tl.types import PeerUser, User
from telethon.utils import get_display_name

from .. import loader, main, utils
from ..inline.types import InlineCall

@loader.tds
class Security(loader.Module):
    """Control security settings"""

    strings = {
        "name": "Security",
        "owner_list": "<b>Users in group</b> <code>owner</code><b>:</b>\n\n<blockquote expandable>{}</blockquote>",
        "no_owner": "<b>There is no users in group</b> <code>owner</code>",
        "owner_removed": "<b><a href=\"tg://user?id={}\">{}</a> removed from group</b> <code>owner</code>",
        "no_user": "<b>Specify user to permit</b>",
        "not_a_user": "<b>Specified entity is not a user</b>",
        "li": " <b><a href=\"{}\">{}</a></b>",
        "warning": "<b>Please, confirm, that you want to add <a href=\"tg://user?id={}\">{}</a> to group</b> <code>{}</code><b>!\nThis action may reveal personal info and grant full or partial access to userbot to this user</b>",
        "cancel": "Cancel",
        "confirm": "Confirm",
        "self": "<b>You can't promote/demote yourself!</b>",
        "suggest_nonick": "<i>Do you want to enable NoNick for this user?</i>",
        "user_nn": "<b>NoNick for <a href=\"tg://user?id={}\">{}</a> enabled</b>",
        "_cmd_doc_owneradd": "[-f|--force] [-n|--nonick] <user> - Add user to `owner`",
        "_cmd_doc_ownerlist": "List users in `owner`",
        "_cmd_doc_ownerrm": "<user> - Remove user from `owner`",
        "_cls_doc": "Control security settings",
    }

    async def _resolve_user(self, message: Message, args_raw: str = None):
        args = (utils.get_args_raw(message) if args_raw is None else args_raw).replace(
            "@", ""
        )
        reply = None

        if not args and not (reply := await message.get_reply_message()):
            await utils.answer(message, self.strings["no_user"])
            return

        user = None

        if args:
            with contextlib.suppress(Exception):
                if str(args).isdigit():
                    args = int(args)

                user = await self._client.get_entity(args, exp=0)

        if user is None:
            if reply is None:
                reply = await message.get_reply_message()

            if reply is not None:
                try:
                    user = await self._client.get_entity(reply.sender_id, exp=0)
                except ValueError:
                    user = await reply.get_sender()

        if user is None:
            await utils.answer(message, self.strings["no_user"])
            return

        if not isinstance(user, (User, PeerUser)):
            await utils.answer(message, self.strings["not_a_user"])
            return

        if user.id == self.tg_id:
            await utils.answer(message, self.strings["self"])
            return

        return user

    async def _add_to_group(
        self,
        message: Message | InlineCall,
        group: str,
        confirmed: bool = False,
        user: int = None,
        enable_nonick: bool = False,
        force: bool = False,
    ):
        if user is None and not (user := await self._resolve_user(message)):
            return

        if isinstance(user, int):
            user = await self._client.get_entity(user, exp=0)

        if not confirmed and not force:
            await self.inline.form(
                self.strings["warning"].format(
                    user.id,
                    utils.escape_html(get_display_name(user)),
                    group,
                ),
                message=message,
                ttl=10 * 60,
                reply_markup=[
                    {
                        "text": self.strings["cancel"],
                        "action": "close", "style": "primary",
                    },
                    {
                        "text": self.strings["confirm"],
                        "callback": self._add_to_group, "style": "primary",
                        "args": (group, True, user.id, enable_nonick),
                    },
                ],
            )
            return

        if user.id not in getattr(self._client.dispatcher.security, group):
            getattr(self._client.dispatcher.security, group).append(user.id)
            self._client.dispatcher.security._reload_rights(force=True)

        if enable_nonick:
            self._db.set(
                main.__name__,
                "nonickusers",
                list(set(self._db.get(main.__name__, "nonickusers", []) + [user.id])),
            )

            await utils.answer(
                message,
                self.strings[f"{group}_added"].format(
                    user.id,
                    utils.escape_html(get_display_name(user)),
                )
                + "\n\n"
                + self.strings["user_nn"].format(
                    user.id,
                    utils.escape_html(get_display_name(user)),
                ),
            )
            return

        await utils.answer(
            message,
            (
                self.strings[f"{group}_added"].format(
                    user.id,
                    utils.escape_html(get_display_name(user)),
                )
                + "\n\n"
                + self.strings["suggest_nonick"]
            ),
            reply_markup=[
                {
                    "text": self.strings["cancel"],
                    "action": "close",
                    "style": "primary",
                },
            ],
        )

    @loader.command()
    async def owneradd(self, message: Message):
        args = utils.get_args(message)
        force = any(arg in {"-f", "--force"} for arg in args)
        enable_nonick = any(arg in {"-n", "--nonick"} for arg in args)
        user_args = " ".join(
            arg for arg in args if arg not in {"-f", "--force", "-n", "--nonick"}
        )
        user = await self._resolve_user(message, user_args)

        if not user:
            return

        await self._add_to_group(
            message,
            "owner",
            user=user.id,
            enable_nonick=enable_nonick,
            force=force,
        )

    @loader.command()
    async def ownerrm(self, message: Message):
        if not (user := await self._resolve_user(message)):
            return

        if user.id in self._client.dispatcher.security.owner:
            self._client.dispatcher.security.owner.remove(user.id)
            self._client.dispatcher.security._reload_rights(force=True)

        await utils.answer(
            message,
            self.strings["owner_removed"].format(
                user.id,
                utils.escape_html(get_display_name(user)),
            ),
        )

    @loader.command()
    async def ownerlist(self, message: Message):
        _resolved_users = []
        _and_prefixes = []
        for user in set(self._client.dispatcher.security.owner + [self.tg_id]):
            with contextlib.suppress(Exception):
                _resolved_users += [await self._client.get_entity(user, exp=0)]

        if not _resolved_users:
            await utils.answer(message, self.strings["no_owner"])
            return

        prefixes = self._db.get(main.__name__, "command_prefixes", {})
        for user in _resolved_users:
            _and_prefixes += [prefixes.get(str(user.id), None)]

        await utils.answer(
            message,
            self.strings["owner_list"].format(
                "\n".join(
                    [
                        self.strings["li"].format(
                            utils.get_entity_url(i), utils.escape_html(get_display_name(i))
                        )
                        + (f" ({p})" if p else "")
                        for i, p in zip(_resolved_users, _and_prefixes)
                    ]
                )
            ),
        )
