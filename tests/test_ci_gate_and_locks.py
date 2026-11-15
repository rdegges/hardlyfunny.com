"""Gaps the config tests left open around the deploy gate, the hash-locked installs and Dependabot.

These read the same text files as test_deploy_config.py (there is no YAML parser in
requirements-dev.txt). Each test names the change it exists to catch.
"""

import importlib.metadata as metadata
import re

import pytest
from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from hardlyfunny.build import ROOT

WORKFLOW_DIR = ROOT / ".github" / "workflows"
WORKFLOWS = {path.name: path.read_text(encoding="utf-8") for path in sorted(WORKFLOW_DIR.glob("*.yml"))}
CI = WORKFLOWS["ci.yml"]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def job(name):
    match = re.search(rf"^  {name}:\n((?:    .*\n|\s*\n)*)", CI, re.M)
    assert match, f"no {name} job in ci.yml"
    return match.group(1)


def run_lines(text):
    return [line.strip() for line in text.splitlines() if re.match(r"\s*(?:- )?run: ", line)]


# --- the deploy gate ---------------------------------------------------------------------


def test_the_test_job_cannot_be_skipped_or_pass_vacuously():
    # deploy only `needs: test`, and a skipped job satisfies `needs` only when the dependent
    # also skips; a test job that is green without running pytest would publish anything.
    body = job("test")
    assert not re.search(r"^    (?:if|continue-on-error|needs|strategy):", body, re.M), "job-level condition on test"
    assert not re.search(r"^ +(?:- )?(?:if|continue-on-error):", body, re.M), "step-level condition on test"
    assert re.search(r"^      - run: python -m pytest -q$", body, re.M), "pytest must run bare, over the whole suite"
    assert re.search(r"^      - run: python -m hardlyfunny build$", body, re.M), "the build must be proven too"
    for line in run_lines(body):
        assert not re.search(r"\|\||;|\bset \+e\b|--co\b|--collect-only|--deselect|\s-k\s|--ignore|\|\s*tee", line), line


def test_pull_requests_and_main_pushes_always_run_ci():
    # A trigger filter is a way for a change to reach main without the test job ever starting.
    on = CI.split("\npermissions:", 1)[0]
    assert re.search(r"^  push:\n    branches: \[main\]\n", on, re.M), on
    pull_request = re.search(r"^  pull_request:[ \t]*\n((?:    .*\n)*)", on, re.M)
    assert pull_request is not None and pull_request.group(1) == "", "pull_request must have no filters"
    assert not re.search(r"^ +(?:paths|paths-ignore|branches-ignore|tags|tags-ignore):", on, re.M)
    assert "workflow_run" not in on and "pull_request_target" not in on


def test_deploy_builds_before_it_publishes_and_has_no_job_level_condition():
    deploy = job("deploy")
    assert not re.search(r"^    (?:if|continue-on-error):", deploy, re.M)
    order = [deploy.find(marker) for marker in
             ("run: pip install --require-hashes -r requirements.txt", "run: python -m hardlyfunny build",
              "run: npm ci", "run: npx cf deploy --dry-run", "run: npx cf deploy\n")]
    assert all(i >= 0 for i in order), order
    assert order == sorted(order), "install, build, npm ci, dry run, then publish"


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_workflow_permissions_are_read_only(name):
    text = WORKFLOWS[name]
    top = re.search(r"^permissions:\n((?:  .*\n)+)", text, re.M)
    assert top and top.group(1) == "  contents: read\n", f"{name}: top-level permissions must be exactly contents: read"
    for match in re.finditer(r"^( *)permissions:(.*)\n((?:\1  .*\n)*)", text, re.M):
        assert match.group(2).strip() == "", f"{name}: inline permissions {match.group(2)!r}"
        for scope in match.group(3).splitlines():
            assert re.fullmatch(r"\s+[\w-]+: (?:read|none)", scope), (name, scope)


# --- installs ----------------------------------------------------------------------------

INSTALLER = re.compile(r"\b(?:pip3?|pipx|uv|poetry|pdm|conda|mamba|easy_install|setup\.py)\b|-m pip\b|\bnpm (?:install|i|ci|add|update)\b|\byarn\b|\bpnpm\b")
ALLOWED_INSTALL = re.compile(r"(?:pip install --require-hashes -r requirements(?:-dev)?\.txt|npm ci)")


def test_no_workflow_command_installs_anything_but_the_locks():
    # The existing check only looks for the literal "pip install", so `pip3 install x` or
    # `python -m pip install x` walked past it.
    seen = []
    for name, text in WORKFLOWS.items():
        for line in run_lines(text):
            command = line.split("run: ", 1)[1]
            if INSTALLER.search(command):
                assert ALLOWED_INSTALL.fullmatch(command), (name, line)
                seen.append(command)
    assert seen.count("npm ci") == 1 and sum(c.startswith("pip install") for c in seen) == 3, seen


@pytest.mark.xfail(
    strict=True,
    reason="README's PNG recompression command runs an unhashed, unpinned `pip install -q pyoxipng`",
)
def test_readme_install_commands_are_hash_checked():
    for line in README.splitlines():
        for command in re.findall(r"pip install[^&\"`]*", line):
            assert "--require-hashes" in command, command


# --- the locks ---------------------------------------------------------------------------


def lock_entries(name):
    """[(package, version, marker or None)] for a hash-locked file."""
    text = (ROOT / name).read_text(encoding="utf-8")
    entries = []
    for entry in re.split(r"\n(?=\S)", text):
        match = re.match(r"([A-Za-z0-9_.-]+)==([\w.!+-]+)(?: ; ([^\\\n]+?))? \\\n", entry.strip() + "\n")
        if match:
            entries.append((canonicalize_name(match.group(1)), match.group(2), match.group(3)))
    return entries


@pytest.mark.parametrize("name", ["requirements.txt", "requirements-dev.txt"])
def test_the_running_environment_is_the_lock_and_the_lock_is_closed(name):
    # `pip install --require-hashes` already refuses a lock with a missing dependency, but only
    # at install time; this fails on the diff, and also catches a test run against loose versions.
    entries = lock_entries(name)
    assert entries
    locked = {package for package, _, _ in entries}
    for package, version, marker in entries:
        if marker and not Marker(marker).evaluate():
            continue
        dist = metadata.distribution(package)
        assert dist.version == version, f"{package}: installed {dist.version}, locked {version}"
        for requirement in map(Requirement, dist.requires or []):
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                assert canonicalize_name(requirement.name) in locked, f"{package} needs {requirement.name}, not in {name}"


def test_each_lock_sits_next_to_the_input_it_is_compiled_from():
    # Dependabot pairs requirements-x.in with requirements-x.txt by file name.
    for stem in ("requirements", "requirements-dev"):
        assert (ROOT / f"{stem}.in").exists() and (ROOT / f"{stem}.txt").exists(), stem


def test_lock_headers_are_the_commands_the_readme_documents():
    python = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    major_minor = ".".join(python.split(".")[:2])
    for stem, constraint in (("requirements", ""), ("requirements-dev", "-c requirements.txt ")):
        header = (ROOT / f"{stem}.txt").read_text(encoding="utf-8").splitlines()[:2]
        assert header[0] == "# This file was autogenerated by uv via the following command:", header
        command = header[1].removeprefix("#").strip()
        expected = (f"uv pip compile {stem}.in -o {stem}.txt {constraint}--generate-hashes --universal "
                    f"--python-version {major_minor} --no-annotate")
        assert command == expected, "regenerate with the documented command and the .python-version minor"
        assert command in README, f"README no longer documents: {command}"


# --- Dependabot --------------------------------------------------------------------------


@pytest.mark.parametrize("ecosystem", ["github-actions", "pip", "npm"])
def test_dependabot_cooldown_has_no_exemptions(ecosystem):
    config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    entry = re.search(rf"^  - package-ecosystem: {ecosystem}\n((?:    .*\n|\s*\n|  #.*\n)*)", config, re.M)
    assert entry, ecosystem
    cooldown = re.search(r"^    cooldown:\n((?:      .*\n)+)", entry.group(1), re.M)
    assert cooldown, f"{ecosystem}: no cooldown"
    # `exclude`/`include` or a shorter semver-*-days would quietly shrink the week this buys.
    assert cooldown.group(1) == "      default-days: 7\n", cooldown.group(1)
