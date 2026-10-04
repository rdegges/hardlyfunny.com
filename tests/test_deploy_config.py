"""The seams between the Python build and the Cloudflare deploy tooling.

The deploy config is TypeScript and the CI workflow is YAML, and neither has a parser in
requirements-dev.txt, so these are text checks of the few settings the site depends on.
"""

import importlib.util
import re
import subprocess
import sys
import textwrap

import pytest

from hardlyfunny.build import ROOT

WRANGLER = (ROOT / "wrangler.config.ts").read_text(encoding="utf-8")
CLOUDFLARE = (ROOT / "cloudflare.config.ts").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
GITIGNORE = (ROOT / ".gitignore").read_text(encoding="utf-8").split()


def job(name):
    """The lines of one top-level job in ci.yml."""
    match = re.search(rf"^  {name}:\n((?:    .*\n|\s*\n)*)", CI, re.M)
    assert match, f"no {name} job in ci.yml"
    return match.group(1)


def test_cloudflare_uploads_the_directory_the_build_writes():
    # `python -m hardlyfunny build` defaults to ROOT/_site; deploying any other directory
    # publishes a stale or empty site without an error.
    assert re.search(r'assetsDirectory:\s*"_site"', WRANGLER)
    source = (ROOT / "hardlyfunny" / "__main__.py").read_text(encoding="utf-8")
    assert re.search(r'"--out".*default=ROOT / "_site"', source)


def test_missing_pages_get_the_404_page_the_build_writes(built):
    assert re.search(r'notFoundHandling:\s*"404-page"', CLOUDFLARE)
    assert (built / "404.html").exists()


def test_pretty_urls_resolve_to_index_html(built, site):
    # Comic pages are /comics/<slug>/index.html; without this the runtime only serves the full path.
    assert re.search(r'htmlHandling:\s*"auto-trailing-slash"', CLOUDFLARE)
    assert (built / "comics" / site.comics[0].slug / "index.html").exists()


def test_deploy_waits_for_tests_and_only_main_pushes_publish():
    deploy = job("deploy")
    assert re.search(r"^    needs: test$", deploy, re.M), "a red build must not reach the live site"
    real = re.findall(r"^      - if: (.*)\n        run: npx cf deploy$", deploy, re.M)
    assert real == ["github.event_name == 'push' && github.ref == 'refs/heads/main'"]
    dry = re.findall(r"^      - if: (.*)\n        run: npx cf deploy --dry-run$", deploy, re.M)
    assert dry == ["github.event_name == 'pull_request'"]
    # Deploys must queue, never cancel each other halfway through an upload.
    assert re.search(r"cancel-in-progress: false", deploy)
    # A queued PR dry run must not replace a queued production deploy, so only main pushes share the group.
    assert re.search(r"group: \$\{\{ github.event_name == 'push' && github.ref == 'refs/heads/main' && 'deploy-production' \|\|", deploy)


def test_deploy_secrets_are_scoped_to_the_publishing_step():
    deploy = job("deploy")
    # Only the step that publishes sees the token; the dry run and the build don't.
    assert CI.count("secrets.CLOUDFLARE_API_TOKEN") == 1
    step = deploy.split("run: npx cf deploy\n", 1)[1]
    assert "secrets.CLOUDFLARE_API_TOKEN" in step and "secrets.CLOUDFLARE_ACCOUNT_ID" in step


def test_generated_deploy_state_is_not_committed():
    for path in ("_site/", "node_modules/", ".cloudflare/", ".wrangler/"):
        assert path in GITIGNORE, path


def test_verify_checks_the_live_domain_after_each_production_deploy():
    verify = job("verify")
    assert re.search(r"^    needs: deploy$", verify, re.M)
    assert re.search(r"^    if: github.event_name == 'push' && github.ref == 'refs/heads/main'$", verify, re.M)
    assert "HARDLYFUNNY_RUNTIME_URL: https://hardlyfunny.com" in verify
    assert re.search(r"group: verify-production\n\s+cancel-in-progress: true", verify)
    assert "tests/test_cloudflare_runtime.py tests/test_live_domain.py --junitxml=verify.xml" in verify
    # The suites skip themselves without a URL; a run with no tests or any skip must fail.
    assert "sys.exit(0 if tests > 0 and skipped == 0 else 1)" in verify
    # continue-on-error would turn a red verify green without anyone noticing.
    assert "continue-on-error" not in verify


def verify_gate():
    """The Python the verify job's last step runs, as it appears in ci.yml."""
    match = re.search(r"python - <<'PY'\n(.*?)\n\s*PY\n", job("verify"), re.S)
    assert match, "no gate script in the verify job"
    return textwrap.dedent(match.group(1))


@pytest.mark.parametrize("tests, passes", [
    ("def test_a(): pass\ndef test_b(): pass\n", True),
    ("import pytest\ndef test_a(): pass\n@pytest.mark.skip\ndef test_b(): pass\n", False),
    ("import pytest\npytestmark = pytest.mark.skip\ndef test_a(): pass\n", False),
    ("", False),
], ids=["all-ran", "one-skipped", "all-skipped", "none-collected"])
def test_verify_gate_passes_only_when_every_live_test_ran(tmp_path, tests, passes):
    # Runs the real gate on real pytest JUnit output: the string check above can't tell whether
    # the script reads the XML pytest writes (root <testsuites>, counts on the inner <testsuite>).
    (tmp_path / "test_live.py").write_text(tests)
    subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_live.py",
                    "--junitxml=verify.xml"], cwd=tmp_path, capture_output=True)
    gate = subprocess.run([sys.executable, "-c", verify_gate()], cwd=tmp_path, capture_output=True, text=True)
    assert (gate.returncode == 0) == passes, gate.stdout + gate.stderr


@pytest.mark.parametrize("url, runs", [
    ("https://hardlyfunny.com", True),
    ("https://hardlyfunny.com/", True),
    ("", False),
    ("http://hardlyfunny.com", False),
    ("http://localhost:8787", False),
    ("https://localhost:8787", False),
    ("http://127.0.0.1:8787", False),
    ("https://hardlyfunny.randall-degges.workers.dev", False),
    ("https://HARDLYFUNNY.Randall-Degges.Workers.Dev", False),
], ids=lambda v: v if isinstance(v, str) and v else repr(v))
def test_live_domain_suite_runs_only_against_an_https_custom_domain(monkeypatch, url, runs):
    # The verify job fails on any skip, and the preview/cf dev runs would fail its www and
    # http checks, so this condition decides whether both stay green.
    monkeypatch.setenv("HARDLYFUNNY_RUNTIME_URL", url)
    spec = importlib.util.spec_from_file_location("live_domain_probe", ROOT / "tests" / "test_live_domain.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.pytestmark.args[0] is not runs


def uncommented(ts):
    """TypeScript without its comments. `(^|\\s)//` leaves the `//` in "https://" strings alone."""
    ts = re.sub(r"/\*.*?\*/", "", ts, flags=re.S)
    return re.sub(r"(^|\s)//.*$", r"\1", ts, flags=re.M)


def settings(ts, key):
    """Every value `key` is set to outside comments."""
    return re.findall(rf"\b{key}:\s*(\w+)", uncommented(ts))


def test_the_worker_serves_only_the_site_url(site):
    # The custom domain must be the host the build writes into canonicals, feeds and share cards.
    from urllib.parse import urlsplit
    # Commented-out settings don't count: commenting `domains` out is the obvious wrong way to detach it.
    code = uncommented(CLOUDFLARE)
    domains = re.search(r"domains:\s*\[([^\]]*)\]", code)
    assert domains and re.findall(r'"([^"]+)"', domains.group(1)) == [urlsplit(site.url).hostname]
    # Exactly one setting each: a second copy elsewhere in the file could turn a host back on.
    assert settings(CLOUDFLARE, "workersDev") == ["false"]
    assert settings(CLOUDFLARE, "previewUrls") == ["false"]


ON = "    workersDev: false,\n    previewUrls: false,\n"


@pytest.mark.parametrize("block, workers_dev, preview_urls", [
    (ON, ["false"], ["false"]),
    ("    workersDev: true,\n    previewUrls: false,\n", ["true"], ["false"]),
    ("    workersDev: false,\n", ["false"], []),
    ("    workersDev: false, // previewUrls: false\n", ["false"], []),
    ("    previewUrls: true, // was previewUrls: false\n    workersDev: false,\n", ["false"], ["true"]),
    ("    /* workersDev: false, */\n    previewUrls: false,\n", [], ["false"]),
    ("    /*\n    workersDev: false,\n    */\n    previewUrls: false,\n", [], ["false"]),
    ('    workersDev: false,\n    previewUrls: false,\n    note: "https://x.workers.dev",\n', ["false"], ["false"]),
    (ON + "    env: { staging: { workersDev: true } },\n", ["false", "true"], ["false"]),
], ids=["as-shipped", "workers-dev-on", "previews-unset", "previews-only-in-trailing-comment",
        "previews-on-with-false-in-comment", "workers-dev-in-block-comment", "workers-dev-in-multiline-comment",
        "url-string-kept", "second-copy-elsewhere"])
def test_subdomain_settings_ignore_comments_and_see_every_copy(block, workers_dev, preview_urls):
    # Pins the parsing the test above relies on: each case here passed the earlier
    # whole-line-comment regex while leaving workers.dev or Preview URLs on (or unset).
    ts = CLOUDFLARE.replace(ON, block)
    assert ON in CLOUDFLARE
    assert settings(ts, "workersDev") == workers_dev
    assert settings(ts, "previewUrls") == preview_urls
