import importlib.resources
import pathlib
import runpy


def write_pyproject():
    path = pathlib.Path("pyproject.toml")
    if path.exists():
        return
    path.write_text(importlib.resources.files().joinpath("pyproject.toml").read_text())


def run():
    write_pyproject()
    runpy.run_module("build")


__name__ == "__main__" and run()
