from __future__ import annotations

import ast
import functools
import pathlib
import sys

from typing import Generator


def rel_prefix(node):
    return '.' * getattr(node, 'level', 0)


@functools.singledispatch
def get_module_imports(module: pathlib.Path | str) -> Generator[str]:
    r"""
    Parse a Python module to extract imported names.

    >>> list(get_module_imports('import ast\nimport requests'))
    ['ast', 'requests']

    >>> list(get_module_imports('from foo import bar'))
    ['foo.bar']

    Handles relative imports.

    >>> list(get_module_imports('from .. import foo'))
    ['..foo']

    >>> list(get_module_imports('from .foo import bar'))
    ['.foo.bar']

    """
    return (
        rel_prefix(node)
        + '.'.join(
            filter(
                bool,
                [
                    getattr(node, 'module', None),
                    alias.name,
                ],
            ),
        )
        for node in ast.walk(ast.parse(module))
        if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom)
        for alias in node.names
    )


@get_module_imports.register
def _(module: pathlib.Path):
    return get_module_imports(module.read_text())


__name__ == '__main__' and print(list(get_module_imports(pathlib.Path(sys.argv[1]))))
