from __future__ import annotations

import ast
import functools
import pathlib
import sys

from typing import Generator


@functools.singledispatch
def get_module_imports(module: pathlib.Path | str) -> Generator[str]:
    """
    Parse a Python module to extract imported names.

    >>> 'ast' in set(get_module_imports(pathlib.Path(__file__)))
    True

    Excludes relative imports.

    >>> list(get_module_imports('from . import foo'))
    []
    """
    return (
        '.'.join(filter(bool, [getattr(node, 'module', None), alias.name]))
        for node in ast.walk(ast.parse(module))
        if isinstance(node, ast.Import)
        or isinstance(node, ast.ImportFrom)
        and not node.level
        for alias in node.names
    )


@get_module_imports.register
def _(module: pathlib.Path):
    return get_module_imports(module.read_text())


__name__ == '__main__' and print(list(get_module_imports(pathlib.Path(sys.argv[1]))))
