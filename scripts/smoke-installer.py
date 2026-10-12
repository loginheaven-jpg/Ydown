"""Install/reinstall into a temporary directory and run the installed bundle."""
from pathlib import Path
import subprocess
import sys
import tempfile
import winreg

UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{D79B9FF0-C25D-47B2-9FAC-B7AA677EAC6B}_is1"


def main():
    # Do not replace a real user's installed app or its uninstall registration.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY):
            print("Installer smoke skipped: a YDown installation already exists")
            return
    except FileNotFoundError:
        pass
    installer = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="ydown-installer-") as work:
        target = Path(work) / "YDown"
        command = [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                   "/NOICONS", "/TASKS=", "/DIR=" + str(target)]
        try:
            subprocess.run(command, check=True, timeout=120)
            assert (target / "YDown.exe").is_file()
            sentinel = target / "keep-on-reinstall.txt"
            sentinel.write_text("preserve user file", encoding="utf-8")
            subprocess.run(command, check=True, timeout=120)
            assert sentinel.read_text(encoding="utf-8") == "preserve user file"
            subprocess.run([sys.executable, str(Path(__file__).with_name("smoke-bundle.py")),
                            str(target / "YDown.exe")], check=True, timeout=90)
            print("Installer smoke passed: install, reinstall, preserve files, installed app startup")
        finally:
            uninstaller = target / "unins000.exe"
            if uninstaller.exists():
                subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                               check=True, timeout=120)


if __name__ == "__main__":
    main()
