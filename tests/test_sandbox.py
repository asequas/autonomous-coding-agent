from pathlib import Path

import pytest

from aiagent.sandbox import SandboxError, Workspace


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "app"
    root.mkdir()
    return root


def test_resolves_paths_inside_root(root: Path) -> None:
    ws = Workspace(root)
    assert ws.resolve("pkg/mod.py") == root.resolve() / "pkg" / "mod.py"
    assert ws.resolve() == root.resolve()
    assert ws.resolve("pkg/../mod.py") == root.resolve() / "mod.py"


@pytest.mark.parametrize("path", ["..", "../secret.txt", "pkg/../../x", "/etc/passwd"])
def test_rejects_paths_outside_root(root: Path, path: str) -> None:
    with pytest.raises(SandboxError):
        Workspace(root).resolve(path)


def test_rejects_sibling_directory_sharing_a_prefix(root: Path) -> None:
    # The original implementation used str.startswith, which accepted this.
    sibling = root.parent / "app_evil"
    sibling.mkdir()
    with pytest.raises(SandboxError):
        Workspace(root).resolve("../app_evil/x.py")


def test_rejects_symlink_pointing_outside(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (root / "link.txt").symlink_to(outside)
    ws = Workspace(root)
    with pytest.raises(SandboxError):
        ws.resolve("link.txt")
    assert list(ws.iter_files()) == []


def test_iter_files_skips_ignored_directories(root: Path) -> None:
    for rel in ["a.py", "pkg/b.py", ".git/config", ".venv/lib.py", "pkg/__pycache__/b.pyc"]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    ws = Workspace(root)
    assert [ws.relative(p) for p in ws.iter_files()] == ["a.py", "pkg/b.py"]


def test_root_must_be_a_directory(tmp_path: Path) -> None:
    with pytest.raises(SandboxError):
        Workspace(tmp_path / "missing")
