import contextlib
import importlib.resources
import pathlib


@contextlib.contextmanager
def write_pyproject():
    path = pathlib.Path('pyproject.toml')
    if path.exists():
        yield
        return
    path.write_text(importlib.resources.files().joinpath('system.toml').read_text())
    try:
        yield
    finally:
        path.unlink()
