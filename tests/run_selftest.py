#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Серия самопроверок для tools/ комплекта "Ритм проекта".

Запуск: python tests\\run_selftest.py

Фикстуры строятся программно в tempfile.mkdtemp и удаляются в finally.
Стандартная библиотека, без внешних зависимостей. Всё, что печатается,
идёт через cp1251-безопасный сток.
"""

import json
import locale
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
ORIGINAL = os.path.join(REPO, "docs", "original")

MD = "\u2014"   # типографское тире - пишем через escape, в .py его быть не должно
ARROW = "\u2192"


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


def decode_out(raw):
    for enc in (locale.getpreferredencoding(False) or "utf-8", "utf-8", "cp1251"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1", "replace")


def run_tool(script, args, drop_path=False):
    env = dict(os.environ)
    env.pop("PYTHONIOENCODING", None)
    if drop_path:
        env["PATH"] = ""
    proc = subprocess.run(
        [sys.executable, os.path.join(TOOLS, script)] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=REPO)
    return proc, decode_out(proc.stdout), decode_out(proc.stderr)


def run_lint(target, extra=()):
    proc, out, err = run_tool("doc_lint.py", [target, "--json"] + list(extra))
    try:
        payload = json.loads(out)
    except ValueError:
        payload = None
    return proc.returncode, payload, out, err


def by_id(payload, check_id):
    for check in payload.get("checks", []):
        if check["id"] == check_id:
            return check
    return None


def write(root, rel, content):
    path = os.path.join(root, rel.replace("/", os.sep))
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return path


def write_many(root, files):
    for rel, content in files.items():
        write(root, rel, content)


# --------------------------------------------------------------------------
# Фикстуры
# --------------------------------------------------------------------------

TPL_AGENTS = """# AGENTS.md - [НАЗВАНИЕ ПРОЕКТА]

> Инструкция для агента. Человек читает README.md.
> Каталог "вопрос -> файл" - в [INDEX.md](INDEX.md).

## Что это
[1-3 предложения: что за продукт, для кого, на чём написан.]

## Порядок работы
1. Заходишь -> хвост [docs/STATE-LOG.md](docs/STATE-LOG.md) + git status.
2. Разведываешь -> INDEX -> README -> код.

## Заморожено (не resurrect без прямого запроса человека)
| Что | Статус | Дата/слова человека |
|---|---|---|
| [фича/план] | заморожено | [слова человека] |

## Первичная настройка (агент заполняет один раз и УДАЛЯЕТ)
1. Замени все `[...]`-плейсхолдеры фактами из репо.
"""

TPL_INDEX = """# INDEX - каталог проекта (вопрос -> файл)

> Сначала сюда, потом читать.
> Горячие зоны: [MAP.md](MAP.md).

| Вопрос | Файл |
|---|---|
| Что это / зачем / как запустить | [README.md](README.md) |
| Что сделано, на чём остановились | [docs/STATE-LOG.md](docs/STATE-LOG.md) |
| Правила работы | [AGENTS.md](AGENTS.md) |
| [Фича A] - где живёт | [реальный путь] |

## Где что искать по умолчанию
- Код: [основные каталоги]
"""

TPL_MAP = """# MAP - карта проекта

> Только семантика. Дерево не дублируем - оно живёт в README "Структура".

## Горячие зоны
| Зона | Чем платить |
|---|---|
| [файл] | [почему опасно] |

## Внешние миры
| Что | Где / как |
|---|---|
| [внешний продукт] | [путь] |
"""

TPL_STATE_LOG = """# STATE-LOG - журнал финалов сессий

> Читать с КОНЦА.

## Формат
```
### [дата] - HEAD=`hash`
Type: fact
<что сделано>
<открыто>
```

### [ДД.ММ.ГГГГ] - первичная настройка - HEAD=`none`
- Создан док-порядок.
"""

TPL_FILES = {
    "AGENTS.md": TPL_AGENTS,
    "INDEX.md": TPL_INDEX,
    "MAP.md": TPL_MAP,
    "docs/STATE-LOG.md": TPL_STATE_LOG,
}


def fx_original_defects():
    """Фикстура, воспроизводящая замеренные дефекты оригинального комплекта."""
    return {
        "AGENTS.md": (
            "# AGENTS.md - [НАЗВАНИЕ ПРОЕКТА]\n"
            "\n"
            "Репозиторий: [git remote]. Продакшн/запуск: [где live, какrestart "
            + MD + " или нет].\n"
            "\n"
            "## Заморожено\n"
            "| Что | Статус | Дата/слова человека |\n"
            "|---|---|---|\n"
            "| [фича] | заморожено | [слова] |\n"
        ),
        "INDEX.md": (
            "# INDEX - каталог проекта\n"
            "\n"
            "| Вопрос | Файл |\n"
            "|---|---|\n"
            "| Что это / зачем / как запустить | [README.md](README.md) |\n"
            "| Что сделано recently, на чём остановились | [docs/STATE-LOG.md](docs/STATE-LOG.md) |\n"
            "\n"
            "## Где что искать\n"
            "- Только для истории: [archive/, примеры, Legay-ветки]\n"
        ),
        "MAP.md": (
            "# MAP - карта проекта\n"
            "\n"
            "## Горячие зоны\n"
            "| Зона | Чем платить |\n"
            "|---|---|\n"
            "| [файл] | [почему опасно] |\n"
        ),
        "docs/STATE-LOG.md": (
            "# STATE-LOG - журнал финалов сессий\n"
            "\n"
            "## Формат\n"
            "```\n"
            "### [дата, метка] - HEAD=`hash`\n"
            "Type: fact\n"
            "<что сделано>\n"
            "<открыто>\n"
            "```\n"
            "\n"
            "### [01.01.2026] - первичная настройка - HEAD=`none`\n"
            "- Создан док-порядок.\n"
        ),
    }


TREE_BLOCK = (
    "+-- src/\n"
    "|-- main.py\n"
    "|-- util.py\n"
    "+-- README.md\n"
)

ADVERSARIAL_TABLE = (
    "| Зона | Чем платить |\n"
    "|---|---|\n"
    "| a | b |\n"
    "| c | d |\n"
)


# --------------------------------------------------------------------------
# Тесты
# --------------------------------------------------------------------------

TESTS = []
NOTES = []   # диагностика теста, печатается после строки результата


def note(text):
    NOTES.append(text)
    return text


def test(fn):
    TESTS.append((fn.__name__, fn))
    return fn


@test
def test_01_init_creates_kit_without_dead_links():
    """Тест 1: init_docs в пустом проекте создаёт четыре файла в docs/, а с
    --create-readme-stub и README.md.

    Проверяем не "doc_lint зелёный" - свежесозданный комплект намеренно
    FAIL по placeholders_left, потому что плейсхолдеры заполняет агент по
    фактам репозитория. Здесь проверяется другое: что создание комплекта
    не порождает ни мёртвых ссылок, ни отсутствующих файлов, то есть
    дефект, ради которого сделана версия 2.0, не воспроизводится.
    """
    root = tempfile.mkdtemp(prefix="spk1_")
    try:
        tpl = os.path.join(root, "tpl")
        write_many(tpl, TPL_FILES)
        target = os.path.join(root, "proj")
        os.makedirs(target)
        proc, out, err = run_tool("init_docs.py", [
            "--target", target, "--templates-dir", tpl,
            "--create-readme-stub", "--project-name", "Тестовый проект", "--json"])
        assert proc.returncode == 0, "init_docs rc=%d out=%s" % (proc.returncode, out)
        init_payload = json.loads(out)
        assert not any("укажет в никуда" in w for w in init_payload["warnings"]), (
            "ложное предупреждение о README при --create-readme-stub")
        assert init_payload["readme_stub_created"] is True
        for rel in ("AGENTS.md", "INDEX.md", "MAP.md", "docs/STATE-LOG.md", "README.md"):
            assert os.path.isfile(os.path.join(target, rel.replace("/", os.sep))), "нет %s" % rel
        assert os.path.isdir(os.path.join(target, "docs")), "нет каталога docs/"
        assert "[НАЗВАНИЕ ПРОЕКТА]" not in open(
            os.path.join(target, "AGENTS.md"), encoding="utf-8").read(), "имя проекта не подставлено"
        assert "Структура" in open(os.path.join(target, "README.md"), encoding="utf-8").read()

        rc, payload, out2, err2 = run_lint(target)
        assert payload is not None, "doc_lint не дал JSON: %s" % out2
        for check_id in ("required_files", "broken_links"):
            check = by_id(payload, check_id)
            assert check is not None, "нет проверки %s" % check_id
            assert check["status"] != "FAIL", "%s FAIL: %s" % (check_id, check["message"])

        # Без --create-readme-stub каталог обязан предупредить о ссылке в никуда.
        target2 = os.path.join(root, "proj2")
        os.makedirs(target2)
        proc2, out3, err3 = run_tool("init_docs.py", [
            "--target", target2, "--templates-dir", tpl, "--json"])
        assert proc2.returncode == 0, "rc=%d out=%s" % (proc2.returncode, out3)
        warnings2 = json.loads(out3)["warnings"]
        assert any("укажет в никуда" in w for w in warnings2), (
            "нет предупреждения о ссылке INDEX.md на отсутствующий README.md: %s" % warnings2)
        assert not os.path.isfile(os.path.join(target2, "README.md")), "стаб создан без флага"
    finally:
        shutil.rmtree(root, ignore_errors=True)


@test
def test_02_dry_run_writes_nothing():
    """Тест 2: init_docs --dry-run не пишет вообще ничего (целевой каталог пуст)."""
    root = tempfile.mkdtemp(prefix="spk2_")
    try:
        tpl = os.path.join(root, "tpl")
        write_many(tpl, TPL_FILES)
        target = os.path.join(root, "proj")
        os.makedirs(target)
        proc, out, err = run_tool("init_docs.py", [
            "--target", target, "--templates-dir", tpl, "--dry-run", "--json"])
        assert proc.returncode == 0, "rc=%d out=%s" % (proc.returncode, out)
        assert os.listdir(target) == [], "dry-run что-то записал: %s" % os.listdir(target)
    finally:
        shutil.rmtree(root, ignore_errors=True)


@test
def test_03_no_clobber_and_force_backup():
    """Тест 3: существующий AGENTS.md не затирается (конфликт, rc=1, файл цел);
    с --force старый файл уходит в AGENTS.md.bak."""
    root = tempfile.mkdtemp(prefix="spk3_")
    try:
        tpl = os.path.join(root, "tpl")
        write_many(tpl, TPL_FILES)
        target = os.path.join(root, "proj")
        os.makedirs(target)
        old = "# AGENTS.md - СТАРЫЙ ФАЙЛ ЧЕЛОВЕКА\n"
        write(target, "AGENTS.md", old)

        proc, out, err = run_tool("init_docs.py", [
            "--target", target, "--templates-dir", tpl, "--json"])
        assert proc.returncode == 1, "ожидался конфликт rc=1, получили %d" % proc.returncode
        payload = json.loads(out)
        assert "AGENTS.md" in payload["skipped_existing"], payload["skipped_existing"]
        after = open(os.path.join(target, "AGENTS.md"), encoding="utf-8").read()
        assert after == old, "существующий AGENTS.md изменён без --force"

        proc2, out2, err2 = run_tool("init_docs.py", [
            "--target", target, "--templates-dir", tpl, "--force", "--json"])
        assert proc2.returncode == 0, "rc=%d out=%s" % (proc2.returncode, out2)
        backup = os.path.join(target, "AGENTS.md.bak")
        assert os.path.isfile(backup), "нет AGENTS.md.bak"
        assert open(backup, encoding="utf-8").read() == old, "бэкап не совпадает со старым файлом"
        assert open(os.path.join(target, "AGENTS.md"), encoding="utf-8").read() != old
    finally:
        shutil.rmtree(root, ignore_errors=True)


@test
def test_04_headline_original_defects():
    """Тест 4 (главный): фикстура с дефектами оригинала обязана дать FAIL
    по broken_links (ссылка на отсутствующий README.md) и по known_typos (Legay)."""
    root = tempfile.mkdtemp(prefix="spk4_")
    try:
        write_many(root, fx_original_defects())
        rc, payload, out, err = run_lint(root)
        assert rc == 1, "ожидали rc=1, получили %d" % rc
        assert payload is not None, "нет JSON: %s" % out
        links = by_id(payload, "broken_links")
        typos = by_id(payload, "known_typos")
        assert links["status"] == "FAIL", "broken_links не FAIL: %s" % links["message"]
        assert links["evidence"], "broken_links без доказательств"
        assert any("README.md" in item["detail"] for item in links["evidence"]), links["evidence"]
        assert typos["status"] == "FAIL", "known_typos не FAIL: %s" % typos["message"]
        assert any("Legay" in item["detail"] for item in typos["evidence"]), typos["evidence"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


@test
def test_05_original_directory_fails_expected():
    """Тест 5: doc_lint на docs/original каталоге комплекта ОБЯЗАН упасть по
    charset и broken_links. Оригинал - дословный исторический артефакт (с тире,
    стрелками, emoji и ссылкой на несуществующий README.md), поэтому ошибки
    здесь ожидаемы и являются признаком работающего линтера, а не бага."""
    assert os.path.isdir(ORIGINAL), "нет docs/original: %s" % ORIGINAL
    rc, payload, out, err = run_lint(ORIGINAL)
    assert "Traceback" not in err, "линтер упал:\n%s" % err
    assert payload is not None, "нет JSON: %s" % out
    assert rc == 1, "ожидали rc=1, получили %d" % rc
    for check_id in ("charset", "broken_links"):
        check = by_id(payload, check_id)
        assert check is not None, "нет проверки %s" % check_id
        assert check["status"] == "FAIL", "%s не FAIL: %s" % (check_id, check["message"])
        assert check["evidence"], "%s без доказательств" % check_id


@test
def test_06_missing_path_and_empty_dir():
    """Тест 6: нет пути -> rc=2; пустой каталог -> rc=1 без падения."""
    rc, payload, out, err = run_lint(os.path.join(REPO, "нет-такого-каталога-xyz"))
    assert rc == 2, "ожидали rc=2 для отсутствующего пути, получили %d" % rc

    root = tempfile.mkdtemp(prefix="spk6_")
    try:
        rc2, payload2, out2, err2 = run_lint(root)
        assert "Traceback" not in err2, "падение на пустом каталоге:\n%s" % err2
        assert rc2 == 1, "ожидали rc=1 на пустом каталоге, получили %d" % rc2
        assert payload2 is not None, "нет JSON на пустом каталоге: %s" % out2
        assert by_id(payload2, "required_files")["status"] == "FAIL"
    finally:
        shutil.rmtree(root, ignore_errors=True)


@test
def test_07_state_log_appends_only():
    """Тест 7: state_log дописывает, не трогая старое (старые байты - строгий
    префикс новых); хеш не выдумывается, когда git недоступен или это не репозиторий."""
    root = tempfile.mkdtemp(prefix="spk7_")
    try:
        target = os.path.join(root, "proj")
        old = "# STATE-LOG - журнал\n\n### [01.01.2026] - старое - HEAD=`none`\n- Старая запись без перевода строки в конце."
        write(target, "docs/STATE-LOG.md", old)
        path = os.path.join(target, "docs", "STATE-LOG.md")
        before = open(path, "rb").read()

        proc, out, err = run_tool("state_log.py", [
            "--target", target, "--wave", "W1", "--done", "сделано",
            "--open", "открыто", "--json"])
        assert proc.returncode == 0, "rc=%d out=%s err=%s" % (proc.returncode, out, err)
        payload = json.loads(out)
        assert payload["head_hash"] == "none", "хеш выдуман: %r" % payload["head_hash"]
        assert payload["head_hash_source"] == "none", payload["head_hash_source"]
        after = open(path, "rb").read()
        assert after.startswith(before), "старые байты не префикс новых"
        assert len(after) > len(before), "запись не дописана"
        assert b"### [W1]" not in before, "тестовая метка не должна быть в старом файле"
        added = after[len(before):].decode("utf-8", "replace")
        assert "### [" in added and "W1" in added and "HEAD=`none`" in added, added
        assert "- Сделано: сделано" in added and "- Открыто / отложено: открыто" in added, added

        # git недоступен вовсе: PATH пуст -> хеш обязан остаться none.
        proc2, out2, err2 = run_tool("state_log.py", [
            "--target", target, "--wave", "W2", "--done", "x", "--json"], drop_path=True)
        assert proc2.returncode == 0, "rc=%d out=%s err=%s" % (proc2.returncode, out2, err2)
        payload2 = json.loads(out2)
        assert payload2["head_hash"] == "none", "хеш выдуман без git: %r" % payload2["head_hash"]

        # новый журнал создаётся с заголовком и записью.
        target3 = os.path.join(root, "proj3")
        os.makedirs(target3)
        proc3, out3, err3 = run_tool("state_log.py", [
            "--target", target3, "--wave", "W3", "--done", "d", "--json"])
        assert proc3.returncode == 0, "rc=%d err=%s" % (proc3.returncode, err3)
        text3 = open(os.path.join(target3, "docs", "STATE-LOG.md"), encoding="utf-8").read()
        assert "# STATE-LOG" in text3 and "## Формат" in text3 and "W3" in text3, text3[:200]
    finally:
        shutil.rmtree(root, ignore_errors=True)


@test
def test_08_cp1251_console_regression():
    """Тест 8: doc_lint как дочерний процесс при cp1251-консоли и БЕЗ
    PYTHONIOENCODING не должен давать UnicodeEncodeError и печатать трейсбек.
    Фикстура содержит кириллицу в путях/ссылках, поэтому вывод реально кириллический."""
    enc_proc = subprocess.run(
        [sys.executable, "-c", "import sys;print(sys.stdout.encoding)"],
        stdout=subprocess.PIPE, env={k: v for k, v in os.environ.items()
                                     if k != "PYTHONIOENCODING"})
    child_enc = decode_out(enc_proc.stdout).strip()
    note("      encoding дочернего python: %s" % child_enc)
    assert "cp1251" in child_enc or "cp866" in child_enc or "1251" in child_enc, (
        "не удалось получить не-utf8 консоль (%s): регрессия проверена слабее" % child_enc)

    root = tempfile.mkdtemp(prefix="spk8_")
    try:
        write_many(root, {
            "INDEX.md": "# INDEX\n\n| Вопрос | Файл |\n|---|---|\n"
                        "| описание | [отсутствующий-док.md](отсутствующий-док.md) |\n",
            "AGENTS.md": "# AGENTS.md\n\nПравила для агента.\n",
            "MAP.md": "# MAP\n\nСемантика.\n",
            "docs/STATE-LOG.md": "# STATE-LOG\n\n### [01.01.2026] - настройка - HEAD=`none`\n- Есть.\n",
        })
        proc, out, err = run_tool("doc_lint.py", [root, "--json"])
        assert proc.returncode in (0, 1), "rc=%d" % proc.returncode
        assert "UnicodeEncodeError" not in err, "UnicodeEncodeError в stderr:\n%s" % err
        assert "UnicodeEncodeError" not in out, "UnicodeEncodeError в stdout"
        assert "Traceback" not in err, "трейсбек:\n%s" % err
        assert "отсутствующий-док.md" in out, "кириллица потерялась в выводе: %s" % out[:200]
        note("      реальный вывод ребёнка (первые 400 символов):")
        for line in out.splitlines()[:12]:
            note("      | %s" % line)
    finally:
        shutil.rmtree(root, ignore_errors=True)


@test
def test_09_json_schema_and_exit_code():
    """Тест 9: ключи --json стабильны, exit_code в JSON совпадает с кодом процесса."""
    root = tempfile.mkdtemp(prefix="spk9_")
    try:
        write_many(root, fx_original_defects())
        rc, payload, out, err = run_lint(root)
        assert payload is not None, "нет JSON: %s" % out
        for key in ("schema_version", "target", "checks", "summary", "exit_code"):
            assert key in payload, "нет ключа %s" % key
        for key in ("pass", "warn", "fail"):
            assert key in payload["summary"], "нет summary.%s" % key
        assert payload["exit_code"] == rc, "exit_code %s != rc %s" % (payload["exit_code"], rc)
        for check in payload["checks"]:
            for key in ("id", "status", "message", "evidence", "action"):
                assert key in check, "в проверке %s нет ключа %s" % (check.get("id"), key)
            assert check["status"] in ("PASS", "WARN", "FAIL"), check["status"]
        total = payload["summary"]["pass"] + payload["summary"]["warn"] + payload["summary"]["fail"]
        assert total == len(payload["checks"]), "summary не сходится с checks"
    finally:
        shutil.rmtree(root, ignore_errors=True)


@test
def test_10_one_tree_detection():
    """Тест 10: one_tree ловит дерево в двух доках (FAIL) и не срабатывает
    на одном дереве и на markdown-таблицах."""
    root = tempfile.mkdtemp(prefix="spk10a_")
    try:
        write_many(root, {
            "AGENTS.md": "# AGENTS.md\n\n## Структура\n" + TREE_BLOCK,
            "MAP.md": "# MAP\n\n## Структура\n" + TREE_BLOCK,
            "INDEX.md": "# INDEX\n\n| Вопрос | Файл |\n|---|---|---|\n| a | b |\n",
            "docs/STATE-LOG.md": "# STATE-LOG\n\n### [01.01.2026] - x - HEAD=`none`\n- Есть.\n",
        })
        rc, payload, out, err = run_lint(root)
        assert payload is not None, out
        check = by_id(payload, "one_tree")
        assert check["status"] == "FAIL", "one_tree не FAIL: %s" % check["message"]
        for name in ("AGENTS.md", "MAP.md"):
            assert name in check["message"], check["message"]
    finally:
        shutil.rmtree(root, ignore_errors=True)

    root2 = tempfile.mkdtemp(prefix="spk10b_")
    try:
        write_many(root2, {
            "AGENTS.md": "# AGENTS.md\n\n## Структура\n" + TREE_BLOCK,
            "MAP.md": "# MAP\n\n## Таблица\n" + ADVERSARIAL_TABLE + ADVERSARIAL_TABLE,
            "INDEX.md": "# INDEX\n\n| Вопрос | Файл |\n|---|---|\n| a | b |\n| c | d |\n",
            "docs/STATE-LOG.md": "# STATE-LOG\n\n### [01.01.2026] - x - HEAD=`none`\n- Есть.\n",
        })
        rc2, payload2, out2, err2 = run_lint(root2)
        assert payload2 is not None, out2
        check2 = by_id(payload2, "one_tree")
        assert check2["status"] == "PASS", "one_tree ложно сработал: %s" % check2["message"]
    finally:
        shutil.rmtree(root2, ignore_errors=True)


@test
def test_11_no_false_positives_on_own_files():
    """Тест 11: линтер не ругается на собственные файлы комплекта.

    Замерено на этом репозитории: линтер находил дефекты в документах, которые
    эти дефекты ОПИСЫВАЮТ, и в шаблонах, чьи ссылки ведут на соседей по
    установке. Инструмент, который кричит на собственные артефакты, приучает
    читателя себя игнорировать - это ровно та театральность, против которой он
    написан.

    Проверяются обе половины:
    1. На своих авторских файлах (всё, кроме docs/original) нет находок по
       broken_links, known_typos, placeholders_left, charset и mixed_language.
    2. Цитата в блоке с отступом в 4 пробела не считается находкой: там
       приведена опечатка, и линтер не должен ругаться на её упоминание.
    """
    proc, out, err = run_tool("doc_lint.py", [REPO, "--json"])
    payload = json.loads(out)
    own = {}
    for check in payload["checks"]:
        leftovers = [e for e in check["evidence"]
                     if "original" not in str(e.get("file", "")).replace("\\", "/")]
        own[check["id"]] = leftovers
    for cid in ("broken_links", "known_typos", "placeholders_left",
                "charset", "mixed_language"):
        hits = own.get(cid) or []
        assert not hits, ("%s нашёл находки в собственных файлах комплекта: %s"
                          % (cid, hits[:4]))

    # Цитата в отступном блоке кода - не находка.
    cited = tempfile.mkdtemp(prefix="spk11_")
    try:
        lines = ["# AGENTS.md", "", "## Пример", ""]
        lines.append("    " + "[FAIL] known_typos  INDEX.md:29 - \"Legay\"")
        lines.append("    " + "           что делать: исправь опечатку")
        lines += ["", "Обычная проза про проект.", ""]
        write_many(cited, {"AGENTS.md": "\n".join(lines)})
        rc, payload2, out2, err2 = run_lint(cited)
        assert payload2 is not None, out2
        check2 = by_id(payload2, "known_typos")
        assert check2["status"] == "PASS", (
            "опечатка внутри отступного блока кода принята за находку: %s"
            % check2["message"])
        assert "Legay" not in json.dumps(check2, ensure_ascii=False), check2
    finally:
        shutil.rmtree(cited, ignore_errors=True)


# --------------------------------------------------------------------------
# Прогон
@test
def test_12_fresh_kit_fails_only_on_placeholders():
    """Тест 12: свежесозданный комплект валит doc_lint РОВНО по одной проверке -
    placeholders_left.

    Это фиксирует смысл, а не баг. init_docs кладёт шаблоны, в которых
    плейсхолдеры заполняет агент по фактам репозитория; пока они не заполнены,
    документация действительно не готова, и doc_lint обязан это сказать. Тест
    существует, чтобы (1) никто не "починил" placeholders_left до PASS на
    свежем комплекте, и (2) чтобы после создания комплекта не появилось
    второго FAIL - значит, комплект не начал врать о репозитории.

    FAIL-класс и WARN-класс проверяются раздельно: у них разные лекарства.
    """
    root = tempfile.mkdtemp(prefix="spk12_")
    try:
        tpl = os.path.join(root, "tpl")
        write_many(tpl, TPL_FILES)
        target = os.path.join(root, "proj")
        os.makedirs(target)
        proc, out, err = run_tool("init_docs.py", [
            "--target", target, "--templates-dir", tpl,
            "--create-readme-stub", "--project-name", "Проверка", "--json"])
        assert proc.returncode == 0, "init_docs rc=%d out=%s" % (proc.returncode, out)

        rc, payload, out2, err2 = run_lint(target)
        assert payload is not None, "doc_lint не выдал JSON: %s" % out2

        fails = sorted(c["id"] for c in payload["checks"] if c["status"] == "FAIL")
        assert fails == ["placeholders_left"], (
            "на свежем комплекте ожидался единственный FAIL placeholders_left, "
            "получено: %s" % fails)
        assert rc == 1, "при наличии FAIL код возврата должен быть 1, получен %d" % rc

        check = by_id(payload, "placeholders_left")
        assert check["evidence"], "placeholders_left FAIL без единой находки"
        note("FAIL-класс: %s; находок: %d" % (", ".join(fails), len(check["evidence"])))

        warn_ids = {"mixed_language", "state_log_grows_tail",
                    "frozen_section", "index_slots"}
        for cid in warn_ids:
            c = by_id(payload, cid)
            assert c is not None, "нет проверки %s" % cid
            assert c["status"] in ("PASS", "WARN"), (
                "%s должен быть PASS или WARN, получен %s" % (cid, c["status"]))

        # Заполнение плейсхолдеров обязано снимать FAIL. Проверяем на одном
        # файле: если это перестанет работать, placeholders_left станет
        # непроходимым, то есть бесполезным.
        agents = os.path.join(target, "AGENTS.md")
        text = open(agents, encoding="utf-8").read()
        filled = re.sub(r"\[[^\]\n]+\]", "заполнено", text)
        assert filled != text, "в AGENTS.md нечего заполнять: фикстура теста сломана"
        open(agents, "w", encoding="utf-8", newline="\n").write(filled)
        rc3, payload3, out3, err3 = run_lint(target)
        assert payload3 is not None, out3
        left = len(by_id(payload3, "placeholders_left")["evidence"])
        assert left < len(check["evidence"]), (
            "заполнение AGENTS.md не уменьшило число находок: %d -> %d"
            % (len(check["evidence"]), left))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------

def main():
    setup_streams()
    total = len(TESTS)
    passed = 0
    failures = []
    for index, (name, fn) in enumerate(TESTS, 1):
        label = "[%d/%d] %s" % (index, total, name)
        del NOTES[:]
        try:
            fn()
        except Exception:
            passed_ok = False
            reason = traceback.format_exc().strip().splitlines()[-1]
            failures.append((name, traceback.format_exc()))
        else:
            passed_ok = True
            passed += 1
        emit("%s ... %s\n" % (label, "PASS" if passed_ok else "FAIL"))
        for line in NOTES:
            emit(line + "\n")
        if not passed_ok:
            emit("      причина: %s\n" % reason)
            if fn.__doc__:
                emit("      что проверялось: %s\n" % " ".join(fn.__doc__.split()))

    emit("\nИтог: %d/%d PASS\n" % (passed, total))
    if failures:
        for name, tb in failures:
            emit("\n--- подробности %s ---\n%s\n" % (name, tb))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())