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
    # ensure Metadata.discover is not called
    monkeypatch.delattr(coherent.build.backend.Metadata, 'discover')
    coherent.build.build_wheel(wheel_root, metadata_directory=md_dir)
