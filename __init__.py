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


from .backend import build_wheel, build_sdist, prepare_metadata_for_build_wheel


__all__ = ['build_wheel', 'build_sdist', 'prepare_metadata_for_build_wheel']
