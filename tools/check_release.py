"""Check public distribution metadata and reject local data from the publishable tree."""

import ast
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "isapi_vision"
REPOSITORY = "https://github.com/RealBlueSky227/ha-isapi-vision"
DIRECTORIES = ("custom_components", "tools", "tests", "tests_ha", "examples", "assets", ".github", "docs")
ROOT_FILES = (
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "BRANDING.md",
    "QUALITY.md",
    "VALIDATION.md",
    "DEPLOYMENT.md",
    "hacs.json",
    "pyproject.toml",
    "requirements-dev.txt",
    "requirements-test-ha.txt",
    ".gitignore",
    ".gitattributes",
)
EXCLUDED = {"__pycache__", ".pytest_cache", ".ruff_cache"}


def distribution_files():
    """Explicit source allowlist; never package Git, runtime config, snapshots or inventories."""
    files = [ROOT / name for name in ROOT_FILES]
    for directory in DIRECTORIES:
        files.extend(
            path
            for path in (ROOT / directory).rglob("*")
            if path.is_file()
            and not EXCLUDED.intersection(path.relative_to(ROOT).parts)
            and path.suffix not in {".pyc", ".zip"}
        )
    return sorted(files)


def validate():
    component = ROOT / "custom_components" / DOMAIN
    manifest = json.loads((component / "manifest.json").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert manifest["domain"] == DOMAIN
    assert manifest["name"] == hacs["name"] == "ISAPI Vision"
    assert manifest["version"] == project["version"] == "0.1.0b1"
    assert manifest["documentation"] == REPOSITORY + "/blob/main/README.md"
    assert manifest["issue_tracker"] == REPOSITORY + "/issues"
    assert manifest["iot_class"] == "local_push" and manifest["config_flow"] is True
    assert manifest["requirements"] == []
    assert (component / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()
    assert hacs["homeassistant"] == "2025.7.0"
    assert len([path for path in component.parent.iterdir() if path.is_dir() and path.name != "__pycache__"]) == 1
    assert json.loads((component / "strings.json").read_text()) == json.loads(
        (component / "translations/en.json").read_text()
    )
    forbidden = re.compile(
        r"\b(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b"
        r"|\bgh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]+|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"
    )
    for path in distribution_files():
        assert path.is_file(), f"Missing public release file: {path.name}"
        if path.suffix == ".png":
            assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
            continue
        content = path.read_text(encoding="utf-8")
        assert not forbidden.search(content), f"Private data or credential material in {path.relative_to(ROOT)}"
        assert not any(name in path.parts for name in (".storage", ".git"))
        if path.suffix == ".py":
            ast.parse(content, filename=str(path))
        elif path.suffix == ".json":
            json.loads(content)
    return manifest, distribution_files()


if __name__ == "__main__":
    _, files = validate()
    print(f"Public release contract passed: {len(files)} allowlisted files; no local inventory/configuration included.")
