"""tools/render_prompt.py (ROADMAP 2.8): the offline guard, and what --check calls broken.

The whole-fleet render runs in the prompt-render eval; these pin the parts that eval cannot
reach. Nothing in assemble_messages opens a connection today, so without the first test the
network block would be a guard nobody has seen go red.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

_TOOL = Path(__file__).resolve().parent.parent / "tools" / "render_prompt.py"
_spec = importlib.util.spec_from_file_location("render_prompt", _TOOL)
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)


def test_block_network_makes_every_connect_raise():
    # A fresh process: the block patches the socket module for the whole process.
    code = (
        "import importlib.util, socket, sys\n"
        f"s = importlib.util.spec_from_file_location('rp', {str(_TOOL)!r})\n"
        "m = importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
        "m._block_network()\n"
        "hits = 0\n"
        "for call in (lambda: socket.create_connection(('127.0.0.1', 9), timeout=1),\n"
        "             lambda: socket.socket().connect(('127.0.0.1', 9)),\n"
        "             lambda: socket.socket().connect_ex(('127.0.0.1', 9))):\n"
        "    try:\n"
        "        call()\n"
        "    except RuntimeError as e:\n"
        "        hits += 'render_prompt is offline' in str(e)\n"
        "    except OSError:\n"
        "        pass\n"
        "print(hits)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "3", out.stderr


def _result(**over):
    r = {
        "preset_layers": ["preset-core.txt"],
        "preset_texts": ["CORE"],
        "post_history": "PHI",
        "messages": [
            {"role": "system", "content": "You are X."},
            {"role": "system", "content": "PHI"},
            {"role": "system", "content": "CORE"},
            {"role": "user", "content": "hi"},
        ],
    }
    r.update(over)
    return r


def test_whole_prompt_has_no_problems():
    assert rp._problems(_result()) == []


def test_missing_layer_file_is_a_problem():
    probs = rp._problems(_result(preset_layers=["preset.txt (fallback)"]))
    assert any("fell back" in p for p in probs)


def test_loaded_layer_absent_from_prompt_is_a_problem():
    probs = rp._problems(_result(preset_texts=["CORE, edited"]))
    assert any("preset-core.txt loaded but is not in the prompt" in p for p in probs)


def test_dropped_post_history_is_a_problem():
    probs = rp._problems(_result(post_history="PHI, edited"))
    assert any("post_history_instructions" in p for p in probs)


def test_unfilled_placeholder_is_a_problem():
    r = _result()
    r["messages"][2] = {"role": "system", "content": "{{char}} texts {{user}}"}
    r["preset_texts"] = ["{{char}} texts {{user}}"]
    assert any("placeholder" in p for p in rp._problems(r))


def test_prompt_must_start_with_system_and_end_with_user():
    r = _result()
    r["messages"] = [{"role": "user", "content": "hi"}] + r["messages"][1:3] + [
        {"role": "assistant", "content": "x"}]
    probs = rp._problems(r)
    assert any("first message" in p for p in probs)
    assert any("last message" in p for p in probs)


def test_instances_table_matches_the_repo():
    # A renamed card or a new instance must reach this table, or --all silently skips it.
    bot_dir = _TOOL.parent.parent
    for name, (card, layers) in rp.INSTANCES.items():
        assert (bot_dir / card).is_file(), card
        assert (bot_dir / name).is_dir(), name
        for layer in layers:
            assert (bot_dir / layer).is_file(), layer


def test_instances_stacks_match_env_example():
    # The stacks are copied from .env.example's "Recommended stacks" table (the live .env
    # files are on the VPS). A stack changed in one place and not the other makes every
    # render describe a prompt no instance sends.
    import re
    doc = (_TOOL.parent.parent / ".env.example").read_text()
    table = doc.split("# Recommended stacks", 1)[1].split("\n#\n", 1)[0]
    documented = {m.group(1): m.group(2).split(",")
                  for m in re.finditer(r"^#\s+(\w+)\s+([a-z,]+)\s+\d+", table, re.M)}
    assert set(documented) == set(rp.INSTANCES)
    for name, (_card, layers) in rp.INSTANCES.items():
        assert [f"preset-{s}.txt" for s in documented[name]] == layers, name
