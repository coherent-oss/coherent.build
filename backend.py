from __future__ import annotations

import io
import os
import pathlib
import posixpath
import re
import tarfile
import textwrap
import time
import types
from typing import (
    Iterator,
)

from jaraco.compat.py38 import r_fix
from jaraco.functools import pass_none
from wheel.wheelfile import WheelFile

from .metadata import Message


class Filter:
    """
    Filters tar- and zip-info objects for inclusion in different distributions.
    """

    def __init__(self, name: str):
        """
        Initialize the filter with the root of the package ("coherent/build").
        """
        self.name = name

    def __call__(self, info):
        """
        Determine disposition for the info object.

        Given an object like a tarfile.TarInfo object, determine if it
        should be included or filtered. Return None if the object should
        be omitted. Otherwise, mutate the object to include self.name
        as a prefix.
        """
        if info.name == '.':
            info.name = self.name
            return info
        ignore_pattern = '|'.join(self.ignored)
        if re.match(ignore_pattern, r_fix(info.name).removeprefix('./')):
            return
        info.name = self.name + '/' + r_fix(info.name).removeprefix('./')
        return info


class SDist(Filter):
    """
    >>> sf = SDist(name="foo")

    Ignores the .git directory
    >>> sf(types.SimpleNamespace(name='./.git'))

    Ignores __pycache__ directories
    >>> sf(types.SimpleNamespace(name='./bar/__pycache__'))

    Ignore paths starting with a dot
    >>> sf(types.SimpleNamespace(name='./bar/.DS_Store'))

    Should not ignore nested dist dirs
    >>> sf(types.SimpleNamespace(name='./bar/dist'))
    namespace(name='foo/bar/dist')
    """

    ignored = ['dist', r'(.*[/])?__pycache__$', r'(.*[/])?[.]']


class Wheel(Filter):
    ignored = [
        'docs',
        'tests',
        r'README.*',
        'PKG-INFO',
        re.escape('(meta)'),
        re.escape('pyproject.toml'),
    ]


class ZipInfo(types.SimpleNamespace):
    """
    Simulate a compatible interface as a tarfile.TarInfo object.
    """

    def __init__(self, path):
        zip_name = path.replace(os.pathsep, posixpath.sep)
        super().__init__(path=path, name=zip_name)


def wheel_walk(filter_: Wheel) -> Iterator[ZipInfo]:
    """
    Walk the current directory, applying and honoring the filter for traversal.
    """
    for root, dirs, files in os.walk('.'):
        zi = ZipInfo(path=root)
        if not filter_(zi):
            dirs[:] = []
            continue

        children = (ZipInfo(path=os.path.join(root, file)) for file in files)
        yield from filter(bool, map(filter_, children))


def make_sdist_metadata(metadata: Message) -> tarfile.TarInfo:
    info = tarfile.TarInfo(f'{metadata.id}/PKG-INFO')
    file = io.BytesIO(metadata.render().encode('utf-8'))
    info.size = len(file.getbuffer())
    info.mtime = time.time()
    return info, file


def prepare_metadata(metadata_directory, config_settings=None):
    metadata = Message.load() or Message.discover()

    md_root = pathlib.Path(metadata_directory, f'{metadata.id}.dist-info')
    md_root.mkdir()
    for name, contents in metadata.render_wheel():
        md_root.joinpath(name).write_text(contents)
    return md_root.name


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    metadata = (
        pass_none(Message.load)(metadata_directory)
        or Message.load()
        or Message.discover()
    )
    root = metadata['Name'].replace('.', '/')
    filename = pathlib.Path(wheel_directory) / f'{metadata.id}-py3-none-any.whl'
    with WheelFile(filename, 'w') as zf:
        for info in wheel_walk(Wheel(root)):
            zf.write(info.path, arcname=info.name)
        for name, contents in metadata.render_wheel():
            zf.writestr(f'{metadata.id}.dist-info/{name}', contents)
    return str(filename)


def build_sdist(sdist_directory, config_settings=None):
    metadata = Message.discover()
    filename = pathlib.Path(sdist_directory) / f'{metadata.id}.tar.gz'
    with tarfile.open(filename, 'w:gz') as tf:
        tf.add(pathlib.Path(), filter=SDist(metadata.id))
        tf.addfile(*make_sdist_metadata(metadata))
    return str(filename)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    metadata = (
        pass_none(Message.load)(metadata_directory)
        or Message.load()
        or Message.discover()
    )
    root = metadata['Name'].replace('.', '/')
    filename = pathlib.Path(wheel_directory) / f'{metadata.id}-py3-none-any.whl'
    with WheelFile(filename, 'w') as zf:
        zf.writestr(f'{root}/__init__.py', proxy())
        for name, contents in metadata.render_wheel():
            zf.writestr(f'{metadata.id}.dist-info/{name}', contents)
    return str(filename)


def proxy():
    return textwrap.dedent(f"""
        import io
        __path__ = [{os.getcwd()!r}]
        __file__ = __path__[0] + '/__init__.py'
        try:
            strm = io.open_code(__file__)
        except FileNotFoundError:
            pass
        else:
            with strm:
                exec(compile(strm.read(), __file__, 'exec'))
        """).lstrip()
