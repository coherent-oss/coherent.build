from __future__ import annotations

import contextlib
import functools
import importlib.metadata
import io
import os
import pathlib
import posixpath
import re
import tarfile
import textwrap
import time
import types
from collections.abc import Mapping
from email.message import Message
from typing import (
    Iterable,
    Tuple,  # Python 3.8
)

import packaging
from jaraco.compat.py38 import r_fix
from jaraco.functools import pass_none
from wheel.wheelfile import WheelFile

from . import discovery


class Filter:
    def __init__(self, name: str):
        self.name = name

    def __call__(self, info):
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
    def __init__(self, path):
        zip_name = path.replace(os.pathsep, posixpath.sep)
        super().__init__(path=path, name=zip_name)


def _normalize(name):
    return packaging.utils.canonicalize_name(name).replace('-', '_')


def make_wheel_metadata(metadata):
    yield 'METADATA', metadata.render()
    wheel_md = Metadata({
        'Wheel-Version': '1.0',
        'Generator': 'coherent.build',
        'Root-Is-Purelib': 'true',
        'Tag': 'py3-none-any',
    })
    yield 'WHEEL', wheel_md.render()
    with contextlib.suppress(FileNotFoundError):
        yield (
            'entry_points.txt',
            pathlib.Path('(meta)/entry_points.txt').read_text(),
        )


def wheel_walk(filter_: Wheel):
    for root, dirs, files in os.walk('.'):
        zi = ZipInfo(path=root)
        if not filter_(zi):
            dirs[:] = []
            continue

        children = (ZipInfo(path=os.path.join(root, file)) for file in files)
        yield from filter(None, map(filter_, children))


@functools.singledispatch
def always_items(
    values: Mapping | Message | Iterable[Tuple[str, str]],
) -> Iterable[Tuple[str, str]]:
    return values


@always_items.register
def _(values: Mapping) -> Iterable[Tuple[str, str]]:
    return values.items()


@always_items.register
def _(values: Message) -> Iterable[Tuple[str, str]]:
    return values._headers


class Metadata(Message):
    """
    >>> md = Metadata.discover()
    >>> md['Summary']
    'A zero-config Python project build backend'
    """

    def __init__(self, values):
        super().__init__()
        for item in always_items(values):
            self.add_header(*item)

    def _description_in_payload(self):
        if 'Description' in self:
            self.set_payload(self['Description'])
            del self['Description']

    @property
    def id(self):
        """
        >>> Metadata(dict(Name='foo.bar', Version='1.0.0')).id
        'foo_bar-1.0.0'
        """
        return f"{_normalize(self['Name'])}-{self['Version']}"

    @classmethod
    def discover(cls):
        """
        >>> md = Metadata.discover()
        """
        return cls(cls._discover_fields())

    @staticmethod
    def _discover_fields():
        yield 'Metadata-Version', '2.3'
        yield 'Name', discovery.best_name()
        yield 'Version', discovery.version_from_vcs()
        yield 'Author-Email', discovery.author_from_vcs()
        yield 'Summary', discovery.summary_from_github()
        yield 'Requires-Python', discovery.python_requires_supported()
        deps = list(discovery.read_deps())
        for dep in deps:
            yield 'Requires-Dist', dep
        for extra in discovery.full_extras(discovery.extras_from_deps(deps)):
            yield 'Provides-Extra', extra
        yield 'Project-URL', f'Source, {discovery.source_url()}'
        yield from discovery.description_from_readme()
        for classifier in discovery.generate_classifiers():
            yield 'Classifier', classifier

    @classmethod
    def load(cls, info: str | pathlib.Path = pathlib.Path()):
        md = importlib.metadata.PathDistribution(pathlib.Path(info)).metadata
        return (md or None) and cls(md)

    def render(self):
        self._description_in_payload()
        return str(self)


def make_sdist_metadata(metadata) -> tarfile.TarInfo:
    info = tarfile.TarInfo(f'{metadata.id}/PKG-INFO')
    file = io.BytesIO(metadata.render().encode('utf-8'))
    info.size = len(file.getbuffer())
    info.mtime = time.time()
    return info, file


def prepare_metadata(metadata_directory, config_settings=None):
    metadata = Metadata.load() or Metadata.discover()

    md_root = pathlib.Path(metadata_directory, f'{metadata.id}.dist-info')
    md_root.mkdir()
    for name, contents in make_wheel_metadata(metadata):
        md_root.joinpath(name).write_text(contents)
    return md_root.name


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    metadata = (
        pass_none(Metadata.load)(metadata_directory)
        or Metadata.load()
        or Metadata.discover()
    )
    root = metadata['Name'].replace('.', '/')
    filename = pathlib.Path(wheel_directory) / f'{metadata.id}-py3-none-any.whl'
    with WheelFile(filename, 'w') as zf:
        for info in wheel_walk(Wheel(root)):
            zf.write(info.path, arcname=info.name)
        for name, contents in make_wheel_metadata(metadata):
            zf.writestr(f'{metadata.id}.dist-info/{name}', contents)
    return str(filename)


def build_sdist(sdist_directory, config_settings=None):
    metadata = Metadata.discover()
    filename = pathlib.Path(sdist_directory) / f'{metadata.id}.tar.gz'
    with tarfile.open(filename, 'w:gz') as tf:
        tf.add(pathlib.Path(), filter=SDist(metadata.id))
        tf.addfile(*make_sdist_metadata(metadata))
    return str(filename)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    metadata = (
        pass_none(Metadata.load)(metadata_directory)
        or Metadata.load()
        or Metadata.discover()
    )
    root = metadata['Name'].replace('.', '/')
    filename = pathlib.Path(wheel_directory) / f'{metadata.id}-py3-none-any.whl'
    with WheelFile(filename, 'w') as zf:
        zf.writestr(f'{root}/__init__.py', proxy())
        for name, contents in make_wheel_metadata(metadata):
            zf.writestr(f'{metadata.id}.dist-info/{name}', contents)
    return str(filename)


def proxy():
    return textwrap.dedent(f"""
        __path__ = [{os.getcwd()!r}]
        __file__ = __path__[0] + '/__init__.py'
        try:
            strm = open(__file__)
        except FileNotFoundError:
            pass
        else:
            with strm:
                exec(strm.read())
        """).lstrip()
