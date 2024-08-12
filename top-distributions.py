"""
Resolve the top-level packages supplied by the most popular distributions.
"""

__requires__ = [
    'requests_toolbelt',
    'autocommand',
    'zipp>=3.20',
    'jaraco.mongodb',
    'keyring',
    'tempora',
]

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

import autocommand
import jaraco.mongodb.helper
import keyring
import tempora.utc
from more_itertools import first, one
from requests_toolbelt import sessions

session = sessions.BaseUrlSession('https://pypi.python.org/pypi/')
log = logging.getLogger(__name__)

url = 'https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json'


@functools.cache
def db():
    username = os.environ.get('DB_USER') or getpass.getuser()
    cluster = os.environ.get('DB_CLUSTER') or 'cluster0.acvlhai.mongodb.net'
    password = keyring.get_password(cluster, username)
    uri = f'mongodb+srv://{username}:{password}@{cluster}/pypi'
    db = jaraco.mongodb.helper.connect_db(uri)
    db.distributions.create_index([('created', 1)], expireAfterSeconds=86400 * 30)
    db.distributions.create_index([('roots', 1)])
    return db.distributions


class Distribution(str):
    @functools.cached_property
    def wheel(self) -> zipfile.Path:
        """
        Return the wheel.
        """
        info = session.get(f'{self}/json').json()
        if 'urls' not in info:
            raise RuntimeError("No URLs")
        match = first(url for url in info['urls'] if url['filename'].endswith('.whl'))
        resp = session.get(match['url'])
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        zf.filename = match['filename']
        return zipfile.Path(zf)

    @classmethod
    def query(cls):
        return map(
            cls, map(operator.itemgetter('project'), session.get(url).json()['rows'])
        )

    def load(self):
        found = db().find_one(dict(norm_name=self))
        doc = found or self.from_wheel()
        vars(self).update(doc)
        return found

    def save(self):
        db().insert_one(dict(self.__json__(), created=tempora.utc.now()))

    def from_wheel(self):
        return dict(
            roots=list(find_roots(*find_names(self.wheel))),
            name=self._get_name(),
        )

    def __json__(self):
        return dict(norm_name=self, name=self.name, roots=self.roots)

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


class Filter(str):
    def __call__(self, dist: Distribution):
        return re.match(self.replace())


@autocommand.autocommand(__name__)
def run(include: re.compile = re.compile('.*')):
    logging.basicConfig()
    for dist in filter(include.match, Distribution.query()):
        try:
            dist.load() or dist.save()
            dist.report()
        except Exception as exc:
            log.exception(f"{exc} loading {dist}")


__name__ == "__main__" and run()
