#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""state_log - дописать запись финала сессии в docs/STATE-LOG.md.

Главный провал комплекта в том, что агенты забывают записать финал. Этот
инструмент дописывает одну запись в КОНЕЦ журнала (комплект говорит "читать
с КОНЦА") и никогда не переписывает и не переставляет старые записи.

Формат записи повторяет блок "Формат" из docs/original/STATE-LOG.md,
переведённый в ASCII-безопасную пунктуацию (тире -> "-", N... вместо знака номера).

HEAD берётся из git rev-parse --short HEAD, если каталог - репозиторий.
Если git недоступен или каталог не репозиторий, пишется строка none:
хеш не выдумывается никогда.

Коды выхода: 0 - запись сделана, 1 - ошибка записи, 2 - плохой путь/аргументы.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

SCHEMA_VERSION = 1

# Заголовок минимального журнала. Блок "Формат" сохранён как в оригинале,
# но без типографских тире и стрелок: их не отображает cp1251.
HEADER = """# STATE-LOG - журнал финалов сессий

> **Для свежего агента: читать с КОНЦА** (последняя запись - актуальное состояние).
> Формат записи - как ниже. Не переписывай старые записи; дополняй.

## Формат
```
### [дата, короткая метка сессии/волны] - HEAD=`hash`
Type: fact
<что сделано: факты, хабы, решения со ссылкой на ловушки (N...), вердикты>
<открыто / отложено: что следующий агент должен знать, чтобы не наступить>
```
"""


def setup_streams():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


def emit(text):
    stream = sys.stdout
    try:
        stream.write(text)
        stream.flush()
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "utf-8"
        buf = getattr(stream, "buffer", None)
        if buf is not None:
            buf.write(text.encode(enc, "replace"))
            buf.flush()
        else:
            stream.write(text.encode(enc, "replace").decode(enc, "replace"))


def git_head_hash(target):
    """Вернуть (hash, источник). Никогда не выдумывать хеш."""
    try:
        proc = subprocess.run(
            ["git", "-C", target, "rev-parse", "--short", "HEAD"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return "none", "none"
    if proc.returncode != 0:
        return "none", "none"
    value = proc.stdout.decode("utf-8", "replace").strip()
    if not value:
        return "none", "none"
    return value, "git"


def build_entry(wave, done, open_text, head_hash, today=None):
    day = today or datetime.date.today()
    date_text = "%02d.%02d.%04d" % (day.day, day.month, day.year)
    lines = [
        "### [%s] - %s - HEAD=`%s`" % (date_text, wave, head_hash),
        "Type: fact",
        "- Сделано: %s" % done,
        "- Открыто / отложено: %s" % open_text,
    ]
    return "\n".join(lines) + "\n"


def append_entry(path, entry_text):
    """Дописать в конец, сохранив существующие байты как строгий префикс."""
    before = b""
    if os.path.isfile(path):
        with open(path, "rb") as handle:
            before = handle.read()
    separator = b""
    if before and not before.endswith(b"\n"):
        separator = b"\n\n"
    elif before and not before.endswith(b"\n\n"):
        separator = b"\n"
    payload = entry_text.encode("utf-8")
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    mode = "ab" if os.path.isfile(path) else "wb"
    if not before:
        payload = HEADER.encode("utf-8") + b"\n" + payload
        separator = b""
    with open(path, mode) as handle:
        handle.write(separator + payload)
    after = before + separator + payload
    return before, after


def main(argv=None):
    setup_streams()
    parser = argparse.ArgumentParser(
        prog="state_log.py",
        description="Дописать одну запись финала сессии в docs/STATE-LOG.md "
                    "(только в конец, старые записи не переписываются).",
        epilog="HEAD читается из git; если git недоступен или это не репозиторий, "
               "пишется none - хеш не выдумывается.",
    )
    parser.add_argument("--target", required=True, help="каталог проекта")
    parser.add_argument("--wave", required=True, help="короткая метка сессии/волны")
    parser.add_argument("--done", default="не указано", help="что сделано (факты)")
    parser.add_argument("--open", dest="open_text", default="нет",
                        help="что открыто/отложено для следующего агента")
    parser.add_argument("--head-hash", default="", help="явный HEAD (иначе из git, иначе none)")
    parser.add_argument("--dry-run", action="store_true", help="показать запись, ничего не писать")
    parser.add_argument("--json", action="store_true", help="машинный вывод в JSON")
    args = parser.parse_args(argv)

    target = os.path.abspath(args.target)
    if not os.path.isdir(target):
        result = {
            "schema_version": SCHEMA_VERSION,
            "target": target,
            "dry_run": bool(args.dry_run),
            "appended": False,
            "head_hash": None,
            "head_hash_source": "none",
            "errors": ["каталог не существует: %s" % args.target],
            "exit_code": 2,
        }
        if args.json:
            emit(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        else:
            emit("[FAIL] target - каталог не существует: %s\n" % args.target)
        return 2

    if args.head_hash:
        head_hash, head_source = args.head_hash, "arg"
    else:
        head_hash, head_source = git_head_hash(target)

    entry_text = build_entry(args.wave, args.done, args.open_text, head_hash)
    state_path = os.path.join(target, "docs", "STATE-LOG.md")

    result = {
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "state_log": state_path.replace(os.sep, "/"),
        "dry_run": bool(args.dry_run),
        "wave": args.wave,
        "head_hash": head_hash,
        "head_hash_source": head_source,
        "appended": False,
        "bytes_before": 0,
        "bytes_after": 0,
        "entry": entry_text,
        "errors": [],
        "exit_code": 0,
    }

    if args.dry_run:
        result["bytes_before"] = os.path.getsize(state_path) if os.path.isfile(state_path) else 0
        result["bytes_after"] = result["bytes_before"]
        result["exit_code"] = 0
        if args.json:
            emit(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        else:
            emit("dry-run: запись не сделана\n")
            emit("journal: %s\n" % result["state_log"])
            emit("HEAD=%s (%s)\n" % (head_hash, head_source))
            emit("---\n%s" % entry_text)
        return 0

    try:
        before, after = append_entry(state_path, entry_text)
    except OSError as exc:
        result["errors"].append("ошибка записи: %s" % exc)
        result["exit_code"] = 1
        if args.json:
            emit(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        else:
            emit("[FAIL] не удалось записать %s: %s\n" % (state_path, exc))
        return 1

    result["appended"] = True
    result["bytes_before"] = len(before)
    result["bytes_after"] = len(after)

    if args.json:
        emit(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    else:
        emit("записано в %s\n" % result["state_log"])
        emit("HEAD=%s (%s), байт было %d, стало %d\n"
             % (head_hash, head_source, len(before), len(after)))
        emit("---\n%s" % entry_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())