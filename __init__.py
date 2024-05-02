import importlib.metadata
import io
import os
import pathlib
import posixpath
import re
import tarfile
import time
import types
import zipfile


def name_from_sdist():
    return importlib.metadata.PathDistribution(pathlib.Path()).metadata.get("Name")


def name_from_path():
    return pathlib.Path(".").absolute().name


def read_version():
    # stubbed
    return "1.0.0"


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
    ignored = [r"\.git", "dist"]


class Wheel(Filter):
    ignored = ["docs", "tests", "README.*", "PKG-INFO", "(meta)"]


class ZipInfo(types.SimpleNamespace):
    def __init__(self, path):
        zip_name = path.replace(os.pathsep, posixpath.sep)
        super().__init__(path=path, name=zip_name)


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    name = name_from_sdist() or name_from_path()
    version = read_version()
    filename = pathlib.Path(wheel_directory) / f"{name}-{version}.zip"
    with zipfile.ZipFile(filename, "w") as zf:
        for info in wheel_walk(Wheel(name)):
            zf.write(info.path, arcname=info.name)
        zf.writestr(*make_wheel_metadata(name, version))
    return str(filename)


def make_wheel_metadata(name, version):
    metadata = f"Name: {name}\nVersion: {version}\n"
    return f"{name}-{version}.dist-info/METADATA", metadata


def wheel_walk(filter_: Wheel):
    for root, dirs, files in os.walk("."):
        zi = ZipInfo(path=root)
        filtered = filter_(zi)
        if not filtered:
            dirs[:] = []
            continue

        yield filtered
        children = (ZipInfo(path=os.path.join(root, file)) for file in files)
        yield from filter(None, map(filter_, children))


def make_sdist_metadata(name, version) -> tarfile.TarInfo:
    info = tarfile.TarInfo(f"{name}-{version}/PKG-INFO")
    metadata = f"Name: {name}\nVersion: {version}\n"
    file = io.BytesIO(metadata.encode("utf-8"))
    info.size = len(file.getbuffer())
    info.mtime = time.time()
    return info, file


def build_sdist(sdist_directory, config_settings=None):
    name = name_from_path()
    version = read_version()
    filename = pathlib.Path(sdist_directory) / f"{name}-{version}.tar.gz"
    with tarfile.open(filename, "w:gz") as tf:
        tf.add(pathlib.Path(), filter=SDist(f"{name}-{version}"))
        tf.addfile(*make_sdist_metadata(name, version))
    return str(filename)
