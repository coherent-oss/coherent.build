import os
import subprocess

from coherent.build import discovery

author = dict(name='Test Author', email='test@example.com')


def make_repo(path):
    """
    Create a git repo in path with one commit authored by ``author``.
    """
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME=author['name'],
        GIT_AUTHOR_EMAIL=author['email'],
        GIT_COMMITTER_NAME=author['name'],
        GIT_COMMITTER_EMAIL=author['email'],
    )
    subprocess.check_call(['git', 'init', '-q'], cwd=path)
    (path / 'README.md').write_text('Sample project', encoding='utf-8')
    subprocess.check_call(['git', 'add', '.'], cwd=path)
    subprocess.check_call(
        ['git', 'commit', '-qm', 'Initial commit', '--no-gpg-sign'],
        cwd=path,
        env=env,
    )


def test_author_unaffected_by_shadowed_stdlib(tmp_path, monkeypatch):
    """
    A project module shadowing a stdlib module that gitfame imports
    must not defeat author discovery (#69).
    """
    make_repo(tmp_path)
    (tmp_path / 'logging.py').write_text('raise RuntimeError("shadowed")')
    monkeypatch.chdir(tmp_path)
    assert discovery.author_from_vcs() == '{name} <{email}>'.format_map(author)
