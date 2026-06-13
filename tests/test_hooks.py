import os
import zipfile

import coherent.build.backend


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
    assert pth_contents.startswith('# import redirect ')
    pkg_name = pth_file.removesuffix('-redirects.pth')
    package_root = os.getcwd()
    assert pth_contents.strip() == f'# import redirect {pkg_name} -> {package_root}'
