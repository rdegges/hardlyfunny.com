"""The seams between the Python build and the Cloudflare deploy tooling.

The deploy config is TypeScript and the CI workflow is YAML, and neither has a parser in
requirements-dev.txt, so these are text checks of the few settings the site depends on.
"""

import re

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
