#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""doc_lint - линтер документации проекта (комплект "Ритм проекта").

Проверяет, что доки не врут про репозиторий: ссылки ведут в реальные файлы,
нет плейсхолдеров, нет смеси языков и запрещённых символов, есть раздел
"Заморожено", журнал STATE-LOG ведётся, дерево проекта живёт в одном месте.

Это не форматтер: он ищет места, где документация противоречит репозиторию.

Коды выхода: 0 - FAIL нет, 1 - есть хотя бы один FAIL, 2 - плохой путь/аргументы.
Все человеческие сообщения выводятся через cp1251-безопасный сток.
"""

import argparse
import datetime
import json
import os
import pathlib
import re
import sys
import urllib.parse

SCHEMA_VERSION = 1

# Абсолютные пути относительно корня проверяемого проекта.
REQUIRED_DOCS = ["AGENTS.md", "INDEX.md", "MAP.md", "docs/STATE-LOG.md"]

# Каталоги, которые линтер не смотрит: не документация проекта.
SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "dist", "build",
    "__pycache__", ".idea", ".vscode", ".mypy_cache", ".pytest_cache",
}

# Намеренно явный список замеренных опечаток в инструкционных доках.
# Это НЕ спеллчекер: опечатка в инструкции копируется каждым агентом,
# который её прочитал, поэтому такие случаи фиксируются поимённо.
KNOWN_TYPOS = [
    ("Legay", "Legacy"),
    ("какrestart", "как restart"),
]

# Технические термины, которые законно остаются латиницей в русской прозе.
TECH_WHITELIST = set("""
readme git commit push pr api json http rest sql ci cd docker kubectl head hash npm pip venv node
python typescript bash curl grep ls src dist build env config logs tmp docs legacy status log
test tests script scripts app apps id url uri yaml md txt sh py js ts ui ux seo ssr csr
mvp rbac jwt oauth dns tls ssl cpu ram io os sdk cli gui ok todo fixme https nosql orm dto dao
crud acme websocket webhook sitemap robots dev prod stage staging
windows fail pass warn info code starter
claude codex cursor gemini cline aider opencode windsurf copilot droid anthropic openai markdown prometheus grafana sentry terraform opentofu kubernetes kafka redis postgres postgresql mysql mongodb nginx linux macos ubuntu debian golang kotlin react vue svelte astro tailwind vite webpack ansible gitlab jetbrains neovim vscode zed
""".split())

# Дополнение к белому списку: имена файлов самого комплекта. Без него русская
# строка со словом "STATE-LOG" даёт ложное срабатывание mixed_language.
TECH_WHITELIST |= {
    "state", "index", "map", "agents", "type", "fact", "wave", "utf", "ascii",
    "cp1251", "skill", "pack", "tools", "tests", "readme",
}

# Символы, которые cp1251 не отображает. Пустые слоты INDEX могут быть
# типографским тире - сравнение идёт через escape, чтобы в .py не было самих тире.
EMPTY_SLOT_TOKENS = {"", "-", "--", "\u2013", "\u2014"}

CYRILLIC_RANGES = ((0x0400, 0x04FF), (0x0500, 0x052F))

MD_LINK_RE = re.compile(r"\[([^\]\n]*)\]\(([^)\n]*)\)")
MD_REF_RE = re.compile(r"^\s{0,3}\[([^\]\n]*)\]:\s*(\S+)")
PLACEHOLDER_RE = re.compile(r"\[([^\[\]\n]+)\](?!\s*\()")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
EXTERNAL_RE = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:)?//|^(?:mailto|tel|data):", re.I)
EXTERNAL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")

BOX_DRAWING_RE = re.compile(r"[\u2500-\u257f]")
TABLE_ONLY_RE = re.compile(r"^\s*\|[\s|:\-]*\|\s*$")
TREE_GLYPH_RE = re.compile(r"^\s*(?:\||\+|`)--")
PATH_ONLY_RE = re.compile(r"^\s*[A-Za-z0-9_.\-]+/\s*$")

SETUP_HEADING_RE = re.compile(r"^#{1,6}\s+.*Первичная настройка")

MAX_EVIDENCE = 25


# --------------------------------------------------------------------------
# Вывод: cp1251-безопасный сток.
# --------------------------------------------------------------------------

def setup_streams():
    """Не даём UnicodeEncodeError выйти наружу при cp1251-консоли."""
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


def sanitize(value):
    """Убирает из эха запрещённые символы, чтобы они не попали в консоль."""
    out = []
    for ch in str(value):
        cp = ord(ch)
        if cp < 0x80 or any(a <= cp <= b for a, b in CYRILLIC_RANGES):
            out.append(ch)
        else:
            out.append("\\u%04X" % cp)
    return "".join(out)


# --------------------------------------------------------------------------
# Чтение и мелкая механика
# --------------------------------------------------------------------------

def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def rel_to(target, path):
    try:
        return os.path.relpath(path, target).replace(os.sep, "/")
    except ValueError:
        return path.replace(os.sep, "/")


def collect_md_files(target):
    found = []
    for root, dirs, files in os.walk(target):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name.lower().endswith(".md"):
                found.append(os.path.join(root, name))
    return found


def slugify(heading):
    text = heading.strip().lower()
    text = re.sub(r"`", "", text)
    text = re.sub(r"[^\w\s\-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text.strip())
    return text.strip("-")


def headings_of(path):
    slugs = set()
    lines = read_text(path).splitlines()
    in_fence = False
    for line in lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING_RE.match(line)
        if match:
            slugs.add(slugify(match.group(2)))
    return slugs


def line_spans(text):
    return text.splitlines()


def setup_block_range(lines):
    """Границы блока 'Первичная настройка' (заголовок -> конец или след. равный)."""
    start = None
    level = 0
    for index, line in enumerate(lines):
        if SETUP_HEADING_RE.match(line):
            start = index
            level = len(re.match(r"^(#{1,6})", line).group(1))
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = HEADING_RE.match(lines[index])
        if match and len(match.group(1)) <= level:
            end = index
            break
    return (start, end)


def strip_code_and_urls(line):
    """Убирает из строки всё, что является именем, а не прозой автора.

    Кроме инлайн-кода, ссылок и имён файлов с расширением срезаются ещё и
    имена каталогов (слово со слэшем). Иначе любое имя директории проекта -
    templates/, src/, docs/ - выглядит как английское слово в русской фразе, и
    проверка ругается на структуру репозитория вместо кривой прозы.
    """
    line = re.sub(r"`[^`]*`", " ", line)
    line = re.sub(r"https?://\S+", " ", line)
    line = re.sub(r"\b[\w.\-]+\.(?:md|py|json|ya?ml|txt|sh|js|ts)\b", " ", line)
    # Цель markdown-ссылки - это путь, а не проза автора.
    line = re.sub(r"\]\([^)\n]*\)", "] ", line)
    line = re.sub(r"[A-Za-z0-9._\-]+/", " ", line)
    return line


def strip_inline_code(line):
    """Инлайн-код в бэктиках - это цитата, а не проза автора."""
    return re.sub(r"`[^`]*`", " ", line)


def indented_code_lines(lines):
    """Номера строк внутри отступных блоков кода Markdown (4+ пробелов).

    Блок с отступом в 4 пробела - это такой же блок кода, как и огороженный
    бэктиками, и его содержимое тоже цитата. Замерено: без этого правила
    линтер ругался на опечатку, приведённую внутри скопированного вывода.
    Одиночная строка с отступом кодом не считается: продолжение элемента
    списка тоже имеет отступ, а это уже проза автора.
    """
    marked = set()
    run = []
    for number, line in enumerate(lines, 1):
        if line.strip() and line[:4] == " " * 4:
            run.append(number)
            continue
        if len(run) >= 2:
            marked.update(run)
        run = []
    if len(run) >= 2:
        marked.update(run)
    return marked


def prose_lines(lines):
    """Отдаёт (номер, строка) для строк вне блоков кода.

    Токен внутри блока кода - это пример/цитата, а не утверждение документа,
    поэтому опечатки и плейсхолдеры в блоках кода не считаются находками.
    Покрыты оба вида блоков: огороженные бэктиками и отступные.
    """
    indented = indented_code_lines(lines)
    in_fence = False
    for number, line in enumerate(lines, 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if number in indented:
            continue
        yield number, line


def is_version_like(token):
    """[2.0.0] и [1] - это версии/сноски, а не незаполненные плейсхолдеры."""
    text = token.strip()
    return bool(re.match(r"^[vV]?\d+(\.\d+)*$", text)) or bool(re.match(r"^\d+$", text))


def make_check(check_id, status, message, evidence=None, action="", note=""):
    evidence = evidence or []
    total = len(evidence)
    capped = evidence[:MAX_EVIDENCE]
    return {
        "id": check_id,
        "status": status,
        "message": message,
        "evidence": capped,
        "evidence_total": total,
        "truncated": total > MAX_EVIDENCE,
        "action": action,
        "note": note,
    }


# --------------------------------------------------------------------------
# Проверки
# --------------------------------------------------------------------------

def check_required_files(ctx):
    missing = [doc for doc in REQUIRED_DOCS
               if not os.path.isfile(os.path.join(ctx["target"], doc))]
    evidence = [{"file": doc, "line": None, "detail": "файл не найден"} for doc in missing]

    readme = os.path.join(ctx["target"], "README.md")
    readme_present = os.path.isfile(readme)
    readme_note = "README.md на месте" if readme_present else "README.md отсутствует"
    if missing:
        status = "FAIL"
        message = "нет обязательных доков: %s; %s" % (", ".join(missing), readme_note)
    else:
        status = "PASS"
        message = "все четыре дока на месте; %s" % readme_note
    action = ""
    if missing:
        action = ("создай отсутствующие доки: "
                  "python tools/init_docs.py --target . --create-readme-stub")
    return make_check("required_files", status, message, evidence, action,
                      note="README.md есть в списке, потому что на него ссылаются INDEX.md и AGENTS.md")


def check_broken_links(ctx):
    evidence = []
    anchor_warnings = []
    remapped = []
    for path in ctx["md_files"]:
        text = read_text(path)
        lines = line_spans(text)
        rel = rel_to(ctx["target"], path)
        # Шаблон - не документ проекта, а файл, которому предстоит установка.
        # Он ссылается на СВОИХ СОСЕДЕЙ ПО УСТАНОВКЕ, которых в дереве
        # исходников нет и быть не должно: <root>/INDEX.md появляется только
        # после init_docs.py. Поэтому ссылки шаблона проверяются не здесь, а на
        # установленном комплекте (тест test_01 в tests/run_selftest.py), а сам
        # пропуск называется вслух - молчаливый пропуск и есть та ложь, против
        # которой написан линтер.
        if install_base(ctx["target"], path, text) is not None:
            remapped.append(sanitize(rel))
            continue
        for number, line in enumerate(lines, 1):
            hits = [(m.group(1), m.group(2)) for m in MD_LINK_RE.finditer(line)]
            ref = MD_REF_RE.match(line)
            if ref:
                hits.append((ref.group(1), ref.group(2)))
            for _text, raw in hits:
                target_raw = raw.strip()
                if not target_raw:
                    continue
                if EXTERNAL_SCHEME_RE.match(target_raw) or EXTERNAL_RE.match(target_raw):
                    continue
                target_raw = target_raw.split(" ", 1)[0].strip("<>")
                if not target_raw:
                    continue
                path_part, _sep, anchor = target_raw.partition("#")
                path_part = urllib.parse.unquote(path_part)
                if not path_part:
                    resolved = path
                else:
                    resolved = os.path.normpath(
                        os.path.join(os.path.dirname(path), path_part))
                if not os.path.exists(resolved):
                    evidence.append({
                        "file": rel, "line": number,
                        "detail": "мёртвая ссылка: %s" % sanitize(target_raw),
                    })
                    continue
                if anchor and resolved.lower().endswith(".md"):
                    if os.path.isfile(resolved):
                        want = slugify(urllib.parse.unquote(anchor))
                        if want and want not in headings_of(resolved):
                            anchor_warnings.append({
                                "file": rel, "line": number,
                                "detail": "якорь #%s не найден в %s" % (
                                    sanitize(anchor), rel_to(ctx["target"], resolved)),
                            })
    note = ("сопоставление якорей с заголовками - эвристика: слаги нормализуются "
            "приблизительно, расхождение якоря это WARN, а не доказательство")
    if remapped:
        note += ("; шаблоны пропущены (ссылки ведут на соседей по установке, "
                 "их проверяет установленный комплект): "
                 + ", ".join(sorted(remapped)))
    if evidence:
        return make_check(
            "broken_links", "FAIL",
            "%d битых ссылок (путь не существует)" % len(evidence),
            evidence + anchor_warnings,
            "почини или удали битые ссылки: каждая ссылка обязана вести в реальный файл",
            note)
    if anchor_warnings:
        return make_check(
            "broken_links", "WARN",
            "%d якорей не найдено в файлах-целях" % len(anchor_warnings),
            anchor_warnings,
            "сверь якорь с реальным заголовком в файле-цели", note)
    return make_check("broken_links", "PASS",
                      "все ссылки ведут в реальные файлы", [], "", note)


def check_placeholders_left(ctx):
    evidence = []
    setup_found = []
    for path in ctx["md_files"]:
        lines = line_spans(read_text(path))
        rel = rel_to(ctx["target"], path)
        block = setup_block_range(lines)
        inside = 0
        for number, line in prose_lines(lines):
            in_setup = bool(block and block[0] < number <= block[1])
            for match in PLACEHOLDER_RE.finditer(strip_inline_code(line)):
                token = match.group(1)
                if is_version_like(token):
                    continue
                if in_setup:
                    inside += 1
                    continue
                evidence.append({
                    "file": rel, "line": number,
                    "detail": "плейсхолдер не заполнен: [%s]" % sanitize(token),
                })
        if block is not None:
            setup_found.append({
                "file": rel, "line": block[0] + 1,
                "detail": ("блок 'Первичная настройка' остался (%d плейсхолдеров внутри); "
                           "его удаляют после настройки" % inside),
            })
    status = "FAIL" if evidence else ("WARN" if setup_found else "PASS")
    if evidence:
        message = "%d незаполненных плейсхолдеров" % len(evidence)
    elif setup_found:
        message = "плейсхолдеров нет, но блок 'Первичная настройка' не удалён"
    else:
        message = "незаполненных плейсхолдеров нет"
    return make_check(
        "placeholders_left", status, message, evidence + setup_found,
        "заполни плейсхолдеры фактами из репо (проверь ls/git), не выдумывай пути; "
        "после заполнения удали блок 'Первичная настройка'",
        note="эвристика: плейсхолдеры внутри блока 'Первичная настройка', инлайн-кода "
             "и блоков кода не считаются FAIL; [2.0.0] и [1] сюда не входят (это версии)")


LANG_MARKER_RE = re.compile(r"<!--\s*doc-lint:\s*lang=(\w+)\s*-->")
INSTALL_AS_RE = re.compile(r"<!--\s*doc-lint:\s*install-as=([^\s>]+)\s*-->")


def install_base(target, path, text):
    """Каталог, относительно которого надо разрешать ссылки файла.

    Файл-шаблон будет установлен в другое место, и его ссылки написаны для
    проекта, в котором он окажется, а не для дерева исходников. Поэтому шаблон
    сам объявляет свой путь установки маркером install-as, а не заставляет
    линтер угадывать. Без маркера база обычная: каталог самого файла.
    """
    match = INSTALL_AS_RE.search(text)
    if not match:
        return None
    installed = match.group(1).lstrip("/").replace("\\", "/")
    base = pathlib.Path(target) / pathlib.Path(installed).parent
    return base


def language_marker(text):
    """Явный маркер языка файла: <!-- doc-lint: lang=en -->.

    Файл, который намеренно написан не по-русски, помечает себя сам. Гадать по
    соотношению букв не надо, а решение автора видно в самом документе. Файл с
    маркером не проверяется, но и не исчезает из отчёта молча - его имя
    попадает в note, потому что молчаливый пропуск и есть та ложь, против
    которой написан линтер.
    """
    match = LANG_MARKER_RE.search(text)
    return match.group(1).lower() if match else None


def check_mixed_language(ctx):
    evidence = []
    skipped = []
    for path in ctx["md_files"]:
        text = read_text(path)
        rel = rel_to(ctx["target"], path)
        marker = language_marker(text)
        if marker and marker not in ("ru", "russian"):
            skipped.append("%s (lang=%s)" % (sanitize(rel), sanitize(marker)))
            continue
        lines = line_spans(text)
        for number, line in prose_lines(lines):
            has_cyrillic = bool(re.search(r"[А-Яа-яЁё]", line))
            if not has_cyrillic:
                continue
            scrubbed = strip_code_and_urls(line)
            for word in re.findall(r"[A-Za-z]{4,}", scrubbed):
                if word.lower() in TECH_WHITELIST:
                    continue
                evidence.append({
                    "file": rel, "line": number,
                    "detail": "латинское слово в русской строке: %s" % sanitize(word),
                })
    if evidence:
        status = "WARN"
        message = "%d строк со смесью языков" % len(evidence)
    else:
        status = "PASS"
        message = "смеси языков не найдено"
    return make_check(
        "mixed_language", status, message, evidence,
        "технический термин оставь, иноязычное слово переведи на русский",
        note=("эвристика: белый список терминов неполный, поэтому это WARN, "
              "а не FAIL")
        + (("; пропущены по маркеру языка: " + ", ".join(sorted(skipped)))
           if skipped else ""))


def check_known_typos(ctx):
    evidence = []
    for path in ctx["md_files"]:
        lines = line_spans(read_text(path))
        rel = rel_to(ctx["target"], path)
        for number, line in prose_lines(lines):
            text = strip_inline_code(line)
            for wrong, right in KNOWN_TYPOS:
                if wrong in text:
                    evidence.append({
                        "file": rel, "line": number,
                        "detail": "%s -> %s" % (sanitize(wrong), sanitize(right)),
                    })
    if evidence:
        return make_check(
            "known_typos", "FAIL", "%d замеренных опечаток" % len(evidence), evidence,
            "исправь опечатку: опечатка в инструкции копируется всеми агентами",
            note="список намеренно явный, это не спеллчекер; цитаты в бэктиках "
                 "и блоках кода не считаются находками")
    return make_check("known_typos", "PASS", "замеренных опечаток нет")


def classify_forbidden(cp):
    if 0x2010 <= cp <= 0x2015:
        return "типографское тире"
    if cp == 0x2212:
        return "минус-знак"
    if 0x2190 <= cp <= 0x21FF:
        return "стрелка"
    if cp in (0x2794, 0x27A0, 0x27A1, 0x2B05, 0x2B06, 0x2B07):
        return "стрелка"
    if 0x1F000 <= cp <= 0x1FAFF:
        return "emoji"
    if 0x2600 <= cp <= 0x27BF:
        return "символ/emoji"
    if 0xFE00 <= cp <= 0xFE0F:
        return "селектор начертания"
    if cp == 0x200D:
        return "невидимый соединитель ZWJ"
    if 0x2B00 <= cp <= 0x2BFF:
        return "стрелка/символ"
    if cp > 0x2300 and not any(a <= cp <= b for a, b in CYRILLIC_RANGES):
        return "символ вне cp1251"
    return None


def check_charset(ctx):
    evidence = []
    seen = set()
    total = 0
    for path in ctx["md_files"]:
        lines = line_spans(read_text(path))
        rel = rel_to(ctx["target"], path)
        for number, line in prose_lines(lines):
            for ch in line:
                label = classify_forbidden(ord(ch))
                if not label:
                    continue
                total += 1
                key = (rel, number, ord(ch))
                if key in seen:
                    continue
                seen.add(key)
                evidence.append({
                    "file": rel, "line": number,
                    "detail": "%s: U+%04X (%s)" % (label, ord(ch), sanitize(ch)),
                })
    if evidence:
        return make_check(
            "charset", "FAIL",
            "%d запрещённых символов (cp1251 их не отображает)" % total,
            evidence,
            "замени тире на '-', стрелки на '->', убери emoji: cp1251 их не рендерит",
            note="блоки кода считаются цитатой и пропускаются; проза - нет")
    return make_check("charset", "PASS", "запрещённых символов нет")


def check_state_log_grows_tail(ctx):
    path = os.path.join(ctx["target"], "docs", "STATE-LOG.md")
    if not os.path.isfile(path):
        return make_check("state_log_grows_tail", "WARN", "docs/STATE-LOG.md не найден",
                          [{"file": "docs/STATE-LOG.md", "line": None,
                            "detail": "журнал отсутствует"}],
                          "создай журнал: python tools/state_log.py --target . --wave <метка>")
    lines = line_spans(read_text(path))
    entries = []
    in_fence = False
    for number, line in enumerate(lines, 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("### "):
            entries.append((number, line[4:].strip()))
    if not entries:
        return make_check("state_log_grows_tail", "WARN", "в журнале нет ни одной записи",
                          [{"file": "docs/STATE-LOG.md", "line": None,
                            "detail": "ни одного заголовка ### вне блока формата"}],
                          "добавь запись финала: python tools/state_log.py --target . --wave <метка>")
    number, heading = entries[-1]
    warnings = []
    date = None
    match = DATE_RE.search(heading)
    if match:
        day, month, year = (int(x) for x in match.groups())
        try:
            date = datetime.date(year, month, day)
        except ValueError:
            date = None
    if date is None:
        warnings.append("дата последней записи не распознана: %s" % sanitize(heading))
    elif (datetime.date.today() - date).days > 90:
        warnings.append("последняя запись старше 90 дней (%s) - ритм остановился" % date.isoformat())
    if len(entries) < 2:
        warnings.append("в журнале меньше 2 записей (нужен блок формата + хотя бы одна запись)")
    evidence = [{"file": "docs/STATE-LOG.md", "line": number,
                 "detail": "последняя запись: %s" % sanitize(heading)}]
    if warnings:
        return make_check("state_log_grows_tail", "WARN", "; ".join(warnings), evidence,
                          "запиши свежую запись финала: python tools/state_log.py --target . "
                          "--wave <метка> --done '<...>' --open '<...>'")
    return make_check("state_log_grows_tail", "PASS",
                      "последняя запись: %s" % sanitize(heading), evidence)


def check_frozen_section(ctx):
    path = os.path.join(ctx["target"], "AGENTS.md")
    if not os.path.isfile(path):
        return make_check("frozen_section", "WARN", "AGENTS.md не найден",
                          [{"file": "AGENTS.md", "line": None, "detail": "файл не найден"}],
                          "создай AGENTS.md и добавь раздел 'Заморожено'")
    lines = line_spans(read_text(path))
    head_index = None
    in_fence = False
    for number, line in enumerate(lines, 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("#") and "Заморожено" in line:
            head_index = number
            break
    if head_index is None:
        return make_check(
            "frozen_section", "WARN", "в AGENTS.md нет раздела 'Заморожено'",
            [{"file": "AGENTS.md", "line": None, "detail": "раздел не найден"}],
            "добавь раздел 'Заморожено' с таблицей: он не даёт новому агенту "
            "вернуть отвергнутые планы",
            note="без этого раздела отвергнутые планы возвращаются как навязчивая идея")
    has_table = False
    for line in lines[head_index:]:
        if line.strip().startswith("|"):
            has_table = True
            break
    if not has_table:
        return make_check(
            "frozen_section", "WARN", "раздел 'Заморожено' есть, но таблицы в нём нет",
            [{"file": "AGENTS.md", "line": head_index, "detail": "нет строк таблицы"}],
            "добавь таблицу 'Что | Статус | Дата/слова человека' в раздел 'Заморожено'")
    return make_check("frozen_section", "PASS", "раздел 'Заморожено' с таблицей на месте",
                      [{"file": "AGENTS.md", "line": head_index, "detail": "раздел найден"}])


def has_tree_block(lines):
    """Дерево = блочные символы ИЛИ 4+ подряд строк с глифами (+--, |--)."""
    run = 0
    for line in lines:
        if BOX_DRAWING_RE.search(line):
            return True
        table_like = bool(TABLE_ONLY_RE.match(line))
        glyph = bool(TREE_GLYPH_RE.match(line)) and not table_like
        path_only = bool(PATH_ONLY_RE.match(line))
        if glyph or path_only:
            run += 1
            if run >= 4:
                return True
        else:
            run = 0
    return False


def check_one_tree(ctx):
    hits = []
    for doc in REQUIRED_DOCS:
        path = os.path.join(ctx["target"], doc)
        if not os.path.isfile(path):
            continue
        if has_tree_block(line_spans(read_text(path))):
            hits.append(doc)
    if len(hits) > 1:
        evidence = [{"file": doc, "line": None, "detail": "блок дерева проекта"}
                    for doc in hits]
        return make_check(
            "one_tree", "FAIL",
            "дерево проекта найдено в нескольких файлах: %s" % ", ".join(hits),
            evidence,
            "оставь дерево только в README 'Структура'; в MAP - семантика без дерева")
    if hits:
        return make_check("one_tree", "PASS",
                          "дерево проекта в одном месте: %s" % hits[0],
                          [{"file": hits[0], "line": None, "detail": "блок дерева проекта"}])
    return make_check("one_tree", "PASS", "блоков дерева проекта не найдено")


def check_index_slots(ctx):
    path = os.path.join(ctx["target"], "INDEX.md")
    if not os.path.isfile(path):
        return make_check("index_slots", "PASS", "INDEX.md не найден (см. required_files)")
    lines = line_spans(read_text(path))
    evidence = []
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped.startswith("|") or TABLE_ONLY_RE.match(line):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        target_cell = cells[1]
        is_slot = target_cell in EMPTY_SLOT_TOKENS or (
            target_cell.startswith("[") and target_cell.endswith("]"))
        if is_slot:
            evidence.append({
                "file": "INDEX.md", "line": number,
                "detail": "пустой слот: %s" % (sanitize(target_cell) or "<пусто>"),
            })
    if evidence:
        return make_check("index_slots", "WARN",
                          "%d пустых слотов в INDEX.md" % len(evidence), evidence,
                          "удали пустые слоты: комплект требует не держать заглушки")
    return make_check("index_slots", "PASS", "пустых слотов в INDEX.md нет")


CHECK_ORDER = [
    check_required_files,
    check_broken_links,
    check_placeholders_left,
    check_mixed_language,
    check_known_typos,
    check_charset,
    check_state_log_grows_tail,
    check_frozen_section,
    check_one_tree,
    check_index_slots,
]


# --------------------------------------------------------------------------
# Запуск и вывод
# --------------------------------------------------------------------------

def build_payload(target, checks, exit_code, error=None):
    summary = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        summary[check["status"].lower()] += 1
    payload = {
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "checks": checks,
        "summary": summary,
        "exit_code": exit_code,
    }
    if error:
        payload["error"] = error
    return payload


def print_human(payload, md_count):
    emit("target: %s\n" % payload["target"])
    emit("markdown-файлов в обходе: %d\n" % md_count)
    if payload.get("error"):
        emit("[FAIL] target - %s\n" % payload["error"])
    fails = []
    for check in payload["checks"]:
        emit("[%s] %s - %s\n" % (check["status"], check["id"], check["message"]))
        for item in check["evidence"]:
            where = item["file"] if item["line"] is None else "%s:%d" % (item["file"], item["line"])
            emit("    %s  %s\n" % (where, item["detail"]))
        if check["truncated"]:
            emit("    ... показаны первые %d из %d\n" % (len(check["evidence"]), check["evidence_total"]))
        if check.get("note"):
            emit("    note: %s\n" % check["note"])
        if check["status"] == "FAIL":
            fails.append(check)
            if check["action"]:
                emit("    -> %s\n" % check["action"])
    summary = payload["summary"]
    emit("\nИтог: PASS %d, WARN %d, FAIL %d\n" % (summary["pass"], summary["warn"], summary["fail"]))
    if fails:
        emit("Есть FAIL - сначала почини их, потом повтори линтер:\n")
        for check in fails:
            emit("  [%s] %s\n" % (check["id"], check["action"] or check["message"]))
    else:
        emit("FAIL нет.\n")


def main(argv=None):
    setup_streams()
    parser = argparse.ArgumentParser(
        prog="doc_lint.py",
        description="Проверить, что документация проекта не врёт про репозиторий "
                    "(ссылки, плейсхолдеры, язык, символы, журнал, дерево).",
        epilog="Коды выхода: 0 - FAIL нет, 1 - есть FAIL, 2 - плохой путь/аргументы.",
    )
    parser.add_argument("target", help="каталог проекта для проверки")
    parser.add_argument("--json", action="store_true", help="машинный вывод в JSON")
    args = parser.parse_args(argv)

    target = os.path.abspath(args.target)
    if not os.path.isdir(target):
        error = "путь не существует или не каталог: %s" % args.target
        if args.json:
            emit(json.dumps(build_payload(target, [], 2, error),
                            ensure_ascii=False, indent=2) + "\n")
        else:
            emit("[FAIL] target - %s\n" % error)
        return 2

    md_files = collect_md_files(target)
    ctx = {"target": target, "md_files": md_files}

    checks = [check(ctx) for check in CHECK_ORDER]
    exit_code = 1 if any(check["status"] == "FAIL" for check in checks) else 0
    payload = build_payload(target, checks, exit_code)

    if args.json:
        emit(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        print_human(payload, len(md_files))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
