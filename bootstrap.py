import contextlib
import pathlib
from typing import Callable

from .compat.py311 import importlib


def write_pyproject(
    target: pathlib.Path = pathlib.Path(),
) -> contextlib.AbstractContextManager[None]:
    return assured(
        target / 'pyproject.toml',
        importlib.resources.files().joinpath('system.toml').read_text,
    )


@contextlib.contextmanager
def assured(
    target: pathlib.Path, content_factory: Callable[[], str]
) -> contextlib.AbstractContextManager[None]:
    """
    Yield with target existing on the file system.

    If target does not already exist, it is created with the contents
    as supplied by ``content_factory()`` and deleted on exit.
    """
    if target.exists():
        yield
        return
    target.write_text(content_factory())
    try:
        yield
    finally:
        target.unlink()
