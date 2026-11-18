"""Every file in the framework that starts with #! is run directly (stage.sh, resolve.sh, stages-run.py ...), so it must be
executable. Sourced helpers (lib.sh, gnome.sh) have no #! line and are not checked.

Scripts committed from an NTFS checkout lost the bit without anyone noticing, because NTFS shows every file as executable and
git there has core.fileMode=false; on ext4 `uitest stages run` then failed with PermissionError on stages/resolve.sh (#91).
This test reads the bit from the checkout, so it catches the problem on any filesystem that keeps modes (ext4, the CI
runners); on NTFS every file is executable and it cannot fail. The test image has no git, so it cannot read git's index.

Git-ignored folders (work files, results) are skipped: they are not part of the framework. Their names come from the root
.gitignore and the framework's own .gitignore, so the list stays in step with them."""
import os
import stat

from oolite_ui_test_framework import hostrun

FRAMEWORK = hostrun.PKG
ROOT_PREFIX = "/tools/oolite-ui-test-framework/"
ALWAYS_SKIP = {".git", "__pycache__", ".pytest_cache"}


def ignored_folders():
    """Top-level folder names of the framework that git ignores."""
    names = set()
    root_gitignore = os.path.join(FRAMEWORK, "..", "..", ".gitignore")
    if os.path.isfile(root_gitignore):
        for line in open(root_gitignore, errors="replace"):
            line = line.strip()
            if line.startswith(ROOT_PREFIX):
                names.add(line[len(ROOT_PREFIX):].strip("/"))
    own = os.path.join(FRAMEWORK, ".gitignore")
    if os.path.isfile(own):
        for line in open(own, errors="replace"):
            line = line.strip()
            if line and not line.startswith("#"):
                names.add(line.strip("/"))
    return names


def scripts():
    """Paths, relative to the framework, of the files that start with #!."""
    skip_top = ignored_folders()
    found = []
    for dirpath, dirnames, filenames in os.walk(FRAMEWORK):
        rel_dir = os.path.relpath(dirpath, FRAMEWORK)
        dirnames[:] = [d for d in dirnames
                       if d not in ALWAYS_SKIP and not (rel_dir == "." and d in skip_top)]
        for name in filenames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                continue
            with open(path, "rb") as f:
                if f.read(2) == b"#!":
                    found.append(os.path.relpath(path, FRAMEWORK))
    return sorted(found)


def test_finds_the_stage_scripts():
    # guards the walk itself: if it found nothing, the next test would pass without checking anything
    found = scripts()
    assert "stages/resolve.sh" in found and "stages/bin/stage.sh" in found, found


def test_skips_the_sourced_helpers():
    found = scripts()
    assert "stages/common/lib.sh" not in found
    assert "stages/desktops/gnome/wayland/gnome.sh" not in found


def test_every_script_is_executable():
    not_exec = [p for p in scripts() if not os.stat(os.path.join(FRAMEWORK, p)).st_mode & stat.S_IXUSR]
    assert not not_exec, (
        "these files start with #! but are not executable, so running them fails with PermissionError on ext4. "
        "Fix with: git update-index --chmod=+x " + " ".join("tools/oolite-ui-test-framework/" + p for p in not_exec))
