"""Build curated source and manual-install component ZIPs, without local camera data."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from check_release import DOMAIN, ROOT, validate


def write_archive(archive: Path, files: list[Path], base: Path) -> None:
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(base).as_posix())
    with ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError("Archive integrity check failed")
        if any(
            "camera-inventory" in name or ".storage/" in name or "__pycache__" in name for name in bundle.namelist()
        ):
            raise ValueError("Local runtime data must not be packaged")
    print(f"Created {archive.name}: {len(files)} files, {archive.stat().st_size:,} bytes")


def main() -> None:
    manifest, files = validate()
    component = ROOT / "custom_components" / DOMAIN
    write_archive(ROOT / f"ha-isapi-vision-{manifest['version']}-source.zip", files, ROOT)
    component_files = [path for path in files if path.is_relative_to(component)]
    write_archive(ROOT / "isapi_vision.zip", component_files, component)


if __name__ == "__main__":
    main()
