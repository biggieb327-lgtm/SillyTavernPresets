# Chub.ai Lorebook Entry Schema

Every lorebook entry must contain ALL 15 fields or the chub.ai importer crashes. No field is optional, even when its value is a default or empty.

| Field | Type | Default / Notes |
|---|---|---|
| `id` | int | Unique per entry, sequential is fine |
| `keys` | array of strings | Primary trigger keywords |
| `content` | string | The entry text. World/character data only — no depth prompts |
| `enabled` | bool | `true` |
| `insertion_order` | int | Controls ordering among fired entries |
| `case_sensitive` | bool | `false` unless there's a reason |
| `name` | string | Entry label |
| `priority` | int | Eviction priority under budget pressure |
| `comment` | string | Can be empty string, must be present |
| `selective` | bool | `false` unless secondary keys used |
| `secondary_keys` | array of strings | Empty array if unused, must be present |
| `constant` | bool | `true` = always injected (counts toward permanent tokens) |
| `position` | string/int | Insertion position per spec |
| `selectiveLogic` | int | `0` = AND. Integer, not string |
| `probability` | int | 0–100, default `100`. Integer, not float |

## Rules

- `selectiveLogic` and `probability` are integers. String or float values are hard bugs.
- Constant entries count against the ~2,500 permanent token budget. Keep constants lean; put bulk reference data in keyed entries.
- Under DS4 Increased Dialogue mode, `scan_depth` drops to 3 — keyed entries relying on deep scan won't fire. Put must-fire keys in vocabulary the character or user actually uses in recent turns.
- Depth prompts and behavioral directives do not go in lorebook entries under any circumstances. They belong in `post_history_instructions`.
