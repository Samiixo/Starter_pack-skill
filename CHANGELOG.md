<!-- doc-lint: lang=en -->
# CHANGELOG

All notable changes to this project are documented here.

## [2.0.0] - 2026-10-02

The enforceable release. The original pack was prose only, and it broke its own
first rule. v2.0 keeps the four files and their intent, cleans the measured
defects, and makes the rules checkable.

### Added - toolchain

- `tools/init_docs.py` - creates the four-file kit in a target project.
  `--dry-run` provably writes nothing. It never clobbers an existing file:
  without `--force` it refuses and reports a conflict, with `--force` it backs
  the file up to `.bak` first. This matters because the pack's own instruction
  forbids blindly overwriting an existing `AGENTS.md`.
  It also closes the headline defect at the source: the kit's `INDEX.md` points
  at `README.md`, so when the target has no README the tool says so explicitly,
  and `--create-readme-stub` writes a minimal one. Creating the kit must not
  immediately create the very broken link this release exists to fix.
- `tools/doc_lint.py` - checks that the documentation does not lie about the
  repository. Ten checks, and it deliberately separates two failure classes:
  **the docs lie** (`broken_links`, `required_files`, `placeholders_left`,
  `known_typos`, `charset`, `one_tree` - FAIL) and **the kit stopped being
  maintained** (`mixed_language`, `state_log_grows_tail`, `frozen_section`,
  `index_slots` - WARN). They need different remedies, so collapsing them would
  lose the signal. Every FAIL prints a concrete next action in Russian.
- `tools/state_log.py` - appends one session-finish entry to the journal.
  It never rewrites or reorders existing entries, and it reports `none` rather
  than inventing a git hash when the target is not a repository.
- `tests/run_selftest.py` - twelve tests, including one that asserts
  `doc_lint` on `docs/original/` **fails** on `charset` and `broken_links`,
  because that failure is the evidence for the release rather than a
  regression; one that asserts `doc_lint` reports nothing on this repository's
  own authored files; and one that asserts a freshly created kit fails on
  `placeholders_left` **and on nothing else**. That last one encodes intent, not
  a bug: the templates ship placeholders for the agent to fill from repository
  facts, so an unfilled kit is genuinely not ready. The test exists so nobody
  "fixes" that FAIL into a PASS, and so that creating a kit can never produce a
  second FAIL - which would mean the kit started lying about the repository the
  moment it was created. Both directions were verified by mutation: making
  `placeholders_left` unable to fail, and suppressing the README stub, each
  turns test 12 red.

### Fixed - measured defects in the original pack

Each of these was verified against the shipped files, not recalled.

| Defect | Location | Why it mattered |
|---|---|---|
| Link to `README.md`, which the pack does not ship | `INDEX.md:9` | The pack's own rule: every path must exist, and "a document with invented paths is worse than no document" |
| `Legay` for `Legacy` | `INDEX.md:29` | A typo in an instruction file is copied by every agent that reads it |
| `какrestart` - English verb glued to a Russian word | `AGENTS.md:8` | Same class: it reads as correct at a glance and propagates |
| `recently` inside Russian prose | `INDEX.md:14` | Mixed language where it carries no meaning |
| Orphan token `Type: fact` | `STATE-LOG.md:9` | Appeared in the format example with no explanation anywhere in the pack |
| Em dashes, en dashes, arrows, emoji | every file | None of these exist in cp1251; they corrupt on a Windows console |

### Changed

- The templates lost every emoji heading (fire, globe, no-entry, warning, gear)
  in favour of plain text labels, and every typographic dash, arrow and ellipsis
  in favour of ASCII punctuation. Cyrillic is unchanged; only the punctuation
  and symbols are constrained.
- `templates/INDEX.md` now states plainly that the project tree lives in
  README's structure section, **and** that if the project has no README the row
  must say `-` rather than pointing at a file that does not exist. That is the
  direct fix for the pack's own broken-link defect.
- `templates/AGENTS.md`'s upkeep list became a table mapping situation to file,
  because the original buried that mapping in prose and that is why agents skip
  it. A short "what not to do" section was added naming the four failure modes
  the pack exists to prevent.
- The pack's path rule now points at `tools/doc_lint.py`, so it can be checked
  rather than merely believed.
- `references/` was added: `files-guide.md` (what each of the four files is
  for, with good and bad examples), `rhythm.md` (the five session steps
  expanded, plus the failure modes of an agent that reads everything and one
  that reads nothing), and `traps.md` (one entry per trap the pack prevents,
  with the symptom, the corrective rule, and which file carries the fix).
- `SKILL.md` was added: the entry point describing when the pack applies and
  what is inside. The original had a `КАК-ПОЛЬЗОВАТЬСЯ.txt` instead, which is
  preserved in `docs/original/`.

### Known limitations

- The content checks in `tools/doc_lint.py` are heuristics over text, not
  proofs. Heading-anchor matching and the detection of an English word inside
  Russian prose both work off a whitelist of technical terms that are
  legitimately Latin in Russian developer writing. Each such check is labelled
  as a heuristic in its output and prints its matches rather than reporting a
  confident PASS.
- `known_typos` is a deliberately explicit list, not a spellchecker. It carries
  the two typos measured in the original. It will not find a new one.
- A freshly created kit does not pass `doc_lint`: it fails `placeholders_left`
  by design, because the templates are filled in by the agent from repository
  facts. This is stated in `README.md` and `SKILL.md` because a tool that
  appears to fail on the very workflow it documents teaches its user to ignore
  it.
- The toolchain is tested on Windows, Python 3.9.9, cp1251 console, and has not
  been run on macOS, Linux, or another Python version.
- The pack is written in Russian, because its audience is Russian-speaking. It
  is not translated.

## [1.0.0] - original

Four Russian Markdown files plus a how-to, titled "Ритм проекта": `AGENTS.md`
(rules and session rhythm), `INDEX.md` (question-to-file catalog), `MAP.md`
(semantic map of danger, foreign code and untrusted layers), and
`docs/STATE-LOG.md` (append-only session journal read from the end). Preserved
verbatim at `docs/original/`.