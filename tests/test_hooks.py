import pathlib
import re
import tarfile
import zipfile

import coherent.build.backend
import coherent.build.discovery


def test_prepared_metadata(tmp_path, monkeypatch):
    """
    Ensure that prepared metadata can be used to build a wheel.
    """
    md_root = tmp_path / 'metadata-build'
    md_root.mkdir()
    md_name = coherent.build.prepare_metadata_for_build_wheel(md_root)
    md_dir = md_root / md_name
    wheel_root = tmp_path / 'wheel-build'
    wheel_root.mkdir()
    # ensure Message.discover is not called
    monkeypatch.delattr(coherent.build.metadata.Message, 'discover')
    coherent.build.build_wheel(wheel_root, metadata_directory=md_dir)


def is_redirect_file(name):
    return name.endswith('-redirects.pth')


def test_editable_pth_redirect(tmp_path):
    """
    Ensure that editable wheels include a .pth file with an import redirect
    comment mapping the package name to the source directory.
    """
    wheel_name = coherent.build.build_editable(tmp_path)
    with zipfile.ZipFile(tmp_path / wheel_name) as zf:
        (pth_file,) = filter(is_redirect_file, zf.namelist())
        pth_contents = zf.read(pth_file).decode()
    match = re.fullmatch(
        r'# import redirect (?P<package>[\w.]+) -> (?P<path>.*)', pth_contents.strip()
    )
    assert match.group('package') == 'coherent.build'
    assert pathlib.Path(match.group('path')).is_dir()


def test_wheel_includes_py_typed(tmp_path):
    """
    Wheels carry a PEP 561 marker in the leaf package, and nowhere else.
    """
    wheel_name = coherent.build.build_wheel(tmp_path)
    with zipfile.ZipFile(tmp_path / wheel_name) as zf:
        names = zf.namelist()
    assert 'coherent/build/py.typed' in names
    assert 'coherent/py.typed' not in names


def test_py_typed_opt_out(tmp_path, monkeypatch):
    """
    A package declaring itself untyped gets no marker.
    """
    monkeypatch.setattr(coherent.build.discovery, 'is_typed', lambda: False)
    wheel_name = coherent.build.build_wheel(tmp_path)
    with zipfile.ZipFile(tmp_path / wheel_name) as zf:
        assert not any(name.endswith('py.typed') for name in zf.namelist())


def test_editable_omits_py_typed(tmp_path):
    """
    Editable wheels omit the marker; it would vouch for the proxy module,
    which exports nothing (coherent-oss/coherent.build#72).
    """
    wheel_name = coherent.build.build_editable(tmp_path)
    with zipfile.ZipFile(tmp_path / wheel_name) as zf:
        assert not any(name.endswith('py.typed') for name in zf.namelist())


def test_sdist_includes_py_typed(tmp_path):
    """
    The sdist carries the marker too. Its pyproject declares flit_core as
    the backend, so coherent.build never sees the wheel built from it
    downstream; the marker has to be in the source tree flit copies.
    """
    sdist_name = coherent.build.build_sdist(tmp_path)
    with tarfile.open(tmp_path / sdist_name) as tf:
        names = tf.getnames()
    root = sdist_name.removesuffix('.tar.gz')
    assert f'{root}/coherent/build/py.typed' in names
    assert f'{root}/coherent/py.typed' not in names
