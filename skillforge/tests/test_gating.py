"""The gate is the heart of the method; its asymmetric rollback is pinned here."""

from skillforge.agents import SkillProposal
from skillforge.gating import gate
from skillforge.workspace import Patch, Workspace


def _proposal(skill, op, **kw):
    return SkillProposal(
        skill=skill,
        patch=Patch(target=f"skills/{skill}/SKILL.md", op=op, **kw),
        rationale="test",
    )


def test_accept_on_strict_improvement():
    import tempfile

    ws = Workspace(tempfile.mkdtemp())
    prop = _proposal("s", "create", text="body")
    r_best, out = gate(ws, prop, validator=lambda: 0.8, r_best=0.5, iteration=1)
    assert out.accepted and r_best == 0.8
    assert ws.list_skill_names() == ["s"]  # skill kept
    assert "Accepted" in ws.read_skill_impact()


def test_reject_rolls_back_skills_but_not_wiki():
    import tempfile

    ws = Workspace(tempfile.mkdtemp())
    # Grow the wiki first; it must survive a rejected skill proposal.
    ws.append_log("- pre-existing knowledge")
    wiki_before = ws.read_file("wiki/logs.md")

    prop = _proposal("s", "create", text="body")
    # equal score is NOT a strict improvement -> reject (paper: strict '>').
    r_best, out = gate(ws, prop, validator=lambda: 0.5, r_best=0.5, iteration=1)

    assert not out.accepted and r_best == 0.5
    assert ws.list_skill_names() == []  # skill rolled back
    assert ws.read_file("wiki/logs.md") == wiki_before  # wiki untouched
    assert "Rejected" in ws.read_skill_impact()  # but the attempt is recorded


def test_neutral_proposal_is_rejected():
    import tempfile

    ws = Workspace(tempfile.mkdtemp())
    prop = _proposal("s", "create", text="body")
    _, out = gate(ws, prop, validator=lambda: 0.5, r_best=0.5, iteration=1)
    assert not out.accepted  # strict improvement required


def test_invalid_patch_is_rejected_and_recorded():
    import tempfile

    ws = Workspace(tempfile.mkdtemp())
    scored = {"n": 0}

    def validator():
        scored["n"] += 1
        return 1.0

    # replace on a file that does not exist -> PatchError -> rejected, validator not run.
    prop = _proposal("s", "replace", old="absent", text="x")
    r_best, out = gate(ws, prop, validator=validator, r_best=0.0, iteration=3)
    assert not out.accepted and out.error
    assert scored["n"] == 0  # never validated an unapplied change
    assert ws.list_skill_names() == []
    assert "invalid patch" in out.label.lower()


def test_rejected_edit_leaves_prior_skill_intact():
    import tempfile

    ws = Workspace(tempfile.mkdtemp())
    # Accept a first skill.
    gate(ws, _proposal("s", "create", text="v1"), validator=lambda: 0.6, r_best=0.0, iteration=1)
    # A regressive edit to it must roll the file back to v1.
    gate(ws, _proposal("s", "append", text="\nv2-noise"), validator=lambda: 0.3, r_best=0.6, iteration=2)
    assert ws.read_file("skills/s/SKILL.md") == "v1"
