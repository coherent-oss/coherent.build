from __future__ import annotations

import ast
import pathlib
import sys


def get_module_imports(module_path: pathlib.Path) -> set[str]:
    """
    Parse a Python module to extract imported names.

    Excludes relative imports.
    """
    return set(
        '.'.join(filter(bool, [getattr(node, 'module', None), alias.name]))
        for node in ast.walk(ast.parse(module_path.read_text()))
        if isinstance(node, ast.Import)
        or isinstance(node, ast.ImportFrom)
        and not node.level
        for alias in node.names
    )


__name__ == '__main__' and print(list(get_module_imports(pathlib.Path(sys.argv[1]))))
