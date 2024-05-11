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
]


from .backend import build_wheel, build_sdist


__all__ = ['build_wheel', 'build_sdist']
