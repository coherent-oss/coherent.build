import contextlib
import pathlib
import sys

if sys.version_info < (3, 12):
    import importlib_resources
else:
    import importlib.resources as importlib_resources


@contextlib.contextmanager
def write_pyproject(target: pathlib.Path = pathlib.Path()):
    path = target / 'pyproject.toml'
    if path.exists():
        yield
        return
    path.write_text(importlib_resources.files().joinpath('system.toml').read_text())
    try:
        yield
    finally:
        path.unlink()
