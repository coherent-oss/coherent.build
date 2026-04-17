import pathlib

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


def test_declared_license_missing(tmp_path, monkeypatch):
    """
    declared_license returns None when __init__.py has no __license__.
    """
    init = tmp_path / '__init__.py'
    init.write_text('__requires__ = ["requests"]\n')
    monkeypatch.chdir(tmp_path)
    assert coherent.build.discovery.declared_license() is None


def test_declared_license_present(tmp_path, monkeypatch):
    """
    declared_license returns the SPDX expression from __init__.py.
    """
    init = tmp_path / '__init__.py'
    init.write_text('__license__ = "MIT"\n')
    monkeypatch.chdir(tmp_path)
    assert coherent.build.discovery.declared_license() == 'MIT'
