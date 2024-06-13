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
    'python-dateutil',
]


from .backend import (
    build_sdist,
    prepare_metadata,
    build_wheel,
    build_editable,
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
