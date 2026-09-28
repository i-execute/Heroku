# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

# (c) Dan Gazizullin, 2021-2023. This file is part of the Hikka Userbot: github.com/hikariatama/Hikka

import functools
import re
import typing
from collections.abc import Callable

import grapheme
import emoji

from . import utils
_VALIDATORS_STRINGS = {
    "validators.boolean": "boolean",
    "validators.positive": "positive",
    "validators.negative": "negative",
    "validators.digits": "with exactly {digits} digits",
    "validators.integer_min": "{sign}integer greater than {minimum}{digits}",
    "validators.integer_range": "{sign}integer from {minimum} to {maximum}{digits}",
    "validators.integer": "{sign}integer{digits}",
    "validators.integer_max": "{sign}integer less than {maximum}{digits}",
    "validators.choice": "one of the following: {possible}",
    "validators.multichoice": "list of values, where each one must be one of: {possible}",
    "validators.each": "(each must be {each})",
    "validators.fixed_len": "(exactly {fixed_len} pcs.)",
    "validators.max_len": "(up to {max_len} pcs.)",
    "validators.len_range": "(from {min_len} to {max_len} pcs.)",
    "validators.min_len": "(at least {min_len} pcs.)",
    "validators.series": "series of values{len}{each}, separated with «,»",
    "validators.link": "link",
    "validators.string_fixed_len": "string of length {length}",
    "validators.string": "string",
    "validators.string_max_len": "string of length up to {max_len}",
    "validators.string_len_range": "string of length from {min_len} to {max_len}",
    "validators.string_min_len": "string of length at least {min_len}",
    "validators.regex": "string matching pattern «{regex}»",
    "validators.float_min": "{sign}float greater than {minimum}",
    "validators.float_range": "{sign}float from {minimum} to {maximum}",
    "validators.float": "{sign}float",
    "validators.float_max": "{sign}float less than {maximum}",
    "validators.union": "one of the following:",
    "validators.empty": "empty value",
    "validators.emoji_fixed_len": "{length} emojis",
    "validators.emoji_len_range": "{min_len} to {max_len} emojis",
    "validators.emoji_min_len": "at least {min_len} emoji",
    "validators.emoji_max_len": "no more than {max_len} emojis",
    "validators.emoji": "emoji",
    "validators.entity_like": "link to entity, username or Telegram ID",
}

ConfigAllowedTypes = typing.Union[tuple, list, str, int, bool, None]

ALLOWED_EMOJIS = set(emoji.EMOJI_DATA.keys())

def _getdict(key: str, **kwargs) -> dict:
    return {"en": _VALIDATORS_STRINGS[key].format(**kwargs) if kwargs else _VALIDATORS_STRINGS[key]}


class ValidationError(Exception):
    pass
class Validator:
    def __init__(
        self,
        validator: Callable,
        doc: str | dict | None = None,
        _internal_id: int | None = None,
    ):
        self.validate = validator

        if isinstance(doc, str):
            doc = {'en': doc}

        self.doc = doc
        self.internal_id = _internal_id

class Boolean(Validator):
    _TRUE_VALUES = frozenset(
        ("True", "true", "1", 1, True, "yes", "Yes", "on", "On", "y", "Y")
    )
    _FALSE_VALUES = frozenset(
        ("False", "false", "0", 0, False, "no", "No", "off", "Off", "n", "N")
    )
    _ALL_VALUES = _TRUE_VALUES | _FALSE_VALUES

    def __init__(self):
        super().__init__(
            self._validate,
            _getdict("validators.boolean"),
            _internal_id="Boolean",
        )

    @staticmethod
    def _validate(value: ConfigAllowedTypes, /) -> bool:
        if value not in Boolean._ALL_VALUES:
            raise ValidationError("Passed value must be a boolean")

        return value in Boolean._TRUE_VALUES

class Integer(Validator):
    def __init__(
        self,
        *,
        digits: int | None = None,
        minimum: int | None = None,
        maximum: int | None = None,
    ):
        _signs = (
            _getdict("validators.positive")
            if minimum is not None and minimum == 0
            else (
                _getdict("validators.negative")
                if maximum is not None and maximum == 0
                else {}
            )
        )
        _digits = (
            _getdict("validators.digits", digits=digits)
            if digits is not None
            else {}
        )

        match True:
            case _ if minimum is not None and minimum != 0:
                doc = (
                    {
                        lang: text.format(
                            sign=_signs.get(lang, ""),
                            digits=_digits.get(lang, ""),
                            minimum=minimum,
                        )
                        for lang, text in _getdict(
                            "validators.integer_min"
                        ).items()
                    }
                    if maximum is None and maximum != 0
                    else {
                        lang: text.format(
                            sign=_signs.get(lang, ""),
                            digits=_digits.get(lang, ""),
                            minimum=minimum,
                            maximum=maximum,
                        )
                        for lang, text in _getdict(
                            "validators.integer_range"
                        ).items()
                    }
                )
            case _ if maximum is None and maximum != 0:
                doc = {
                    lang: text.format(
                        sign=_signs.get(lang, ""), digits=_digits.get(lang, "")
                    )
                    for lang, text in _getdict("validators.integer").items()
                }
            case _:
                doc = {
                    lang: text.format(
                        sign=_signs.get(lang, ""),
                        digits=_digits.get(lang, ""),
                        maximum=maximum,
                    )
                    for lang, text in _getdict(
                        "validators.integer_max"
                    ).items()
                }

        super().__init__(
            functools.partial(
                self._validate,
                digits=digits,
                minimum=minimum,
                maximum=maximum,
            ),
            doc,
            _internal_id="Integer",
        )

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        /,
        *,
        digits: int,
        minimum: int,
        maximum: int,
    ) -> int | None:
        try:
            value = int(str(value).strip())
        except ValueError:
            raise ValidationError(f"Passed value ({value}) must be a number")

        if minimum is not None and value < minimum:
            raise ValidationError(f"Passed value ({value}) is lower than minimum one")

        if maximum is not None and value > maximum:
            raise ValidationError(f"Passed value ({value}) is greater than maximum one")

        if digits is not None and len(str(value)) != digits:
            raise ValidationError(
                f"The length of passed value ({value}) is incorrect "
                f"(Must be exactly {digits} digits)"
            )

        return value

class Choice(Validator):
    def __init__(
        self,
        possible_values: list[ConfigAllowedTypes],
        /,
    ):
        super().__init__(
            functools.partial(self._validate, possible_values=possible_values),
            _getdict(
                "validators.choice",
                possible=" / ".join(list(map(str, possible_values))),
            ),
            _internal_id="Choice",
        )

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        /,
        *,
        possible_values: list[ConfigAllowedTypes],
    ) -> ConfigAllowedTypes:
        if value not in possible_values:
            raise ValidationError(
                f"Passed value ({value}) is not one of the following:"
                f" {' / '.join(list(map(str, possible_values)))}"
            )

        return value

class MultiChoice(Validator):
    def __init__(
        self,
        possible_values: list[ConfigAllowedTypes],
        /,
    ):
        possible = " / ".join(list(map(str, possible_values)))
        super().__init__(
            functools.partial(self._validate, possible_values=possible_values),
            _getdict("validators.multichoice", possible=possible),
            _internal_id="MultiChoice",
        )

    @staticmethod
    def _validate(
        value: list[ConfigAllowedTypes],
        /,
        *,
        possible_values: list[ConfigAllowedTypes],
    ) -> list[ConfigAllowedTypes]:
        if not isinstance(value, (list, tuple)):
            value = [value]

        for item in value:
            if item not in possible_values:
                raise ValidationError(
                    f"One of passed values ({item}) is not one of the following:"
                    f" {' / '.join(list(map(str, possible_values)))}"
                )

        return list(set(value))

class Series(Validator):
    def __init__(
        self,
        validator: Validator | None = None,
        min_len: int | None = None,
        max_len: int | None = None,
        fixed_len: int | None = None,
    ):
        def trans(lang: str) -> str:
            return validator.doc.get(lang, validator.doc["en"])

        _each = (
            {
                lang: text.format(each=trans(lang))
                for lang, text in _getdict("validators.each").items()
            }
            if validator is not None
            else {}
        )

        match True:
            case _ if fixed_len is not None:
                _len = _getdict("validators.fixed_len", fixed_len=fixed_len)
            case _ if min_len is None:
                if max_len is None:
                    _len = {}
                else:
                    _len = _getdict("validators.max_len", max_len=max_len)
            case _ if max_len is not None:
                _len = _getdict(
                    "validators.len_range", min_len=min_len, max_len=max_len
                )
            case _:
                _len = _getdict("validators.min_len", min_len=min_len)

        super().__init__(
            functools.partial(
                self._validate,
                validator=validator,
                min_len=min_len,
                max_len=max_len,
                fixed_len=fixed_len,
            ),
            {
                lang: text.format(each=_each.get(lang, ""), len=_len.get(lang, ""))
                for lang, text in _getdict("validators.series").items()
            },
            _internal_id="Series",
        )

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        /,
        *,
        validator: Validator | None = None,
        min_len: int | None = None,
        max_len: int | None = None,
        fixed_len: int | None = None,
    ) -> list[ConfigAllowedTypes]:
        if not isinstance(value, (list, tuple, set)):
            value = str(value).split(",")

        if isinstance(value, (tuple, set)):
            value = list(value)

        if min_len is not None and len(value) < min_len:
            raise ValidationError(
                f"Passed value ({value}) contains less than {min_len} items"
            )

        if max_len is not None and len(value) > max_len:
            raise ValidationError(
                f"Passed value ({value}) contains more than {max_len} items"
            )

        if fixed_len is not None and len(value) != fixed_len:
            raise ValidationError(
                f"Passed value ({value}) must contain exactly {fixed_len} items"
            )

        value = [item.strip() if isinstance(item, str) else item for item in value]

        if isinstance(validator, Validator):
            for i, item in enumerate(value):
                try:
                    value[i] = validator.validate(item)
                except ValidationError:
                    raise ValidationError(
                        f"Passed value ({value}) contains invalid item"
                        f" ({str(item).strip()}), which must be {validator.doc['en']}"
                    )

        value = list(filter(lambda x: x, value))

        return value

class Link(Validator):
    def __init__(self):
        super().__init__(
            lambda value: self._validate(value),
            _getdict("validators.link"),
            _internal_id="Link",
        )

    @staticmethod
    def _validate(value: ConfigAllowedTypes, /) -> str:
        try:
            if not utils.check_url(value):
                raise Exception("Invalid URL")
        except Exception:
            raise ValidationError(f"Passed value ({value}) is not a valid URL")

        return value

class String(Validator):
    def __init__(
        self,
        length: int | None = None,
        min_len: int | None = None,
        max_len: int | None = None,
    ):
        if length is not None:
            doc = _getdict("validators.string_fixed_len", length=length)
        else:
            match True:
                case _ if min_len is None:
                    if max_len is None:
                        doc = _getdict("validators.string")
                    else:
                        doc = _getdict(
                            "validators.string_max_len", max_len=max_len
                        )
                case _ if max_len is not None:
                    doc = _getdict(
                        "validators.string_len_range", min_len=min_len, max_len=max_len
                    )
                case _:
                    doc = _getdict(
                        "validators.string_min_len", min_len=min_len
                    )

        super().__init__(
            functools.partial(
                self._validate,
                length=length,
                min_len=min_len,
                max_len=max_len,
            ),
            doc,
            _internal_id="String",
        )

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        /,
        *,
        length: int | None,
        min_len: int | None,
        max_len: int | None,
    ) -> str:
        if (
            isinstance(length, int)
            and len(list(grapheme.graphemes(str(value)))) != length
        ):
            raise ValidationError(
                f"Passed value ({value}) must be a length of {length}"
            )

        if (
            isinstance(min_len, int)
            and len(list(grapheme.graphemes(str(value)))) < min_len
        ):
            raise ValidationError(
                f"Passed value ({value}) must be a length of at least {min_len}"
            )

        if (
            isinstance(max_len, int)
            and len(list(grapheme.graphemes(str(value)))) > max_len
        ):
            raise ValidationError(
                f"Passed value ({value}) must be a length of up to {max_len}"
            )

        return str(value)

class RegExp(Validator):
    def __init__(
        self,
        regex: str,
        flags: re.RegexFlag | None = None,
        description: dict | str | None = None,
    ):
        if not flags:
            flags = 0

        try:
            re.compile(regex, flags=flags)
        except re.error as e:
            raise Exception(f"{regex} is not a valid regex") from e

        if description is None:
            doc = _getdict("validators.regex", regex=regex)
        else:
            if isinstance(description, str):
                doc = {"en": description}
            else:
                doc = description

        super().__init__(
            functools.partial(self._validate, regex=regex, flags=flags),
            doc,
            _internal_id="RegExp",
        )

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        /,
        *,
        regex: str,
        flags: re.RegexFlag | None,
    ) -> str:
        if not re.match(regex, str(value), flags=flags):
            raise ValidationError(f"Passed value ({value}) must follow pattern {regex}")

        return str(value)

class Float(Validator):
    def __init__(
        self,
        minimum: float | None = None,
        maximum: float | None = None,
    ):
        _signs = (
            _getdict("validators.positive")
            if minimum is not None and minimum == 0
            else (
                _getdict("validators.negative")
                if maximum is not None and maximum == 0
                else {}
            )
        )

        if minimum is not None and minimum != 0:
            doc = (
                {
                    lang: text.format(sign=_signs.get(lang, ""), minimum=minimum)
                    for lang, text in _getdict("validators.float_min").items()
                }
                if maximum is None and maximum != 0
                else {
                    lang: text.format(
                        sign=_signs.get(lang, ""), minimum=minimum, maximum=maximum
                    )
                    for lang, text in _getdict(
                        "validators.float_range"
                    ).items()
                }
            )

        elif maximum is None and maximum != 0:
            doc = {
                lang: text.format(sign=_signs.get(lang, ""))
                for lang, text in _getdict("validators.float").items()
            }
        else:
            doc = {
                lang: text.format(sign=_signs.get(lang, ""), maximum=maximum)
                for lang, text in _getdict("validators.float_max").items()
            }

        super().__init__(
            functools.partial(
                self._validate,
                minimum=minimum,
                maximum=maximum,
            ),
            doc,
            _internal_id="Float",
        )

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        /,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        try:
            value = float(str(value).strip().replace(",", "."))
        except ValueError:
            raise ValidationError(f"Passed value ({value}) must be a float")

        if minimum is not None and value < minimum:
            raise ValidationError(f"Passed value ({value}) is lower than minimum one")

        if maximum is not None and value > maximum:
            raise ValidationError(f"Passed value ({value}) is greater than maximum one")

        return value

class TelegramID(Validator):
    def __init__(self):
        super().__init__(
            self._validate,
            "Telegram ID",
            _internal_id="TelegramID",
        )

    @staticmethod
    def _validate(value: ConfigAllowedTypes, /) -> int:
        e = ValidationError(f"Passed value ({value}) is not a valid telegram id")

        try:
            value = int(str(value).strip())
        except Exception:
            raise e

        if str(value).startswith("-100"):
            value = int(str(value)[4:])

        if value > 2**64 - 1 or value < 0:
            raise e

        return value

class Union(Validator):
    def __init__(self, *validators):
        doc = _getdict("validators.union")

        def case(x: str) -> str:
            return x[0].upper() + x[1:]

        for validator in validators:
            for key in doc:
                doc[key] += f"- {case(validator.doc.get(key, validator.doc['en']))}\n"

        for key, value in doc.items():
            doc[key] = value.strip()

        super().__init__(
            functools.partial(self._validate, validators=validators),
            doc,
            _internal_id="Union",
        )

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        /,
        *,
        validators: list,
    ) -> ConfigAllowedTypes:
        for validator in validators:
            try:
                return validator.validate(value)
            except ValidationError:
                pass

        raise ValidationError(f"Passed value ({value}) is not valid")

class NoneType(Validator):
    def __init__(self):
        super().__init__(
            self._validate,
            _getdict("validators.empty"),
            _internal_id="NoneType",
        )

    @staticmethod
    def _validate(value: ConfigAllowedTypes, /) -> None:
        if not value:
            raise ValidationError(f"Passed value ({value}) is not None")

        return None

class Hidden(Validator):
    def __init__(self, validator: Validator | None = None):
        if not validator:
            validator = String()

        super().__init__(
            functools.partial(self._validate, validator=validator),
            validator.doc,
            _internal_id="Hidden",
        )

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        /,
        *,
        validator: Validator,
    ) -> ConfigAllowedTypes:
        return validator.validate(value)

class Emoji(Validator):
    def __init__(
        self,
        length: int | None = None,
        min_len: int | None = None,
        max_len: int | None = None,
    ):
        match True:
            case _ if length is not None:
                doc = _getdict("validators.emoji_fixed_len", length=length)
            case _ if min_len is not None and max_len is not None:
                doc = _getdict(
                    "validators.emoji_len_range", min_len=min_len, max_len=max_len
                )
            case _ if min_len is not None:
                doc = _getdict("validators.emoji_min_len", min_len=min_len)
            case _ if max_len is not None:
                doc = _getdict("validators.emoji_max_len", max_len=max_len)
            case _:
                doc = _getdict("validators.emoji")

        super().__init__(
            functools.partial(
                self._validate,
                length=length,
                min_len=min_len,
                max_len=max_len,
            ),
            doc,
            _internal_id="Emoji",
        )

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        /,
        *,
        length: int | None,
        min_len: int | None,
        max_len: int | None,
    ) -> str:
        value = str(value)
        passed_length = len(list(grapheme.graphemes(value)))

        if length is not None and passed_length != length:
            raise ValidationError(f"Passed value ({value}) is not {length} emojis long")

        if (
            min_len is not None
            and max_len is not None
            and (passed_length < min_len or passed_length > max_len)
        ):
            raise ValidationError(
                f"Passed value ({value}) is not between {min_len} and {max_len} emojis"
                " long"
            )

        if min_len is not None and passed_length < min_len:
            raise ValidationError(
                f"Passed value ({value}) is not at least {min_len} emojis long"
            )

        if max_len is not None and passed_length > max_len:
            raise ValidationError(
                f"Passed value ({value}) is not no more than {max_len} emojis long"
            )

        if any(emoji not in ALLOWED_EMOJIS for emoji in grapheme.graphemes(value)):
            raise ValidationError(
                f"Passed value ({value}) is not a valid string with emojis"
            )

        return value

class EntityLike(RegExp):
    def __init__(self):
        super().__init__(
            regex=r"^(?:@|https?://t\.me/)?(?:[a-zA-Z0-9_]{5,32}|[a-zA-Z0-9_]{1,32}\?[a-zA-Z0-9_]{1,32})$",
            description=_getdict("validators.entity_like"),
        )

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        /,
        *,
        regex: str,
        flags: re.RegexFlag | None,
    ) -> str | int:
        value = super()._validate(value, regex=regex, flags=flags)

        if value.isdigit():
            if value.startswith("-100"):
                value = value[4:]

            value = int(value)

        if value.startswith("https://t.me/"):
            value = value.split("https://t.me/")[1]

        if not value.startswith("@"):
            value = f"@{value}"

        return value

class RandomLinkList(list):
    def __str__(self):
        import random

        if not self:
            return ""
        return str(random.choice(self))

    def __bytes__(self):
        return str(self).encode("utf-8")

    def __repr__(self):
        return super().__repr__()

class RandomLink(Series):
    def __init__(self):
        super().__init__(validator=Link(), min_len=1)
        self.internal_id = "Series"
        self.doc = {
            "en": "A list of links, one of which will be chosen randomly",
            "ru": "Список ссылок, одна из которых будет выбрана случайным образом",
        }

    @staticmethod
    def _validate(value: ConfigAllowedTypes, /, **kwargs) -> RandomLinkList:
        val_args = kwargs.copy()
        if "validator" not in val_args:
            val_args["validator"] = Link()
        if "min_len" not in val_args:
            val_args["min_len"] = 1

        clean_list = Series._validate(value, **val_args)
        return RandomLinkList(clean_list)
