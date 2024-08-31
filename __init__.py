__requires__ = [
    'build',
    'git-fame',
    'importlib_resources; python_version < "3.12"',
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
