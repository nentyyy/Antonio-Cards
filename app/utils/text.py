from __future__ import annotations

from functools import wraps
from typing import Any, Awaitable, Callable

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup


def fix_text(text: Any) -> Any:
    if not isinstance(text, str) or not text:
        return text

    best = text
    seen = {text}
    queue = [text]

    while queue:
        current = queue.pop(0)
        for encoding in ("cp1251", "latin1"):
            try:
                candidate = current.encode(encoding).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            queue.append(candidate)
            if _looks_better(candidate, best):
                best = candidate

    return best


def fix_markup(markup: Any) -> Any:
    if isinstance(markup, InlineKeyboardMarkup):
        for row in markup.inline_keyboard:
            for button in row:
                button.text = fix_text(button.text)
        return markup

    if isinstance(markup, ReplyKeyboardMarkup):
        for row in markup.keyboard:
            for button in row:
                if isinstance(button, KeyboardButton):
                    button.text = fix_text(button.text)
        markup.input_field_placeholder = fix_text(markup.input_field_placeholder)
        return markup

    return markup


def install_aiogram_text_fixes() -> None:
    if getattr(Bot, "_cards_text_fix_installed", False):
        return

    Bot.send_message = _wrap_text_method(Bot.send_message, text_arg_index=2)
    Bot.send_photo = _wrap_text_method(Bot.send_photo, text_arg_index=5, text_kwarg="caption")
    Bot.edit_message_text = _wrap_text_method(Bot.edit_message_text, text_arg_index=1)
    Bot.edit_message_caption = _wrap_text_method(Bot.edit_message_caption, text_arg_index=5, text_kwarg="caption")
    Message.answer = _wrap_text_method(Message.answer, text_arg_index=1)
    Message.answer_photo = _wrap_text_method(Message.answer_photo, text_arg_index=3, text_kwarg="caption")
    Message.edit_text = _wrap_text_method(Message.edit_text, text_arg_index=1)
    Message.edit_caption = _wrap_text_method(Message.edit_caption, text_arg_index=2, text_kwarg="caption")
    Bot._cards_text_fix_installed = True


def _looks_better(candidate: str, current: str) -> bool:
    return _score(candidate) > _score(current)


def _score(text: str) -> tuple[int, int, int, int]:
    return (
        _russian_score(text),
        -_mojibake_score(text),
        _emoji_score(text),
        -len(text),
    )


def _emoji_score(text: str) -> int:
    return sum(1 for ch in text if ord(ch) > 0x2600)


def _mojibake_score(text: str) -> int:
    bad_chunks = (
        "?",
        "?",
        "??",
        "??",
        "??",
        "??",
        "??",
        "??",
        "??",
        "???",
        "???",
        "??",
    )
    return sum(text.count(chunk) for chunk in bad_chunks)


def _russian_score(text: str) -> int:
    lower = text.lower()
    score = 0
    score += sum(1 for ch in text if _is_cyrillic(ch))
    common_chunks = (
        " ???????",
        " ?????",
        " ??????",
        " ???????",
        " ?????",
        " ?????????",
        " ?????",
        " ????????",
        " ????",
        " ??????",
        " ???????",
        " ???????",
        " ?????",
        " ??????",
        " ???????",
        " ?????",
        " ??",
        " ????????",
        " ?????",
        " ??????",
        " ??????",
        " ??????",
        " ????????",
        " ????????",
        " ?????",
        " ????????",
        " ?????",
        " ???????",
        " ????????",
    )
    score += sum(lower.count(chunk) * 8 for chunk in common_chunks)
    good_bigrams = (
        "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??", "??",
    )
    score += sum(lower.count(chunk) * 2 for chunk in good_bigrams)
    return score


def _is_cyrillic(ch: str) -> bool:
    code = ord(ch)
    return 0x0400 <= code <= 0x04FF


def _wrap_text_method(
    method: Callable[..., Awaitable[Any]],
    *,
    text_arg_index: int,
    text_kwarg: str = "text",
) -> Callable[..., Awaitable[Any]]:
    @wraps(method)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        args_list = list(args)

        if "reply_markup" in kwargs:
            kwargs["reply_markup"] = fix_markup(kwargs["reply_markup"])

        if text_kwarg in kwargs:
            kwargs[text_kwarg] = fix_text(kwargs[text_kwarg])
        elif len(args_list) > text_arg_index:
            args_list[text_arg_index] = fix_text(args_list[text_arg_index])

        return await method(*args_list, **kwargs)

    return wrapper
