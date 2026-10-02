#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""init_docs - создать комплект документации "Ритм проекта" в проекте.

Копирует AGENTS.md, INDEX.md, MAP.md и docs/STATE-LOG.md из каталога templates/
в целевой проект. Никогда не затирает существующий файл вслепую: без --force
файл пропускается с конфликтом, с --force он сначала уходит в <имя>.bak.

Если в проекте нет README.md, а INDEX.md на него ссылается, инструмент
предупреждает и предлагает --create-readme-stub: комплект запрещает ссылки
в никуда, и создание комплекта не должно сразу ломать ссылку.

Коды выхода: 0 - готово, 1 - конфликт/пропуски, 2 - плохой путь или аргументы.
"""

import argparse
import json
import os
import shutil
import sys

SCHEMA_VERSION = 1

# rel в проекте -> список возможных имён шаблона в templates/.
# STATE-LOG ищем и как templates/docs/STATE-LOG.md, и как templates/STATE-LOG.md.
FILE_PLAN = [
    ("AGENTS.md", ["AGENTS.md"]),
    ("INDEX.md", ["INDEX.md"]),
    ("MAP.md", ["MAP.md"]),
    ("docs/STATE-LOG.md", ["docs/STATE-LOG.md", "STATE-LOG.md"]),
]

README_STUB = """# {title}

Краткое описание проекта - заполни: что за продукт, для кого, на чём написан.

## Запуск

- Как запустить локально: заполни.
- Продакшн/стенд: заполни или напиши "нет".

## Структура

- Дерево проекта живёт только здесь (см. AGENTS.md, правило "одно дерево").
- Заполни реальные каталоги; не выдумывай пути.

## Ловушки

- Известные грабли: заполни по мере появления.
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


def skill_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_template(templates_dir, candidates):
    for name in candidates:
        path = os.path.join(templates_dir, name.replace("/", os.sep))
        if os.path.isfile(path):
            return path
    return None


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
        return handle.read()


def apply_project_name(content, name):
    if not name:
        return content
    for token in ("[НАЗВАНИЕ ПРОЕКТА]", "{{PROJECT_NAME}}", "{{project_name}}"):
        content = content.replace(token, name)
    return content


def write_text(path, content):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def build_plan(target, templates_dir, project_name):
    plan = []
    for dest_rel, candidates in FILE_PLAN:
        dest = os.path.join(target, dest_rel.replace("/", os.sep))
        template = find_template(templates_dir, candidates)
        entry = {
            "dest_rel": dest_rel,
            "dest": dest,
            "template": template,
            "exists": os.path.isfile(dest),
            "content": None,
        }
        if template is not None:
            entry["content"] = apply_project_name(read_text(template), project_name)
        plan.append(entry)
    return plan


def index_links_readme(plan):
    for entry in plan:
        if entry["dest_rel"] == "INDEX.md" and entry["content"]:
            return "README.md" in entry["content"]
    return False


def main(argv=None):
    setup_streams()
    parser = argparse.ArgumentParser(
        prog="init_docs.py",
        description="Создать комплект документации AGENTS.md + INDEX.md + MAP.md + "
                    "docs/STATE-LOG.md из шаблонов templates/.",
        epilog="Инструмент не затирает файлы без --force и предупреждает о ссылке "
               "INDEX.md на отсутствующий README.md.",
    )
    parser.add_argument("--target", required=True, help="каталог проекта (должен существовать)")
    parser.add_argument("--dry-run", action="store_true", help="только показать план, ничего не писать")
    parser.add_argument("--force", action="store_true",
                        help="перезаписать существующий файл, сохранив копию <имя>.bak")
    parser.add_argument("--json", action="store_true", help="машинный вывод в JSON")
    parser.add_argument("--project-name", default="",
                        help="подставить имя проекта вместо плейсхолдера в шаблонах")
    parser.add_argument("--create-readme-stub", action="store_true",
                        help="создать минимальный README.md, если его нет")
    parser.add_argument("--templates-dir", default="",
                        help="каталог шаблонов (по умолчанию templates/ рядом с tools/)")
    args = parser.parse_args(argv)

    target = os.path.abspath(args.target)
    if not os.path.isdir(target):
        result = {
            "schema_version": SCHEMA_VERSION,
            "target": target,
            "dry_run": bool(args.dry_run),
            "created": [],
            "skipped_existing": [],
            "skipped_missing_template": [],
            "backed_up": [],
            "readme_stub_created": False,
            "warnings": ["каталог не существует: %s" % args.target],
            "exit_code": 2,
        }
        if args.json:
            emit(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        else:
            emit("[FAIL] target - каталог не существует: %s\n" % args.target)
        return 2

    templates_dir = args.templates_dir or os.path.join(skill_root(), "templates")
    templates_dir = os.path.abspath(templates_dir)

    plan = build_plan(target, templates_dir, args.project_name)
    missing_templates = [e["dest_rel"] for e in plan if e["template"] is None]
    conflicts = [e["dest_rel"] for e in plan if e["exists"] and not args.force]

    warnings = []
    readme_path = os.path.join(target, "README.md")
    readme_exists = os.path.isfile(readme_path)
    if index_links_readme(plan) and not readme_exists and not args.create_readme_stub:
        warnings.append(
            "INDEX.md ссылается на README.md, но README.md в проекте нет - "
            "каталог укажет в никуда. Запусти с --create-readme-stub, "
            "или создай README.md сам.")
    if not os.path.isdir(templates_dir):
        warnings.append("каталог шаблонов не найден: %s" % templates_dir)
    if missing_templates:
        warnings.append("нет шаблонов для: %s - эти файлы пропущены" % ", ".join(missing_templates))

    result = {
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "templates_dir": templates_dir,
        "dry_run": bool(args.dry_run),
        "project_name": args.project_name,
        "created": [],
        "skipped_existing": list(conflicts),
        "skipped_missing_template": list(missing_templates),
        "backed_up": [],
        "readme_stub_created": False,
        "warnings": warnings,
        "exit_code": 0,
    }

    if args.dry_run:
        result["planned"] = [e["dest_rel"] for e in plan if e["template"] is not None]
        result["exit_code"] = 1 if (conflicts or missing_templates) else 0
        if args.json:
            emit(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        else:
            emit("dry-run: ничего не записано\n")
            emit("target: %s\n" % target)
            for entry in plan:
                if entry["template"] is None:
                    emit("  [SKIP] %s - нет шаблона\n" % entry["dest_rel"])
                elif entry["exists"] and not args.force:
                    emit("  [CONFLICT] %s - уже существует (нужен --force)\n" % entry["dest_rel"])
                else:
                    emit("  [WRITE] %s\n" % entry["dest_rel"])
            if args.create_readme_stub and not readme_exists:
                emit("  [WRITE] README.md (заглушка)\n")
            for line in warnings:
                emit("  WARNING: %s\n" % line)
        return result["exit_code"]

    for entry in plan:
        if entry["template"] is None:
            continue
        dest = entry["dest"]
        if entry["exists"]:
            if not args.force:
                continue
            backup = dest + ".bak"
            shutil.copy2(dest, backup)
            result["backed_up"].append(os.path.basename(backup))
        write_text(dest, entry["content"])
        result["created"].append(entry["dest_rel"])

    if args.create_readme_stub and not readme_exists:
        title = args.project_name or "Проект"
        write_text(readme_path, README_STUB.format(title=title))
        result["readme_stub_created"] = True

    if conflicts or missing_templates:
        result["exit_code"] = 1

    if args.json:
        emit(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    else:
        emit("target: %s\n" % target)
        emit("шаблоны: %s\n" % templates_dir)
        for name in result["created"]:
            emit("  [OK] создан %s\n" % name)
        for name in result["backed_up"]:
            emit("  [BACKUP] %s\n" % name)
        for name in result["skipped_existing"]:
            emit("  [CONFLICT] %s - не тронут (нужен --force для перезаписи с бэкапом)\n" % name)
        for name in result["skipped_missing_template"]:
            emit("  [SKIP] %s - шаблона нет, контент не выдумываем\n" % name)
        if result["readme_stub_created"]:
            emit("  [OK] создан README.md (заглушка с разделом \"Структура\")\n")
        for line in warnings:
            emit("  WARNING: %s\n" % line)
        if result["exit_code"] == 0:
            emit("Готово.\n")
        else:
            emit("Готово с замечаниями (см. выше).\n")
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())