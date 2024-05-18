import contextlib
import functools
import json
import logging
import operator
import pathlib
import subprocess
import types
import mimetypes
from collections.abc import Mapping

import jaraco.functools
import packaging.requirements
import requests
import setuptools_scm
from jaraco.context import suppress
from pip_run import scripts


log = logging.getLogger(__name__)

mimetypes.add_type('text/plain', '', strict=True)
mimetypes.add_type('text/markdown', '.md', strict=True)
mimetypes.add_type('text/x-rst', '.rst', strict=True)


@suppress(subprocess.CalledProcessError)
def name_from_vcs():
    """
    >>> name_from_vcs()
    'coherent.build'
    """
    url = subprocess.check_output(
        ['git', 'remote', 'get-url', 'origin'],
        text=True,
        encoding='utf-8',
    )
    _, _, tail = url.strip().rpartition('/')
    return tail.removesuffix('.git')


def name_from_path():
    """
    >>> name_from_vcs()
    'coherent.build'
    """
    return pathlib.Path('.').absolute().name


def best_name():
    """
    Name is important, so if the name can't be inferred from the VCS,
    use the path.
    """
    return name_from_vcs() or name_from_path()


def version_from_vcs():
    return setuptools_scm.get_version()


def none_as(replacement):
    return lambda val: replacement if val is None else val


@functools.lru_cache
@jaraco.functools.apply(none_as({}))
@suppress(subprocess.CalledProcessError)
def repo_info() -> Mapping:
    data = json.loads(
        subprocess.check_output(
            ['gh', 'repo', 'view', '--json', 'description,url'],
            text=True,
            encoding='utf-8',
        )
    )
    return {k: v for k, v in data.items() if v}


def summary_from_github():
    """
    Load the summary from GitHub.

    >>> summary_from_github()
    'A zero-config Python project build backend'
    """
    return repo_info().get('description')


def source_url():
    """
    Load the repo URL from GitHub.

    >>> source_url()
    'https://github.com/coherent-oss/coherent.build'
    """
    return repo_info().get('url')


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
    try:
        min_ver = branches[0]["name"]
    except KeyError:
        log.warning(f"Unexpected {branches=}")
        min_ver = "3.8"
    return f'>= {min_ver}'


def read_deps():
    """
    Read deps from ``__init__.py``.
    """
    return scripts.DepsReader.search(['__init__.py'])


def extras_from_dep(dep):
    try:
        markers = packaging.requirements.Requirement(dep).marker._markers
    except AttributeError:
        markers = ()
    return set(
        marker[2].value
        for marker in markers
        if isinstance(marker, tuple) and marker[0].value == 'extra'
    )


def extras_from_deps(deps):
    return functools.reduce(operator.or_, map(extras_from_dep, deps))


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
