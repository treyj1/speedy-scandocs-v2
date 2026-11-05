"""Saves the folder drawn by app.py as packaging/icon.ico and icon.icns. Rerun only if the icon changes."""

import io
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
from PySide6.QtCore import QBuffer
from PySide6.QtWidgets import QApplication

import app as ui

qapp = QApplication([])
buffer = QBuffer()
buffer.open(QBuffer.WriteOnly)
ui.folder_pixmap(1024).save(buffer, "PNG")
image = Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")

here = Path(__file__).resolve().parent
image.save(here / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
image.save(here / "icon.icns")
