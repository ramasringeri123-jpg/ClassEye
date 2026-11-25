"""Build the Windows app, the installer and a portable zip.

    python tools/build.py              ->  dist/ClassEye/ClassEye.exe
    python tools/build.py --installer  ->  also dist/ClassEye-Setup-<version>.exe (needs Inno Setup 6)
                                            and   dist/ClassEye-Portable-<version>.zip

Run it from the app's environment (venv) with the models already in models/
(setup.bat or tools/get_models.py). Student data and reports are never packaged.
The GitHub "Release" workflow runs exactly this script.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from classeye import __version__  # noqa: E402
from classeye.settings import MODEL_FILES  # noqa: E402

DIST = os.path.join(ROOT, "dist")
APP = os.path.join(DIST, "ClassEye")

EXCLUDE = ["torch", "ultralytics", "matplotlib", "pandas", "scipy", "tkinter", "onnxruntime.quantization",
           "onnxruntime.transformers", "onnxruntime.tools"]

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=({v}, 0), prodvers=({v}, 0), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
          StringStruct('CompanyName', 'ClassEye contributors'),
          StringStruct('FileDescription', 'ClassEye - Smart Attendance & Exam Monitoring'),
          StringStruct('FileVersion', '{s}'),
          StringStruct('InternalName', 'ClassEye'),
          StringStruct('LegalCopyright', 'MIT License'),
          StringStruct('OriginalFilename', 'ClassEye.exe'),
          StringStruct('ProductName', 'ClassEye'),
          StringStruct('ProductVersion', '{s}')])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)"""


def run(cmd):
    print(">", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def check_models():
    missing = [f for f in MODEL_FILES.values() if not os.path.exists(os.path.join(ROOT, "models", f))]
    if missing:
        raise SystemExit("Models missing (run setup.bat or tools/get_models.py first): " + ", ".join(missing))


def build_exe():
    parts = (__version__.split(".") + ["0", "0", "0"])[:3]
    vfile = os.path.join(ROOT, "build", "version_info.txt")
    os.makedirs(os.path.dirname(vfile), exist_ok=True)
    with open(vfile, "w", encoding="utf-8") as f:
        f.write(VERSION_INFO.format(v=", ".join(parts), s=__version__))
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "ClassEye",
           "--icon", os.path.join("assets", "classeye.ico"),
           "--add-data", f"assets{os.pathsep}assets",
           "--collect-binaries", "onnxruntime", "--hidden-import", "pygrabber.dshow_graph"]
    if sys.platform == "win32":
        cmd += ["--version-file", vfile]
    for m in EXCLUDE:
        cmd += ["--exclude-module", m]
    run(cmd + ["app.py"])
    dst = os.path.join(APP, "models")
    os.makedirs(dst, exist_ok=True)
    for f in MODEL_FILES.values():
        shutil.copy2(os.path.join(ROOT, "models", f), dst)
    for f in ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.md"):
        shutil.copy2(os.path.join(ROOT, f), APP)
    print("Built", os.path.join(APP, "ClassEye.exe"))


def find_iscc():
    for p in [shutil.which("iscc"), r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
              r"C:\Program Files\Inno Setup 6\ISCC.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe")]:
        if p and os.path.exists(p):
            return p
    return None


def build_installer():
    iscc = find_iscc()
    if iscc is None:
        raise SystemExit("Inno Setup 6 not found. Install it from https://jrsoftware.org/isdl.php "
                         "(or: winget install JRSoftware.InnoSetup) and run again.")
    run([iscc, f"/DAppVersion={__version__}", os.path.join("installer", "ClassEye.iss")])


def build_portable():
    tmp = os.path.join(DIST, "portable", "ClassEye")
    shutil.rmtree(os.path.join(DIST, "portable"), ignore_errors=True)
    shutil.copytree(APP, tmp)
    with open(os.path.join(tmp, "portable.txt"), "w", encoding="utf-8") as f:
        f.write("This file makes ClassEye keep its data and reports in this folder.\n")
    out = shutil.make_archive(os.path.join(DIST, f"ClassEye-Portable-{__version__}"), "zip",
                              os.path.join(DIST, "portable"), "ClassEye")
    shutil.rmtree(os.path.join(DIST, "portable"), ignore_errors=True)
    print("Built", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--installer", action="store_true", help="also make the Setup.exe and portable zip")
    a = ap.parse_args()
    check_models()
    build_exe()
    if a.installer:
        build_installer()
        build_portable()
    print("\nFiles in dist/:")
    for f in sorted(glob.glob(os.path.join(DIST, "*"))):
        print("  ", os.path.basename(f))


if __name__ == "__main__":
    main()
