__requires__ = [
    "wheel",
    "pip-run",
    "jaraco.vcs",
    "build",
]

import importlib.metadata
import io
import os
import pathlib
import posixpath
import re
import tarfile
import time
import types

from jaraco import vcs
from wheel.wheelfile import WheelFile
from pip_run import scripts


def name_from_sdist():
    return importlib.metadata.PathDistribution(pathlib.Path()).metadata.get("Name")


def name_from_path():
    return pathlib.Path(".").absolute().name


def version_from_vcs():
    return vcs.repo().get_current_version()


def version_from_sdist():
    return importlib.metadata.PathDistribution(pathlib.Path()).metadata.get("Version")


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
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
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


def make_sdist_metadata(name, version) -> tarfile.TarInfo:
    info = tarfile.TarInfo(f"{normalize(name)}-{version}/PKG-INFO")
    metadata = f"Metadata-Version: 1.2\nName: {name}\nVersion: {version}\n"
    file = io.BytesIO(metadata.encode("utf-8"))
    info.size = len(file.getbuffer())
    info.mtime = time.time()
    return info, file


def build_sdist(sdist_directory, config_settings=None):
    name = name_from_path()
    version = version_from_vcs()
    filename = pathlib.Path(sdist_directory) / f"{normalize(name)}-{version}.tar.gz"
    with tarfile.open(filename, "w:gz") as tf:
        tf.add(pathlib.Path(), filter=SDist(f"{normalize(name)}-{version}"))
        tf.addfile(*make_sdist_metadata(name, version))
    return str(filename)
