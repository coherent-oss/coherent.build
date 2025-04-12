from __future__ import annotations

import itertools
import os
import pathlib
import posixpath
import tarfile
import textwrap
import types
from collections.abc import Iterator

from jaraco.functools import pass_none
from more_itertools import consume
from wheel.wheelfile import WheelFile

from . import flit, layouts
from .metadata import Message


class ZipInfo(types.SimpleNamespace):
    """
    Simulate a compatible interface as a tarfile.TarInfo object.
    """

    def __init__(self, path):
        zip_name = path.replace(os.pathsep, posixpath.sep)
        super().__init__(path=path, name=zip_name)


def wheel_walk(filter_: layouts.Wheel) -> Iterator[ZipInfo]:
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
    filename = pathlib.Path(wheel_directory) / f'{metadata.id}-py3-none-any.whl'
    with WheelFile(filename, 'w') as zf:
        for info in wheel_walk(layouts.Wheel(metadata)):
            zf.write(info.path, arcname=info.name)
        for name, contents in metadata.render_wheel():
            zf.writestr(f'{metadata.id}.dist-info/{name}', contents)
    return filename.name


sdist_backends = dict(
    flit=flit.SDist,
    coherent=layouts.SDist,
)


def build_sdist(sdist_directory, config_settings=None):
    metadata = Message.discover()
    filename = pathlib.Path(sdist_directory) / f'{metadata.id}.tar.gz'
    layout = sdist_backends[os.environ.get('SDIST_BACKEND', 'coherent')](metadata)
    with tarfile.open(filename, 'w:gz') as tf:
        tf.add(pathlib.Path(), filter=layout)
        consume(itertools.starmap(tf.addfile, layout.add_files()))
    return filename.name


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
