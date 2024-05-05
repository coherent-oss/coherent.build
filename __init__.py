__requires__ = [
    "wheel",
    "pip-run",
    "setuptools_scm",
    "build",
    "git-fame",
    "jaraco.context",
    "requests",
]

import functools
import importlib.metadata
import io
import json
import mimetypes
import os
import pathlib
import posixpath
import re
import subprocess
import tarfile
import time
import types

from collections.abc import Mapping
from email.message import Message
from typing import Iterable

import requests
import setuptools_scm
from wheel.wheelfile import WheelFile
from pip_run import scripts
from jaraco.context import suppress


mimetypes.add_type("text/plain", "", strict=True)
mimetypes.add_type("text/markdown", ".md", strict=True)
mimetypes.add_type("text/x-rst", ".rst", strict=True)


def name_from_path():
    return pathlib.Path(".").absolute().name


def version_from_vcs():
    return setuptools_scm.get_version()


@suppress(Exception)
def summary_from_github():
    return (
        json.loads(
            subprocess.check_output(
                ["gh", "repo", "view", "--json", "description"],
                text=True,
                encoding="utf-8",
            )
        )["description"]
        or None
    )


def python_requires_supported():
    owner = "python"
    repo = "cpython"
    url = f"https://api.github.com/repos/{owner}/{repo}/branches"
    branches = requests.get(url).json()
    # cheat and grab the first branch, which is the oldest supported Python version
    return f'>= {branches[0]["name"]}'


class Filter:
    def __init__(self, name: str):
        self.name = name

    def __call__(self, info):
        if info.name == ".":
            info.name = self.name
            return info
        ignore_pattern = "|".join(self.ignored)
        if re.match(ignore_pattern, info.name.removeprefix("./")):
            return
        info.name = self.name + "/" + info.name.removeprefix("./")
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

    ignored = ["dist", r"(.*[/])?__pycache__$", r"(.*[/])?[.]"]


class Wheel(Filter):
    ignored = ["docs", "tests", "README.*", "PKG-INFO", "(meta)"]


class ZipInfo(types.SimpleNamespace):
    def __init__(self, path):
        zip_name = path.replace(os.pathsep, posixpath.sep)
        super().__init__(path=path, name=zip_name)


def normalize(name):
    # todo: do proper normalization
    return name.replace(".", "_")


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    metadata = Metadata.from_sdist() or Metadata.discover()
    root = metadata["Name"].replace(".", "/")
    filename = pathlib.Path(wheel_directory) / f"{metadata.id}-py3-none-any.whl"
    with WheelFile(filename, "w") as zf:
        for info in wheel_walk(Wheel(root)):
            zf.write(info.path, arcname=info.name)
        for md_name, contents in make_wheel_metadata(metadata):
            zf.writestr(md_name, contents)
    return str(filename)


def read_deps():
    """
    Read deps from ``__init__.py``.
    """
    return scripts.DepsReader.search(["__init__.py"])


def make_wheel_metadata(metadata):
    dist_info = f"{metadata.id}.dist-info"
    yield f"{dist_info}/METADATA", metadata.render()
    wheel_md = Metadata(
        {
            "Wheel-Version": "1.0",
            "Generator": "coherent.build",
            "Root-Is-Purelib": "true",
            "Tag": "py3-none-any",
        }
    )
    yield f"{dist_info}/WHEEL", wheel_md.render()


def wheel_walk(filter_: Wheel):
    for root, dirs, files in os.walk("."):
        zi = ZipInfo(path=root)
        if not filter_(zi):
            dirs[:] = []
            continue

        children = (ZipInfo(path=os.path.join(root, file)) for file in files)
        yield from filter(None, map(filter_, children))


def _to_mapping(fame):
    return (dict(zip(fame["columns"], row)) for row in fame["data"])


class Contributor(types.SimpleNamespace):
    @property
    def combined_detail(self):
        return f'"{self.name}" <{self.email}>'


@suppress(Exception)
def author_from_vcs():
    # run git-fame twice to get both name and email
    cmd = ["git-fame", "--format", "json"]
    names_data = json.loads(subprocess.check_output(cmd, text=True, encoding="utf-8"))
    emails_data = json.loads(
        subprocess.check_output(
            cmd + ["--show-email"],
            text=True,
            encoding="utf-8",
        )
    )
    names_data["columns"][0] = "name"
    emails_data["columns"][0] = "email"
    emails_contribs = _to_mapping(emails_data)
    names_contribs = _to_mapping(names_data)

    contribs = (
        Contributor(**val)
        for val in (
            {**name_contrib, **email_contrib}
            for name_contrib, email_contrib in zip(names_contribs, emails_contribs)
        )
    )
    return next(contribs).combined_detail


@functools.singledispatch
def always_items(
    values: Mapping | Message | Iterable[tuple[str, str]],
) -> Iterable[tuple[str, str]]:
    return values


@always_items.register
def _(values: Mapping) -> Iterable[tuple[str, str]]:
    return values.items()


@always_items.register
def _(values: Message) -> Iterable[tuple[str, str]]:
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
        if "Description" in self:
            self.set_payload(self["Description"])
            del self["Description"]

    @property
    def id(self):
        return f"{normalize(self['Name'])}-{self['Version']}"

    @classmethod
    def discover(cls):
        return cls(cls._discover_fields())

    @staticmethod
    def _discover_fields():
        yield "Metadata-Version", "2.3"
        yield "Name", name_from_path()
        yield "Version", version_from_vcs()
        yield "Author-Email", author_from_vcs()
        yield "Summary", summary_from_github()
        yield "Requires-Python", python_requires_supported()
        for dep in read_deps():
            yield "Requires-Dist", dep
        yield from description_from_readme()

    @classmethod
    def from_sdist(cls):
        sdist_metadata = importlib.metadata.PathDistribution(pathlib.Path()).metadata
        return (sdist_metadata or None) and cls(sdist_metadata)

    def render(self):
        self._description_in_payload()
        return str(self)


def guess_content_type(path: pathlib.Path):
    """
    >>> guess_content_type('foo.md')
    'text/markdown'
    >>> guess_content_type('foo.rst')
    'text/x-rst'
    >>> guess_content_type('foo')
    'text/plain'
    """
    type, _ = mimetypes.guess_type(str(path))
    return type


@suppress(Exception)
def description_from_readme():
    (readme,) = pathlib.Path().glob("README*")
    ct = guess_content_type(readme)
    assert ct
    yield "Description-Content-Type", ct
    yield "Description", readme.read_text(encoding="utf-8")


def make_sdist_metadata(metadata) -> tarfile.TarInfo:
    info = tarfile.TarInfo(f"{metadata.id}/PKG-INFO")
    file = io.BytesIO(metadata.render().encode("utf-8"))
    info.size = len(file.getbuffer())
    info.mtime = time.time()
    return info, file


def build_sdist(sdist_directory, config_settings=None):
    metadata = Metadata.discover()
    filename = pathlib.Path(sdist_directory) / f"{metadata.id}.tar.gz"
    with tarfile.open(filename, "w:gz") as tf:
        tf.add(pathlib.Path(), filter=SDist(metadata.id))
        tf.addfile(*make_sdist_metadata(metadata))
    return str(filename)
