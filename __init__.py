__requires__ = [
    'wheel',
    'pip-run',
    'setuptools_scm',
    'build',
    'git-fame',
    'jaraco.context',
    'requests',
    'packaging',
    'jaraco.functools',
    'jaraco.compat >= 4.1',
    'importlib_resources; python_version < "3.12"',
    'jaraco.vcs',
]


from .backend import (
    build_editable,
    build_sdist,
    build_wheel,
    prepare_metadata,
)

prepare_metadata_for_build_wheel = prepare_metadata_for_build_editable = (
    prepare_metadata
)


__all__ = [
    'build_sdist',
    'prepare_metadata_for_build_wheel',
    'prepare_metadata_for_build_editable',
    'build_wheel',
    'build_editable',
]
