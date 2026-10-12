"""Download verified build inputs; no system installation or PATH changes."""
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def download(url, destination, sha256):
    if destination.exists():
        with destination.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() == sha256:
                return
    print("Downloading " + destination.name, flush=True)
    with urllib.request.urlopen(url, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    with destination.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != sha256:
        destination.unlink()
        raise RuntimeError("Checksum mismatch for " + destination.name)


def main():
    manifest = json.loads((ROOT / "packaging/runtime-manifest.json").read_text())
    cache = ROOT / ".tools/cache"
    cache.mkdir(parents=True, exist_ok=True)
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    licenses = runtime / "licenses"
    licenses.mkdir(exist_ok=True)
    for name in ("ffmpeg", "node"):
        spec = manifest[name]
        archive = cache / spec["url"].split("/")[-1]
        download(spec["url"], archive, spec["sha256"])
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.namelist():
                if member.endswith("/"):
                    continue
                path = Path(member)
                if name == "ffmpeg" and path.parent.name == "bin" and path.name != "ffplay.exe":
                    destination = runtime / path.name
                elif name == "node" and path.name == "node.exe":
                    destination = runtime / path.name
                elif (path.name.lower().startswith(("license", "copying"))
                      or name == "ffmpeg" and "doc" in path.parts):
                    destination = licenses / name / Path(*path.parts[1:])
                else:
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
    shutil.copy2(ROOT / "packaging/runtime-manifest.json", licenses / "runtime-manifest.json")
    # Python's redistribution license belongs with the standalone interpreter.
    import sys
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, licenses / "Python-LICENSE.txt")
    print("Runtime ready: " + str(runtime), flush=True)


if __name__ == "__main__":
    main()
