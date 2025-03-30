from __future__ import annotations

import contextlib
import datetime
import functools
import itertools
import json
import logging
import mimetypes
import operator
import pathlib
import re
import subprocess
import types
import urllib.parse
from collections.abc import Mapping

import gitlab
import jaraco.functools
import jaraco.vcs
import packaging.requirements
import requests
import setuptools_scm
from jaraco.context import suppress
from more_itertools import unique_everseen
from packaging.version import Version
from pip_run import scripts

from ..deps import imports, pypi

log = logging.getLogger(__name__)

mimetypes.add_type('text/plain', '', strict=True)
mimetypes.add_type('text/markdown', '.md', strict=True)
mimetypes.add_type('text/x-rst', '.rst', strict=True)


@suppress(subprocess.CalledProcessError)
def origin() -> str:
    return subprocess.check_output(
        ['git', 'remote', 'get-url', 'origin'],
        text=True,
        encoding='utf-8',
    ).strip()


def name_from_vcs() -> str | None:
    """
    >>> name_from_vcs()
    'coherent.build'
    """
    return name_from_origin(origin())


def owner_from_vcs() -> str | None:
    """
    >>> owner_from_vcs()
    'coherent-oss'
    """
    return owner_from_origin(origin())


@jaraco.functools.pass_none
def name_from_origin(origin: str | None) -> str:
    _, _, tail = origin.rpartition('/')
    return tail.removesuffix('.git')


@jaraco.functools.pass_none
def owner_from_origin(origin: str | None) -> str:
    head, _, _ = origin.rpartition('/')
    _, _, owner = head.rpartition('/')
    return owner


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
def repo_info() -> Mapping:
    return github_repo_info() or gitlab_repo_info()


def remove_color_codes(text):
    """
    Remove ANSI color codes from a string. (coherent-oss/system#20)
    """
    ansi_escape = r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])'
    return re.sub(ansi_escape, '', text)


@suppress(subprocess.CalledProcessError, FileNotFoundError)
def github_repo_info() -> Mapping:
    out = subprocess.check_output(
        ['gh', 'repo', 'view', '--json', 'description,url'],
        text=True,
        encoding='utf-8',
    )
    data = json.loads(remove_color_codes(out))
    return {k: v for k, v in data.items() if v}


@suppress(gitlab.exceptions.GitlabError)
def gitlab_repo_info() -> Mapping:
    api = gitlab.Gitlab('https://gitlab.com')
    name = name_from_vcs()
    owner = owner_from_vcs()
    project = api.projects.get(f'{owner}/{name}')
    result = dict(url=project.web_url)
    if project.description:
        result.update(description=project.description)
    return result


def summary():
    """
    Load the summary from hosted project.

    >>> summary()
    'A zero-config Python project build backend'
    """
    return repo_info().get('description')


def source_url():
    """
    Load the repo URL from hosted project.

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


def declared_deps():
    """
    Read deps from ``__init__.py``.
    """
    return scripts.DepsReader.search(['__init__.py'])


def source_files():
    """
    Return all files in the source distribution.

    >>> list(source_files())
    [...Path('discovery.py')...]
    """
    return (
        pathlib.Path(path)
        for path in subprocess.check_output(['git', 'ls-files'], text=True).splitlines()
    )


def is_python(path: pathlib.Path) -> bool:
    return path.suffix == '.py'


def base(module):
    """
    >>> base(pathlib.Path('foo/bar/bin.py'))
    'coherent.build.foo.bar'
    >>> base(pathlib.Path('foo.py'))
    'coherent.build'
    """
    return '.'.join((best_name(),) + module.parent.parts)


def is_local(import_):
    return import_.name.startswith(best_name())


def inferred_deps():
    """
    Infer deps from module imports.
    """
    imps = (
        types.SimpleNamespace(name=imp.relative_to(base(module)), module=module)
        for module in filter(is_python, source_files())
        for imp in imports.get_module_imports(module)
        if not imp.excluded()
    )
    for imp in itertools.filterfalse(is_local, imps):
        # TODO(#30): Handle resolution errors gracefully
        yield pypi.distribution_for(imp.name) + extra_for(imp.module)


def combined_deps():
    def normalize(name):
        return re.sub(r'[.-_]', '-', name).lower()

    def package_name(dep):
        return normalize(packaging.requirements.Requirement(dep).name)

    return unique_everseen(
        itertools.chain(declared_deps(), inferred_deps()),
        key=package_name,
    )


def extra_for(module: pathlib.Path) -> str:
    """
    Emit appropriate extra marker if relevant to the module's path.

    >>> extra_for(pathlib.Path('foo/bar'))
    ''
    >>> extra_for(pathlib.Path('foo.py'))
    ''
    >>> extra_for(pathlib.Path('tests/functional/foo'))
    '; extra=="test"'
    >>> extra_for(pathlib.Path('docs/conf.py'))
    '; extra=="doc"'
    """
    mapping = dict(tests='test', docs='doc')
    try:
        return f'; extra=="{mapping[str(list(module.parents)[-2])]}"'
    except (KeyError, IndexError):
        return ''


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
    """
    >>> extras_from_deps(['requests'])
    set()
    >>> extras_from_deps(['pytest; extra == "test"'])
    {'test'}
    >>> sorted(extras_from_deps([
    ...     'requests',
    ...     'pytest; extra == "test"',
    ...     'pytest-cov; extra == "test"',
    ...     'sphinx; extra=="doc"']))
    ['doc', 'test']
    """
    return functools.reduce(operator.or_, map(extras_from_dep, deps), set())


def full_extras(deps):
    """
    Ensure that implied extras are included in the extras.

    Ref coherent-oss/coherent.test#5.
    """
    deps.add('test')
    deps.add('doc')
    return deps


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


def join(*strings):
    return ''.join(strings)


def inject_badges(readme, type):
    """
    Put badges at the top of the readme.
    """
    return '\n\n'.join(itertools.chain(render_badges(type), [readme]))


def render_badge(type, *, image, target=None, alt_text=''):
    """
    >>> print(render_badge('markdown', image='file://foo.img', alt_text='foo'))
    ![foo](file://foo.img)
    >>> print(render_badge('rst', image='file://foo.img', alt_text='foo'))
    .. image:: file://foo.img
       :alt: foo
    """
    markdown = join(
        '[' * bool(target),
        '![{alt_text}]({image})',
        ']({target})' * bool(target),
    )
    rst = join(
        '.. image:: {image}',
        '\n   :target: {target}' * bool(target),
        '\n   :alt: {alt_text}' * bool(alt_text),
    )
    return locals().get(type, markdown).format_map(locals())


def render_badges(type):
    _, _, subtype = type.partition('/')
    rb = functools.partial(render_badge, subtype.replace('x-', ''))
    PROJECT = best_name()
    URL = source_url()
    yield rb(
        image=f'https://img.shields.io/pypi/v/{PROJECT}',
        target=f'https://pypi.org/project/{PROJECT}',
    )

    yield rb(image=f'https://img.shields.io/pypi/pyversions/{PROJECT}')

    yield rb(
        image=f'{URL}/actions/workflows/main.yml/badge.svg',
        target=f'{URL}/actions?query=workflow%3A%22tests%22',
    )

    yield rb(
        image=(
            'https://img.shields.io/endpoint?'
            'url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json'
        ),
        target='https://github.com/astral-sh/ruff',
        alt_text='Ruff',
    )

    system = urllib.parse.quote('coherent system')
    yield rb(
        image=f'https://img.shields.io/badge/{system}-informational',
        target='https://github.com/coherent-oss/system',
        alt_text='Coherent Software Development System',
    )


def description_from_readme():
    with contextlib.suppress(ValueError, AssertionError):
        (readme,) = pathlib.Path().glob('README*')
        ct = guess_content_type(readme)
        assert ct
        yield 'Description-Content-Type', ct
        yield 'Description', inject_badges(readme.read_text(encoding='utf-8'), ct)


def age_of_repo():
    """Return the age of the repo."""
    return jaraco.vcs.repo().age()


def generate_classifiers():
    yield (
        'Development Status :: 4 - Beta'
        if Version(version_from_vcs()) < Version('1.0')
        else 'Development Status :: 5 - Production/Stable'
        if age_of_repo() < datetime.timedelta(days=365)
        else 'Development Status :: 6 - Mature'
    )
    yield 'Intended Audience :: Developers'
    yield 'License :: OSI Approved :: MIT License'
    yield 'Programming Language :: Python :: 3'
    yield 'Programming Language :: Python :: 3 :: Only'
