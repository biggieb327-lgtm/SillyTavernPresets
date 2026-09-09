# Hermes Obsidian Toolset — Design Handoff

An Obsidian vault toolset for the Hermes agent, following the same
`tools.registry` pattern as the YNAB chief. Direct file-system access to the
vault — no plugins, no running Obsidian required.

**Files:** `obsidian_client.py` + `obsidian_tools.py`
**Toolset:** `obsidian`
**Tools:** 8 (5 read, 3 write)

---

## 1. Approach

An Obsidian vault is a directory of Markdown files with optional YAML
frontmatter. No database, no lock file, no binary format. The toolset operates
entirely through the file system — `open()`, `os.walk()`, `glob` — with zero
dependencies beyond the standard library and **PyYAML** for frontmatter parsing.

The client reads and writes `.md` files in the vault directory, parses
`---`-delimited YAML frontmatter, respects Obsidian's folder structure, and
ignores dotfiles and the `.obsidian/` config directory. The tools register
through `tools.registry` exactly like the YNAB toolset, gated on
`OBSIDIAN_VAULT_PATH` being set and pointing to an existing directory.

> **Why file-system, not REST API?** The Obsidian Local REST API plugin requires
> Obsidian to be running, which rules out headless servers, mobile, and scheduled
> agent runs. Direct file access works everywhere the vault directory is
> reachable — local disk, Syncthing, iCloud, or an NFS mount. The tradeoff: no
> live-reload notification to Obsidian. In practice, Obsidian watches its vault
> directory and picks up external changes within seconds.

---

## 2. Architecture

Two files, same pattern as `hermes-ynab-chief/`:

```
Hermes Gateway          obsidian_tools.py           obsidian_client.py
(Matrix interface)  -->  registry.register()    -->  ObsidianVault
                         8 tool handlers             read / write / glob
                                                     frontmatter parse
                                                           |
                                                     ~/vault/**/*.md
```

---

## 3. Configuration

All config lives in `~/.hermes/.env`, same as the YNAB toolset.

| Variable | Required | Description |
|---|---|---|
| `OBSIDIAN_VAULT_PATH` | **Yes** | Absolute path to the vault root. This is the gate — if unset, `check_requirements()` returns `False` and no tools appear. |
| `OBSIDIAN_DAILY_FORMAT` | No | Python `strftime` path format for daily notes, relative to vault root. Default: `Daily/%Y-%m-%d` (produces `Daily/2026-09-09.md`). |
| `OBSIDIAN_DEFAULT_FOLDER` | No | Default folder for `obsidian_create_note` when no path is given. Default: vault root. |
| `OBSIDIAN_IGNORE` | No | Comma-separated folder names to skip during search and list operations. Default: `.obsidian,.trash`. |

---

## 4. Client: `ObsidianVault`

A single class wrapping all vault operations. Instantiated once and cached at
module level, same pattern as `YNABClient`.

### Constructor

```python
vault = ObsidianVault(
    path="/home/brian/obsidian/main-vault",
    daily_format="Daily/%Y-%m-%d",
    ignore=[".obsidian", ".trash"]
)
```

### Core methods

```python
# Read a note -> {"path", "title", "frontmatter", "content", "tags"}
vault.read_note("Projects/hermes-tools.md")

# Write a new note (fails if file exists)
vault.create_note("Projects/new-idea.md", content="...", frontmatter={"tags": ["idea"]})

# Append to an existing note (creates if missing when allow_create=True)
vault.append_note("Daily/2026-09-09.md", "\n## From Hermes\nBudget looks tight.")

# Replace body content, preserving frontmatter
vault.update_note("Projects/hermes-tools.md", content="New body text here.")

# List notes in a folder, optionally filtered by tags
vault.list_notes(folder="Projects", tags=["active"], recursive=True)

# Full-text search across vault (case-insensitive substring match)
vault.search(query="budget review", folder=None, limit=20)

# Get or create today's daily note
vault.daily_note()

# Collect all tags used across the vault
vault.list_tags(limit=50)
```

### Frontmatter handling

Every `.md` file is split at the first two `---` lines. If the file starts with
`---`, everything between the first and second delimiter is parsed as YAML. The
rest is the body. Files without frontmatter return an empty dict.

```python
def _parse_note(self, path: str) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    fm, body = {}, text

    if text.startswith("---\n"):
        parts = text.split("---\n", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1]) or {}
            body = parts[2]

    # Inline tags: #tag anywhere in body
    inline_tags = set(re.findall(r'(?:^|\s)#([a-zA-Z][\w/-]*)', body))
    fm_tags = set(fm.get("tags", []) if isinstance(fm.get("tags"), list) else [])

    return {
        "path": str(Path(path).relative_to(self.root)),
        "title": fm.get("title") or Path(path).stem,
        "frontmatter": fm,
        "content": body,
        "tags": sorted(fm_tags | inline_tags),
    }
```

> **Write safety:** `create_note` refuses to overwrite an existing file.
> `update_note` preserves the original frontmatter block and replaces only the
> body. `append_note` adds to the end. No tool deletes files or modifies
> frontmatter — that is always a manual operation in Obsidian.

---

## 5. Tool Registry

Eight tools in the `obsidian` toolset, split 5 read / 3 write. Every tool is
gated by `check_requirements()` — if `OBSIDIAN_VAULT_PATH` is unset or does not
exist, no tools register.

### `obsidian_search_notes` · read

Full-text search across vault notes. Returns matching note paths with title,
tags, and a context snippet around each match. Call this first when the user asks
about something that might be in their notes.

```
query:  string     REQUIRED  Search text (case-insensitive substring)
folder: string               Limit search to a subfolder path
tags:   string[]             Only notes with ALL of these tags
limit:  integer              Max results (default 10)
```

### `obsidian_read_note` · read

Read a specific note by its vault-relative path. Returns the full content,
parsed frontmatter, title, and all tags.

```
path: string  REQUIRED  Vault-relative path (e.g. "Projects/hermes.md")
```

### `obsidian_list_notes` · read

List notes in a folder. Returns path, title, tags, and last-modified time for
each note.

```
folder:    string             Subfolder to list (default: vault root)
recursive: boolean            Include subfolders (default false)
tags:      string[]           Only notes with ALL of these tags
sort_by:   string             "modified" | "name" | "created" (default "modified")
limit:     integer            Max results (default 30)
```

### `obsidian_daily_note` · read

Get today's daily note. If it exists, returns its content. If not, creates it
from the configured template path (or a minimal default with the date as title)
and returns that.

```
date: string  YYYY-MM-DD, defaults to today
```

### `obsidian_list_tags` · read

List all tags in use across the vault with a count of how many notes carry each
tag. Combines frontmatter `tags:` and inline `#tags`.

```
limit: integer  Max tags to return (default 50, sorted by count desc)
```

### `obsidian_create_note` · write

Create a new note in the vault. Fails if a note already exists at the given path.
Creates intermediate folders as needed.

```
path:        string    REQUIRED  Vault-relative path for the new note
content:     string    REQUIRED  Markdown body content
title:       string              Title for frontmatter (defaults to filename stem)
tags:        string[]            Tags to set in frontmatter
frontmatter: object              Additional YAML frontmatter fields
```

### `obsidian_append_note` · write

Append content to the end of an existing note. If the note does not exist and
`create_if_missing` is true, creates it first.

```
path:              string    REQUIRED  Vault-relative path to the note
content:           string    REQUIRED  Markdown to append
heading:           string              Append under this heading (e.g. "## Notes from Hermes")
create_if_missing: boolean             Create the note if it doesn't exist (default false)
```

### `obsidian_update_note` · write

Replace the body of an existing note while preserving its frontmatter. Fails if
the note does not exist.

```
path:    string  REQUIRED  Vault-relative path to the note
content: string  REQUIRED  New Markdown body (replaces everything after frontmatter)
```

---

## 6. Search Strategy

No index. `obsidian_search_notes` walks the vault and does case-insensitive
substring matching on file contents.

1. Walk the vault directory, skipping ignored folders (`.obsidian`, `.trash`)
2. For each `.md` file: read, parse frontmatter, check tag filters
3. Case-insensitive substring search across title + body content
4. Extract a context snippet: 100 characters before and after each match
5. Sort by relevance (title match ranks higher than body match)
6. Return path, title, tags, and snippet for each hit, up to `limit`

> **Performance ceiling:** On a 2,000-note vault with an average of 500 words
> per note, a full scan takes under 200ms on any modern machine. If the vault
> grows past ~5,000 notes, add a `modified_since` parameter to limit the scan
> window, or build a simple keyword index (a JSON file rebuilt on each write).
> Do not add that complexity until the scan is measurably slow.

---

## 7. Build Order

1. **`obsidian_client.py`** — The `ObsidianVault` class. No tool registration,
   no Hermes imports. Pure file operations + YAML parsing. Testable standalone:
   `python3 -c "from obsidian_client import ObsidianVault; v = ObsidianVault('/path'); print(v.list_notes())"`

2. **`obsidian_tools.py`** — Eight `registry.register()` calls. Imports
   `ObsidianVault` from the client, wraps each method with the standard
   JSON-dumps + error-catch pattern, defines the schemas. Module-level
   `_vault = None` with lazy init, exactly like `_client` in `ynab_tools.py`.

3. **Config** — Add env vars to `~/.hermes/.env`. At minimum:
   `OBSIDIAN_VAULT_PATH=/absolute/path/to/vault`.

4. **Install** — Copy both files to `~/.hermes/hermes-agent/tools/`, restart the
   gateway with `systemctl --user restart hermes-gateway`, confirm tools appear.

5. **Verify** — Ask Hermes in Matrix:
   - "What's in my vault?" — should call `obsidian_list_notes`
   - "Search my notes for budget" — should hit matching notes
   - "Add to my daily note: reviewed budget with Hermes" — should call
     `obsidian_daily_note` then `obsidian_append_note`

---

## 8. Safety Rules

| Rule | Enforcement |
|---|---|
| No deletes | No tool exposes file deletion. The user does it in Obsidian. |
| No overwrite | `create_note` raises `FileExistsError` if the path is taken. |
| Frontmatter preserved | `update_note` replaces only the body. Original YAML is written back verbatim. |
| No .obsidian | The client skips `.obsidian/` in all operations. Config and plugins are never touched. |
| Path traversal | All paths resolve relative to vault root. `../` escapes raise `ValueError`. |

---

## 9. Example Conversations

### "What did I write about the deploy migration?"

```
1. obsidian_search_notes(query="deploy migration", limit=5)
   -> [{path: "Projects/vps-migration.md", snippet: "...migration plan..."}]

2. obsidian_read_note(path="Projects/vps-migration.md")
   -> {title: "VPS Migration", content: "## Plan\n...", tags: ["infra", "active"]}
```

### "Add to today's note: finished reviewing the YNAB integration"

```
1. obsidian_daily_note()
   -> {path: "Daily/2026-09-09.md", content: "...existing daily note..."}

2. obsidian_append_note(
     path="Daily/2026-09-09.md",
     content="- Finished reviewing the YNAB integration",
     heading="## Log"
   )
   -> {path: "Daily/2026-09-09.md", appended: true}
```

### "Create a note for the Hermes Obsidian project"

```
1. obsidian_create_note(
     path="Projects/hermes-obsidian-sync.md",
     content="# Hermes Obsidian Sync\n\nToolset for...",
     tags=["hermes", "project", "active"]
   )
   -> {path: "Projects/hermes-obsidian-sync.md", created: true}
```

### "What tags do I use most?"

```
1. obsidian_list_tags(limit=10)
   -> [{"tag": "active", "count": 34}, {"tag": "project", "count": 28}, ...]
```
