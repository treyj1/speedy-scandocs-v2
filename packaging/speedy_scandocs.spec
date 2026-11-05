# Builds the app with PyInstaller, for whichever system this runs on. From the top folder:
#
#     python -m PyInstaller packaging/speedy_scandocs.spec --noconfirm
#
# Windows: dist/Speedy Scandocs/  Mac: dist/Speedy Scandocs.app
# PyInstaller can't build for another system, so the Mac copy has to be built on a Mac. That's what
# .github/workflows/release.yml is for. See "Releases on GitHub" in README.md.

import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
NAME = "Speedy Scandocs"
VERSION = re.search(r'^VERSION = "(.+)"', (ROOT / "engine.py").read_text(encoding="utf-8"), re.M).group(1)

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    # keyring finds Windows Credential Manager or the Mac Keychain by name at run time, through its
    # package metadata, so PyInstaller can't see either one on its own.
    hiddenimports=collect_submodules("keyring.backends"),
    datas=copy_metadata("keyring"),
    excludes=["tkinter", "unittest.test"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,
    icon=str(ROOT / "packaging" / ("icon.icns" if sys.platform == "darwin" else "icon.ico")),
)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{NAME}.app",
        icon=str(ROOT / "packaging" / "icon.icns"),
        bundle_identifier="com.speedyscandocs.app",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": NAME,
            "NSHighResolutionCapable": True,
            # macOS shows these when asking to reach a scans folder in one of these places.
            "NSDesktopFolderUsageDescription": "Speedy Scandocs reads and names the scans in your scans folder.",
            "NSDocumentsFolderUsageDescription": "Speedy Scandocs reads and names the scans in your scans folder.",
            "NSDownloadsFolderUsageDescription": "Speedy Scandocs reads and names the scans in your scans folder.",
            "NSNetworkVolumesUsageDescription": "Speedy Scandocs reads and names the scans in your scans folder.",
            "NSRemovableVolumesUsageDescription": "Speedy Scandocs reads and names the scans in your scans folder.",
        },
    )
