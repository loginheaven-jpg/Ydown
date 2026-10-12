"""Create a portable ZIP using shared reads and an atomic final rename."""
from pathlib import Path
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import VERSION


def main():
    source = ROOT / "dist/YDown"
    archive = ROOT / f"dist/YDown-{VERSION}-windows-x64.zip"
    staging = archive.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for path in sorted(source.rglob("*")):
                if not path.is_file():
                    continue
                for attempt in range(4):
                    try:
                        bundle.write(path, path.relative_to(source.parent))
                        break
                    except PermissionError:
                        if attempt == 3:
                            raise
                        time.sleep(0.5 * (attempt + 1))
        staging.replace(archive)
    finally:
        staging.unlink(missing_ok=True)
    print("Portable ZIP ready: " + archive.name)


if __name__ == "__main__":
    main()
