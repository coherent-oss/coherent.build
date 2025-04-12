import abc
import io
import pathlib
import re
import tarfile
import time

from .metadata import Message


class Layout(abc.ABC):
    """
    Lay out tar- and zip-info objects for inclusion in different distributions.
    """

    def __init__(self, metadata: Message):
        """
        Initialize the filter with the root of the package ("coherent/build").
        """
        self.metadata = metadata

    @abc.abstractmethod
    def prefix(self, name: str) -> str:
        """
        Given the name, give its location.
        """

    def __call__(self, info):
        """
        Determine disposition for the info object.

        Given an object like a tarfile.TarInfo object, determine if it
        should be included or filtered. Return None if the object should
        be omitted. Otherwise, relocate the object to self.prefix.
        """
        info.name = info.name.removeprefix('./')
        ignore_pattern = '|'.join(self.ignored)
        if info.name != '.' and re.match(ignore_pattern, info.name):
            return
        info.name = str(pathlib.PurePosixPath(self.prefix(info.name), info.name))
        return info


def make_tarinfo(filename, content):
    info = tarfile.TarInfo(filename)
    file = io.BytesIO(content.encode('utf-8'))
    info.size = len(file.getbuffer())
    info.mtime = time.time()
    return info, file


class SDist(Layout):
    """
    >>> import types
    >>> sf = SDist(metadata=types.SimpleNamespace(id="foo"))

    Ignores the .git directory
    >>> sf(types.SimpleNamespace(name='./.git'))

    Ignores __pycache__ directories
    >>> sf(types.SimpleNamespace(name='./bar/__pycache__'))

    Ignore paths starting with a dot
    >>> sf(types.SimpleNamespace(name='./bar/.DS_Store'))

    Ignore dist dirs
    >>> sf(types.SimpleNamespace(name='./dist'))

    Should not ignore nested dist dirs
    >>> sf(types.SimpleNamespace(name='./bar/dist'))
    namespace(name='foo/bar/dist')

    Should not ignore paths that begin with 'dist'
    >>> sf(types.SimpleNamespace(name='./distributions'))
    namespace(name='foo/distributions')
    """

    ignored = ['dist$', r'(.*[/])?__pycache__$', r'(.*[/])?[.]']

    def prefix(self, name):
        return self.metadata.id

    def add_files(self):
        yield make_tarinfo(f'{self.metadata.id}/PKG-INFO', self.metadata.render())


class Wheel(Layout):
    """
    >>> import types
    >>> wf = Wheel(metadata=dict(Name="foo"))

    Ignore all the things SDist does (coherent-oss/coherent.build#33)
    >>> wf(types.SimpleNamespace(name='./.git'))
    >>> wf(types.SimpleNamespace(name='./bar/__pycache__'))
    >>> wf(types.SimpleNamespace(name='./bar/.DS_Store'))
    >>> wf(types.SimpleNamespace(name='./dist'))
    >>> wf(types.SimpleNamespace(name='./bar/dist'))
    namespace(name='foo/bar/dist')
    >>> wf(types.SimpleNamespace(name='./distributions'))
    namespace(name='foo/distributions')

    Additionally, filters out non-project files:
    >>> wf(types.SimpleNamespace(name='./README.rst'))
    >>> wf(types.SimpleNamespace(name='./docs'))
    >>> wf(types.SimpleNamespace(name='./(meta)'))
    >>> wf(types.SimpleNamespace(name='./pyproject.toml'))
    """

    ignored = SDist.ignored + [
        'docs',
        'tests',
        r'README.*',
        'PKG-INFO',
        re.escape('(meta)'),
        re.escape('pyproject.toml'),
    ]

    def prefix(self, name):
        return self.metadata['Name'].replace('.', '/')
