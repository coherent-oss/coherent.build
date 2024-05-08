import contextlib
import json
import pathlib
import subprocess
import types
import mimetypes

import requests
import setuptools_scm
from jaraco.context import suppress
from pip_run import scripts


mimetypes.add_type('text/plain', '', strict=True)
mimetypes.add_type('text/markdown', '.md', strict=True)
mimetypes.add_type('text/x-rst', '.rst', strict=True)


def name_from_path():
    return pathlib.Path('.').absolute().name


def version_from_vcs():
    return setuptools_scm.get_version()


@suppress(subprocess.CalledProcessError)
def summary_from_github():
    """
    Load the summary from GitHub.

    >>> summary_from_github()
    'A zero-config Python project build backend'
    """
    return (
        json.loads(
            subprocess.check_output(
                ['gh', 'repo', 'view', '--json', 'description'],
                text=True,
                encoding='utf-8',
            )
        )['description']
        or None
    )


def python_requires_supported():
    """
    >>> python_requires_supported()
    '>= 3...'
    """
    owner = 'python'
    repo = 'cpython'
    url = f'https://api.github.com/repos/{owner}/{repo}/branches'
    branches = requests.get(url).json()
    # cheat and grab the first branch, which is the oldest supported Python version
    return f'>= {branches[0]["name"]}'


def read_deps():
    """
    Read deps from ``__init__.py``.
    """
    return scripts.DepsReader.search(['__init__.py'])


def _to_mapping(fame):
    return (dict(zip(fame['columns'], row)) for row in fame['data'])


class Contributor(types.SimpleNamespace):
    @property
    def combined_detail(self):
        return f'"{self.name}" <{self.email}>'


@suppress(Exception)
def author_from_vcs():
    # run git-fame twice to get both name and email
    cmd = ['git-fame', '--format', 'json']
    names_data = json.loads(
        subprocess.check_output(
            cmd,
            text=True,
            encoding='utf-8',
            stderr=subprocess.DEVNULL,
        )
    )
    emails_data = json.loads(
        subprocess.check_output(
            cmd + ['--show-email'],
            text=True,
            encoding='utf-8',
            stderr=subprocess.DEVNULL,
        )
    )
    names_data['columns'][0] = 'name'
    emails_data['columns'][0] = 'email'
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


def description_from_readme():
    with contextlib.suppress(ValueError, AssertionError):
        (readme,) = pathlib.Path().glob('README*')
        ct = guess_content_type(readme)
        assert ct
        yield 'Description-Content-Type', ct
        yield 'Description', readme.read_text(encoding='utf-8')
