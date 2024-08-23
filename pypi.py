"""
Resolve the top-level packages supplied by the most popular distributions.
"""

import functools
import getpass
import io
import importlib.metadata
import itertools
import json
import logging
import operator
import os
import pathlib
import re
import sys
from zipp.compat.overlay import zipfile

from typing import Iterator

import jaraco.mongodb.helper
import keyring
import tempora.utc
from more_itertools import first, one
from requests_toolbelt import sessions
from requests_file import FileAdapter


session = sessions.BaseUrlSession('https://pypi.python.org/pypi/')
session.mount('file://', FileAdapter())
log = logging.getLogger(__name__)

top_8k = 'https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json'


@functools.cache
def store():
    db = client(getpass.getuser())
    db.distributions.create_index([('roots', 1)])
    db.distributions.create_index([('id', 1)])
    return db.distributions


@functools.cache
def client(username=None):
    username = username or os.environ.get('DB_USER') or 'anonymous'
    cluster = os.environ.get('DB_CLUSTER') or 'cluster0.acvlhai.mongodb.net'
    password = keyring.get_password(cluster, username) or 'coherent.build'
    uri = f'mongodb+srv://{username}:{password}@{cluster}/pypi'
    return jaraco.mongodb.helper.connect_db(uri)


def create_anonymous_user():
    client(getpass.getuser()).command(
        "createUser", "anonymous", pwd="coherent.build", roles=["read"]
    )


def all_names(module):
    """
    Given a module name, yield all possible roots.

    >>> list(all_names('foo.bar.baz'))
    ['foo.bar.baz', 'foo.bar', 'foo']
    """
    yield module
    parent, _, _ = module.rpartition('.')
    if not parent:
        return
    yield from all_names(parent)


def is_root(module):
    return client().distributions.find_one({'roots': module})


def distribution_for(import_name):
    """
    Resolve a distribution name from an import name.
    """
    return next(filter(bool, map(is_root, all_names(import_name))))['name']


class Distribution(str):
    @functools.cached_property
    def wheel(self) -> zipfile.Path:
        """
        Return the wheel.
        """
        info = session.get(f'{self}/json').json()
        if 'urls' not in info:
            raise RuntimeError("No URLs")
        try:
            match = first(
                url for url in info['urls'] if url['filename'].endswith('.whl')
            )
        except ValueError:
            raise ValueError("No wheels")
        resp = session.get(match['url'])
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        zf.filename = match['filename']
        return zipfile.Path(zf)

    @classmethod
    def query(cls, url=top_8k):
        return map(
            cls, map(operator.itemgetter('project'), session.get(url).json()['rows'])
        )

    def load(self):
        found = store().find_one(dict(id=self))
        doc = found or self.from_wheel()
        vars(self).update(doc)
        return found

    def save(self):
        store().insert_one(dict(self.__json__(), updated=tempora.utc.now()))

    def from_wheel(self):
        return dict(
            roots=list(find_roots(*find_names(self.wheel))),
            name=self._get_name(),
        )

    def __json__(self):
        return dict(id=self, name=self.name, roots=self.roots)

    def _get_name(self):
        info = one(self.wheel.glob('*.dist-info'))
        return importlib.metadata.PathDistribution(info).name

    def report(self):
        json.dump(self.__json__(), sys.stdout)
        print(flush=True)


def top(package_name: str) -> str:
    """
    >>> top('foo.bar')
    'foo'
    >>> top('foo.bar.baz')
    'foo'
    >>> top('foo')
    ''
    """
    top, sep, name = package_name.partition('.')
    return sep and top


def parent(package_name: str) -> str:
    """
    >>> parent('foo.bar')
    'foo'
    >>> parent('foo.bar.baz')
    'foo.bar'
    >>> parent('foo')
    ''
    """
    parent, sep, name = package_name.rpartition('.')
    return sep and parent


def find_roots(*packages: str) -> Iterator[str]:
    """
    Given a set of package paths, find all the top-level names.

    >>> list(find_roots('boto3', 'boto3.docs', 'spare'))
    ['boto3', 'spare']
    """
    return (
        pkg
        for pkg in packages
        if top(pkg) not in packages and parent(pkg) not in packages
    )


def find_packages(wheel: zipfile.Path):
    """
    Find all Python packages in the wheel.
    """
    return (
        init.parent.at.rstrip('/').replace('/', '.')
        for init in wheel.glob('**/__init__.py')
        if not is_namespace(init)
    )


ns_pattern = re.compile(
    r'import.*(pkg_resources|pkgutil).*'
    r'(\.declare_namespace\(__name__\)|\.extend_path\(__path__, __name__\))',
    flags=re.DOTALL,
)


def is_namespace(init: zipfile.Path) -> bool:
    r"""
    Is the init file one of the namespace package declarations.

    >>> pkgutil = "__path__ = __import__('pkgutil').extend_path(__path__, __name__)"
    >>> bool(ns_pattern.search(pkgutil))
    True
    >>> pkg_res = "import pkg_resources\npkg_resources.declare_namespace(__name__)"
    >>> bool(ns_pattern.search(pkg_res))
    True
    """
    text = init.read_text(encoding='utf-8')
    return len(text) < 2**10 and ns_pattern.search(text)


def find_modules(wheel: zipfile.Path):
    """
    Find all modules in the wheel.
    """
    return (
        str(pathlib.PurePosixPath(modfile.at).with_suffix('')).replace('/', '.')
        for modfile in itertools.chain(
            wheel.glob('**/*.py'),
            wheel.glob('*.py'),
        )
        if modfile.name != '__init__.py'
    )


def importable(name: str) -> bool:
    return all(map(str.isidentifier, name.split('.')))


def find_names(wheel):
    return filter(
        importable, itertools.chain(find_packages(wheel), find_modules(wheel))
    )
