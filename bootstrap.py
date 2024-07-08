import contextlib
import pathlib

from .compat.py311 import importlib


@contextlib.contextmanager
def write_pyproject(target: pathlib.Path = pathlib.Path()):
    path = target / 'pyproject.toml'
    if path.exists():
        yield
        return
    path.write_text(importlib.resources.files().joinpath('system.toml').read_text())
    try:
        yield
    finally:
        path.unlink()
