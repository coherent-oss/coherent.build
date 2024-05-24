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
    'keyring',
    'google.generativeai',
]


from .backend import build_wheel, build_sdist


__all__ = ['build_wheel', 'build_sdist']
