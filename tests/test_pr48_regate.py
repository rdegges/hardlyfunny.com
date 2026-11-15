"""Gaps found when PR #48 was re-gated at f2a2a97 (Dependabot moved from pip to uv, PNG lock check added to CI).

Each test names the mutation that got past the existing suite. They read the same plain text files as
test_ci_gate_and_locks.py and test_deploy_config.py, so none of them touch the network.
"""

import re

import pytest

from hardlyfunny.build import ROOT

DEPENDABOT = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
WORKFLOWS = {path.name: path.read_text(encoding="utf-8") for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))}
CI = WORKFLOWS["ci.yml"]
LOCKS = ("requirements.txt", "requirements-dev.txt", "requirements-png.txt")


def dependabot_entries():
    """{ecosystem: body} for every `- package-ecosystem:` entry actually in dependabot.yml."""
    parts = re.split(r"^  - package-ecosystem: (\S+)\n", DEPENDABOT, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2]))


def test_dependabot_has_a_seven_day_cooldown_on_every_ecosystem_in_the_file():
    # The cooldown tests name three ecosystems, so a fourth (say `docker`) added with a short cooldown, or
    # none, passed them. This reads the ecosystems from the file itself.
    entries = dependabot_entries()
    assert {"github-actions", "uv", "npm"} <= entries.keys(), entries.keys()
    for ecosystem, body in entries.items():
        cooldown = re.search(r"^    cooldown:\n((?:      .*\n)+)", body, re.M)
        assert cooldown, f"{ecosystem}: no cooldown"
        assert cooldown.group(1) == "      default-days: 7\n", (ecosystem, cooldown.group(1))


def test_dependabot_never_regenerates_the_locks_with_pip_tools_in_any_directory():
    # `pip` anywhere in the file, not only as the root entry, would run pip-compile over these locks
    # and drop the Windows-only colorama pin.
    assert "pip" not in dependabot_entries(), "the pip ecosystem drops colorama from the --universal locks"
    assert not re.search(r"package-ecosystem:\s*[\"']?pip[\"']?\s*$", DEPENDABOT, re.M)


@pytest.mark.parametrize("name", LOCKS)
def test_lock_header_is_exactly_the_two_comment_lines_uv_writes(name):
    # The header tests read only the first two lines, so a hand-written note on line 3 (the one the
    # README used to carry) passed them. Dependabot's uv updater keeps every leading `#` line, so a
    # note added once would stay in the lock for good.
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    assert [line for line in lines if line.startswith("#")] == lines[:2], f"{name} has a comment beyond uv's header"
    assert lines[2] and not lines[2].startswith("#"), f"{name}: the third line must be the first pin"


COLORAMA_0_4_6_HASHES = {
    # sdist and wheel, checked against PyPI with `pip download --require-hashes`.
    "08695f5cb7ed6e0531a20572697297273c47b8cae5a63ffc6d6ed5c201be6e44",
    "4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6",
}


def test_colorama_hashes_in_the_dev_lock_are_the_published_ones():
    # colorama only installs on Windows, so neither `pip install --require-hashes` in CI nor the PNG
    # `pip download` check ever compares its hashes with PyPI; one corrupted hash passed every test.
    dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    block = re.search(r"^colorama==([\w.]+) ; sys_platform == 'win32' \\\n((?:    --hash=sha256:[0-9a-f]{64} ?\\?\n)+)", dev, re.M)
    assert block, "colorama is not locked behind its Windows marker with hashes"
    hashes = set(re.findall(r"[0-9a-f]{64}", block.group(2)))
    assert len(hashes) >= 2, "expect the wheel and the sdist"
    if block.group(1) == "0.4.6":
        assert hashes == COLORAMA_0_4_6_HASHES
    # Another version needs its own hashes checked against PyPI by hand; this test then only checks shape.


def png_check_command():
    lines = [line.strip() for line in CI.splitlines() if "requirements-png.txt" in line and "run:" in line]
    assert len(lines) == 1, lines
    return lines[0].split("run: ", 1)[1]


def test_ci_png_lock_check_targets_the_interpreter_the_png_lock_was_resolved_for():
    # The step hardcodes 3.13 / cp313. If the PNG lock and the README's Docker image move to another
    # Python, the step would keep proving hashes for wheels nobody installs, and every test stayed green.
    header = (ROOT / "requirements-png.txt").read_text(encoding="utf-8").splitlines()[1]
    major, minor = re.search(r"--python-version (\d+)\.(\d+)", header).groups()
    command = png_check_command()
    assert re.search(rf"--python-version {major}\.{minor}(?: |$)", command), (command, header)
    assert re.search(rf"--abi cp{major}{minor}(?: |$)", command), (command, header)
    assert re.search(r"--implementation cp(?: |$)", command)


INDICATORS = "@`%*&!{[?|>"


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_single_line_workflow_values_parse_as_yaml_scalars(name):
    # The plain-scalar test covers `: ` and ` #` in `run:` only. GitHub rejects the whole file for a plain
    # value that starts with a YAML indicator, or a quoted value that is not closed, and for the same
    # `: ` in `name:` or `if:`. All of these passed the other tests.
    for line in WORKFLOWS[name].splitlines():
        match = re.match(r"\s*(?:- )?(?P<key>run|name|if): (?P<value>\S.*)$", line)
        if not match:
            continue
        value = match.group("value")
        if value[0] in "|>" and re.fullmatch(r"[|>][+-]?\d?\s*(?:#.*)?", value):
            continue
        if value[0] == '"':
            assert re.fullmatch(r'"(?:[^"\\]|\\.)*"\s*(?:#.*)?', value), (name, line)
        elif value[0] == "'":
            assert re.fullmatch(r"'(?:[^']|'')*'\s*(?:#.*)?", value), (name, line)
        else:
            assert value[0] not in INDICATORS, (name, line)
            assert ": " not in value and not value.endswith(":") and " #" not in value, (name, line)
