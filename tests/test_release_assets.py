"""The release-asset contract: the names self_update downloads and unpacks must
be exactly what .github/workflows/release.yml publishes and kazbars.spec builds.
A rename on either side would silently break every install's self-update.

Run: `pytest tests/test_release_assets.py` (from repo root).
"""

from pathlib import Path

from kazbars import self_update as S

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
SPEC = (REPO / "kazbars.spec").read_text(encoding="utf-8")


def test_workflow_publishes_both_assets():
    files_block = WORKFLOW.split("files:", 1)[1]
    assert S.ZIP_ASSET in files_block and S.SHA_ASSET in files_block


def test_workflow_zips_the_root_self_update_expects():
    assert f'Compress-Archive -Path "dist/{S.ZIP_ROOT}"' in WORKFLOW


def test_workflow_sha_line_parses():
    assert f'  {S.ZIP_ASSET}"' in WORKFLOW            # the "$hash  KazBars.zip" template
    assert S.parse_sha256_file("0" * 64 + "  " + S.ZIP_ASSET) == "0" * 64


def test_spec_builds_the_expected_exe_and_folder():
    assert f'name="{S.ZIP_ROOT}"' in SPEC
    assert S.EXE_NAME == S.ZIP_ROOT + ".exe"
