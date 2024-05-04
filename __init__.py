__requires__ = [
    "wheel",
    "pip-run",
    "setuptools_scm",
    "build",
    "git-fame",
    "jaraco.context",
]

import importlib.metadata
import io
import json
import os
import pathlib
import posixpath
import re
import subprocess
import tarfile
import time
import types

import setuptools_scm
from wheel.wheelfile import WheelFile
from pip_run import scripts
from jaraco.context import suppress


def name_from_sdist():
    return importlib.metadata.PathDistribution(pathlib.Path()).metadata.get("Name")


def name_from_path():
    return pathlib.Path(".").absolute().name


def version_from_vcs():
    return setuptools_scm.get_version()


def version_from_sdist():
    return importlib.metadata.PathDistribution(pathlib.Path()).metadata.get("Version")


def author_from_sdist():
    return importlib.metadata.PathDistribution(pathlib.Path()).metadata.get("Author")


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
    ignored = [r"\.git", "dist", r".*\b__pycache__$"]


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
    name = name_from_sdist() or name_from_path()
    root = name.replace(".", "/")
    version = version_from_sdist() or version_from_vcs()
    filename = (
        pathlib.Path(wheel_directory) / f"{normalize(name)}-{version}-py3-none-any.whl"
    )
    with WheelFile(filename, "w") as zf:
        for info in wheel_walk(Wheel(root)):
            zf.write(info.path, arcname=info.name)
        for md_name, contents in make_wheel_metadata(name, version):
            zf.writestr(md_name, contents)
    return str(filename)


def read_deps():
    """
    Read deps from ``__init__.py``.
    """
    return scripts.DepsReader.search(["__init__.py"])


def make_wheel_metadata(name, version):
    metadata = {
        "Metadata-Version": "2.1",
        "Name": name,
        "Version": version,
        "Author-Email": author_from_sdist(),
    }
    metadata = render(metadata)
    for dep in read_deps():
        metadata += f"Requires-Dist: {dep}\n"
    dist_info = f"{normalize(name)}-{version}.dist-info"
    yield f"{dist_info}/METADATA", metadata
    wheel_md = "Wheel-Version: 1.0\nGenerator: coherent.build\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    yield f"{dist_info}/WHEEL", wheel_md


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


def render(metadata):
    return (
        "\n".join(
            f"{key}: {value}" for key, value in metadata.items() if value is not None
        )
        + "\n"
    )


class Metadata(dict):
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


def make_sdist_metadata(metadata) -> tarfile.TarInfo:
    info = tarfile.TarInfo(f"{metadata.id}/PKG-INFO")
    file = io.BytesIO(render(metadata).encode("utf-8"))
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
