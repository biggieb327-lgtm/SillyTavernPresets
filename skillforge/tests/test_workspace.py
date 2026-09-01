import pytest

from skillforge.workspace import Patch, PatchError, Workspace


def test_layers_are_seeded(tmp_path):
    ws = Workspace(tmp_path / "wk")
    assert (ws.wiki / "index.md").exists()
    assert (ws.wiki / "logs.md").exists()
    assert (ws.wiki / "skill-impact.md").exists()
    assert ws.raw.is_dir() and ws.patterns.is_dir() and ws.skills.is_dir()


def test_raw_traces_are_write_once(tmp_path):
    ws = Workspace(tmp_path / "wk")
    rel = ws.write_trace(0, "task/1", "trace body")
    assert ws.read_file(rel) == "trace body"
    with pytest.raises(PatchError, match="write-once"):
        ws.write_trace(0, "task/1", "different")


def test_patch_ops(tmp_path):
    ws = Workspace(tmp_path / "wk")
    ws.apply_patch(Patch("wiki/patterns/p.md", "create", "line one\n"))
    ws.apply_patch(Patch("wiki/patterns/p.md", "append", "line two\n"))
    assert ws.read_file("wiki/patterns/p.md") == "line one\nline two\n"

    ws.apply_patch(Patch("wiki/patterns/p.md", "replace", old="line two", text="LINE 2"))
    assert "LINE 2" in ws.read_file("wiki/patterns/p.md")

    ws.apply_patch(Patch("wiki/patterns/p.md", "insert_after", anchor="line one", text="inserted"))
    assert ws.read_file("wiki/patterns/p.md").splitlines()[1] == "inserted"


def test_patch_errors(tmp_path):
    ws = Workspace(tmp_path / "wk")
    ws.apply_patch(Patch("wiki/patterns/p.md", "create", "hello"))
    with pytest.raises(PatchError, match="span not found"):
        ws.apply_patch(Patch("wiki/patterns/p.md", "replace", old="absent", text="x"))
    with pytest.raises(PatchError, match="anchor not found"):
        ws.apply_patch(Patch("wiki/patterns/p.md", "insert_after", anchor="absent", text="x"))
    with pytest.raises(PatchError, match="does not exist"):
        ws.apply_patch(Patch("wiki/patterns/missing.md", "replace", old="a", text="b"))


def test_path_escape_is_blocked(tmp_path):
    ws = Workspace(tmp_path / "wk")
    with pytest.raises(PatchError, match="escapes workspace"):
        ws.read_file("../secret")
    assert "error" in ws.read_file_tool("../secret").lower()


def test_active_skill_injection(tmp_path):
    ws = Workspace(tmp_path / "wk")
    ws.apply_patch(Patch("skills/alpha/SKILL.md", "create", "do alpha"))
    ws.apply_patch(Patch("skills/beta/SKILL.md", "create", "do beta"))
    assert ws.list_skill_names() == ["alpha", "beta"]
    injected = ws.read_active_skills()
    assert "Skill: alpha" in injected and "do beta" in injected


def test_skills_snapshot_and_rollback(tmp_path):
    ws = Workspace(tmp_path / "wk")
    ws.apply_patch(Patch("skills/alpha/SKILL.md", "create", "v1"))
    snap = ws.snapshot_skills()

    # Mutate: edit alpha and add a new skill.
    ws.apply_patch(Patch("skills/alpha/SKILL.md", "replace", old="v1", text="v2"))
    ws.apply_patch(Patch("skills/gamma/SKILL.md", "create", "new"))
    assert ws.list_skill_names() == ["alpha", "gamma"]

    ws.restore_skills(snap)
    assert ws.list_skill_names() == ["alpha"]
    assert ws.read_file("skills/alpha/SKILL.md") == "v1"


def test_wiki_has_no_rollback(tmp_path):
    """The wiki is permanent by construction: there is no restore method for it."""
    ws = Workspace(tmp_path / "wk")
    assert not hasattr(ws, "restore_wiki")
    assert hasattr(ws, "restore_skills")
