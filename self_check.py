"""
Proves a packaged copy of the app works on the computer it was built on.

    "Speedy Scandocs" --self-check=report.txt

The release build runs this on Windows and on a Mac, because the tests in test/ hold client data and
stay off GitHub. It opens the real window on a temporary scans folder, renders a PDF made on the
spot, and checks that the libraries most easily left out of a package are really there. It writes
what it found to the report and exits 1 if anything failed.

It uses no AI, no key and no network, and it never reads or changes real settings, scans or keys.
"""

import sys
import tempfile
import traceback
from pathlib import Path
from unittest import mock

from PySide6.QtWidgets import QApplication

import engine

SCAN_NAME = "scan_0001.pdf"


def make_pdf(path):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument.new()
    pdf.new_page(612, 792)
    pdf.save(str(path))
    pdf.close()


def check_pdf(root):
    """PDFium and Pillow, turning a page into the JPEG that would go to Claude."""
    path = Path(root) / "check.pdf"
    make_pdf(path)
    images, pages = engine.render_jpegs(path, 0, 1)
    if pages != 1 or not images or not images[0].startswith(b"\xff\xd8"):
        raise RuntimeError(f"expected one JPEG page, got {len(images)} of {pages}")
    return f"{len(images[0])} byte JPEG"


def check_bedrock(root):
    """boto3 reads its service descriptions from data files, which packaging can leave behind."""
    client = engine.make_client("us-west-2", "self-check")
    if not hasattr(client, "converse"):
        raise RuntimeError("the Bedrock client has no converse call")
    return client.meta.service_model.service_name


def check_keyring(root):
    """Finds where keys are stored without touching any key."""
    import keyring
    wanted = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform)
    found = keyring.get_keyring()
    backends = getattr(found, "backends", None) or [found]
    names = [f"{type(b).__module__}.{type(b).__name__}" for b in backends]
    if wanted and not any(type(b).__module__.endswith(f".{wanted}") for b in backends):
        raise RuntimeError(f"no {wanted} key store, only {names}")
    return ", ".join(names)


def check_window(root, main_window):
    """The real window on a temporary scans folder, finding one scan."""
    folder = Path(root) / "scans"
    ws = engine.Workspace(folder)
    ws.create()
    make_pdf(ws.root / SCAN_NAME)
    settings = dict(engine.DEFAULT_SETTINGS, scan_folder=str(ws.root), guide_seen=True)
    with (mock.patch.object(engine, "load_settings", lambda path=None: settings),
          mock.patch.object(engine, "load_api_key", lambda: ""),
          mock.patch.object(engine, "save_settings", lambda s, path=None: None)):
        window = main_window()
        try:
            window.show()
            QApplication.processEvents()
            window.check_folder()
            QApplication.processEvents()
            count = window.list.count()
            if count != 1:
                raise RuntimeError(f"expected to find 1 scan, found {count}")
            if not window.windowIcon().availableSizes():
                raise RuntimeError("the logo file is missing from the package")
        finally:
            window.close()
    return "opened, logo loaded, found 1 scan"


def run(main_window, report_path):
    """Run every check, even after one fails. Returns the exit code."""
    lines = [f"Speedy Scandocs {engine.VERSION} on {sys.platform}, Python {sys.version.split()[0]}"]
    checks = (("PDF pages", check_pdf), ("Bedrock client", check_bedrock), ("Key store", check_keyring),
              ("Window", lambda root: check_window(root, main_window)))
    failed = False
    with tempfile.TemporaryDirectory() as root:
        for name, check in checks:
            try:
                lines.append(f"ok      {name}: {check(root)}")
            except Exception:
                failed = True
                lines.append(f"FAILED  {name}")
                lines.append(traceback.format_exc().rstrip())
    lines.append("FAILED" if failed else "PASSED")
    Path(report_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if failed else 0
