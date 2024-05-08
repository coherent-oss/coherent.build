import contextlib
import importlib.resources
import pathlib
import runpy


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


def run():
    with write_pyproject():
        runpy.run_module('build', run_name='__main__')


__name__ == '__main__' and run()
