<!-- doc-lint: lang=en -->
# NOTICE

## What this is

`Starter_pack-skill` is a documentation-rhythm pack for AI coding agents: four
files that tell an agent where things live, what is dangerous to change, where
the last session stopped, and what the project's rules are - plus the tooling
to create and enforce them.

The code, templates, prose and tooling in this repository were written by the
author of this repository and are licensed MIT (see `LICENSE`, Copyright (c)
2026 Samiixo).

No third-party code is vendored, imported, or required at runtime. The pack is
a set of Markdown templates and a stdlib-only Python toolchain.

## The original pack

The pack originates as a set of four Russian Markdown files plus a how-to,
authored by the repository owner and titled "Ритм проекта" (project rhythm):
`AGENTS.md`, `INDEX.md`, `MAP.md`, `docs/STATE-LOG.md`, and
`КАК-ПОЛЬЗОВАТЬСЯ.txt`.

That original is preserved **verbatim** at `docs/original/`, including its
defects, so the changes in v2.0 can be diffed rather than taken on trust. It is
a historical artifact, not an active template:

- It is deliberately exempt from the punctuation and charset rules that apply
  to every authored file in v2.0. It contains em dashes, en dashes, arrows and
  emoji, none of which exist in cp1251.
- Running `python tools/doc_lint.py docs/original` is **expected to fail**, on
  `charset` and `broken_links` in particular. That failure is the evidence for
  why v2.0 exists, not a regression. The self-test asserts this behaviour so it
  cannot be quietly "fixed".

## Ideas and influences

Nothing here is copied from another project. The design is the author's, with
one exception worth naming: the frozen-plans table in `AGENTS.md` implements the
same discipline as the `forbidden.md` / `LEARNINGS.md` promotion rule in this
workspace's other packs - a rejected decision must be recorded where the next
agent will read it, or it will be re-proposed. The two implementations are
independent; neither imports the other.

## What v2.0 changed

The full list is in `CHANGELOG.md`. In summary: the four templates were cleaned
of measured defects (a link to a `README.md` the pack never shipped, a typo in
an instruction file, a mixed-language word, an unexplained token, and
punctuation absent from cp1251), three tools were added, and the pack's own
first rule - that every path in a document must exist - became machine-checked
instead of aspirational.

## A note on the headline defect

The original pack's rule reads: "Проверяй пути: каждая ссылка в документах
должна вести в реальное место. Документ с выдуманными путями хуже отсутствия."
The pack then linked to `README.md` without shipping one. This is recorded here
rather than quietly corrected because it is the reason the v2.0 toolchain exists:
a rule that is only prose is followed probabilistically, and the pack is its own
counter-example.
