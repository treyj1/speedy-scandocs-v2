"""Exits with an error if a library the app needs is missing or too old. Used by the .vbs launcher."""

import importlib.metadata as metadata

import keyring  # noqa: F401
import PIL  # noqa: F401
import pypdfium2  # noqa: F401
import PySide6  # noqa: F401

major_minor = tuple(int(x) for x in metadata.version("boto3").split(".")[:2])
raise SystemExit(0 if major_minor >= (1, 43) else 1)
