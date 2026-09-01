"""The three-layer workspace and its patch engine (paper §3.1).

    raw/    immutable execution traces         (permanent, write once)
    wiki/   patterns/ + index.md + logs.md      (compounding, never reset)
            + skill-impact.md
    skills/ <name>/SKILL.md                      (reversible, conditional)

The lifecycle differences are enforced here, not just documented:
  - raw traces refuse to be overwritten;
  - the wiki has no rollback method at all — only the gate can revert skills;
  - skills can be snapshotted and restored (skills-only rollback).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Patch:
    """One incremental edit to a wiki page or a skill (paper §3.2.2/§3.2.3)."""

    target: str  # path relative to the workspace root
    op: str  # "create" | "append" | "replace" | "insert_after"
    text: str = ""  # content to write / append / insert, or the replacement
    old: str = ""  # for "replace": the span to find
    anchor: str = ""  # for "insert_after": the span to insert after


class PatchError(ValueError):
    pass


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.raw = self.root / "raw"
        self.wiki = self.root / "wiki"
        self.patterns = self.wiki / "patterns"
        self.skills = self.root / "skills"
        for d in (self.raw, self.patterns, self.skills):
            d.mkdir(parents=True, exist_ok=True)
        self._seed(self.wiki / "index.md", "# Wiki Index\n\nPattern pages:\n")
        self._seed(self.wiki / "logs.md", "# Evolution Log\n")
        self._seed(
            self.wiki / "skill-impact.md",
            "# Skill-Impact Tracker\n\n"
            "Append-only, never rolled back. One entry per validated proposal:\n"
            "the target skill, the diff, the validation score, and the outcome.\n",
        )

    @staticmethod
    def _seed(path: Path, content: str) -> None:
        if not path.exists():
            path.write_text(content)

    # ------------------------------------------------------------------ paths
    def _resolve(self, relpath: str) -> Path:
        p = (self.root / relpath).resolve()
        if not (p == self.root or self._is_within(p)):
            raise PatchError(f"path escapes workspace: {relpath}")
        return p

    def _is_within(self, p: Path) -> bool:
        try:
            p.relative_to(self.root)
            return True
        except ValueError:
            return False

    def read_file(self, relpath: str) -> str:
        p = self._resolve(relpath)
        if not p.is_file():
            raise FileNotFoundError(relpath)
        return p.read_text()

    def read_file_tool(self, relpath: str) -> str:
        """read_file for the ReAct proposer: never raises, returns an error string."""
        try:
            return self.read_file(relpath)
        except (FileNotFoundError, PatchError) as e:
            return f"[read_file error] {e}"

    def list_files(self, subdir: str = "") -> list[str]:
        base = self._resolve(subdir) if subdir else self.root
        if not base.exists():
            return []
        return sorted(
            str(p.relative_to(self.root))
            for p in base.rglob("*")
            if p.is_file()
        )

    # -------------------------------------------------------------- raw layer
    def write_trace(self, iteration: int, task_id: str, content: str) -> str:
        """Write an immutable rollout trace. Refuses to overwrite (write-once)."""
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", task_id)
        rel = f"raw/iter{iteration:03d}/{safe}.txt"
        p = self._resolve(rel)
        if p.exists():
            raise PatchError(f"raw trace already exists (write-once): {rel}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return rel

    # ---------------------------------------------------------- patch engine
    def apply_patch(self, patch: Patch) -> None:
        p = self._resolve(patch.target)
        if patch.op == "create":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(patch.text)
            return
        if patch.op == "append":
            p.parent.mkdir(parents=True, exist_ok=True)
            existing = p.read_text() if p.exists() else ""
            sep = "" if (not existing or existing.endswith("\n")) else "\n"
            p.write_text(existing + sep + patch.text)
            return
        if patch.op == "replace":
            self._require_file(p, patch.target)
            body = p.read_text()
            if not patch.old or patch.old not in body:
                raise PatchError(f"replace: span not found in {patch.target}")
            p.write_text(body.replace(patch.old, patch.text, 1))
            return
        if patch.op == "insert_after":
            self._require_file(p, patch.target)
            body = p.read_text()
            if not patch.anchor or patch.anchor not in body:
                raise PatchError(f"insert_after: anchor not found in {patch.target}")
            idx = body.index(patch.anchor) + len(patch.anchor)
            insert = patch.text if patch.text.startswith("\n") else "\n" + patch.text
            p.write_text(body[:idx] + insert + body[idx:])
            return
        raise PatchError(f"unknown patch op: {patch.op!r}")

    @staticmethod
    def _require_file(p: Path, rel: str) -> None:
        if not p.is_file():
            raise PatchError(f"target does not exist: {rel}")

    # -------------------------------------------------------------- wiki layer
    def append_log(self, text: str) -> None:
        self.apply_patch(Patch("wiki/logs.md", "append", text))

    def append_skill_impact(self, text: str) -> None:
        self.apply_patch(Patch("wiki/skill-impact.md", "append", text))

    def read_skill_impact(self) -> str:
        return self.read_file("wiki/skill-impact.md")

    def wiki_index(self) -> str:
        return self.read_file("wiki/index.md")

    def list_patterns(self) -> list[str]:
        return [f for f in self.list_files("wiki/patterns") if f.endswith(".md")]

    # ------------------------------------------------------------ skills layer
    def read_active_skills(self) -> str:
        """Concatenate every active SKILL.md — this is what the inference agent sees."""
        chunks = []
        for name in self.list_skill_names():
            body = self.read_file(f"skills/{name}/SKILL.md")
            chunks.append(f"## Skill: {name}\n{body.strip()}")
        return "\n\n".join(chunks)

    def list_skill_names(self) -> list[str]:
        if not self.skills.exists():
            return []
        return sorted(
            d.name
            for d in self.skills.iterdir()
            if d.is_dir() and (d / "SKILL.md").is_file()
        )

    def snapshot_skills(self) -> dict[str, str]:
        """Serialize the skills layer for skills-only rollback."""
        return {
            str(p.relative_to(self.skills)): p.read_text()
            for p in self.skills.rglob("*")
            if p.is_file()
        }

    def restore_skills(self, snapshot: dict[str, str]) -> None:
        """Rewrite the skills layer from a snapshot. Files added since are removed."""
        for p in list(self.skills.rglob("*")):
            if p.is_file():
                p.unlink()
        for rel, content in snapshot.items():
            dest = self.skills / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
        # drop now-empty dirs
        for d in sorted(self.skills.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
