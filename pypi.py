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
import tokenize
from zipp.compat.overlay import zipfile

from typing import Iterator

import jaraco.collections
import jaraco.mongodb.helper
import keyring
import tempora.utc
from jaraco.context import suppress
from jaraco.functools import apply
from more_itertools import first, one
from requests.exceptions import HTTPError
from requests_toolbelt import sessions
from requests_file import FileAdapter
from retry_requests import retry


session = retry(sessions.BaseUrlSession('https://pypi.python.org/pypi/'))
session.mount('file://', FileAdapter())
log = logging.getLogger(__name__)

top_8k = 'https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json'


@functools.cache
def store():
    """
    An authenticated, read-write connection to the collection.
    """
    db = client(getpass.getuser())
    db.distributions.create_index([('roots', 1)])
    db.distributions.create_index([('id', 1)])
    return db.distributions


@functools.cache
def client(username=None):
    """
    A client to the database.

    Defaults to an anonymous, read-only connection if no username is supplied.
    """
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
        resp = session.get(f'{super().__str__()}/json')
        resp.raise_for_status()
        info = resp.json()
        if 'urls' not in info:
            raise ValueError("No dists")
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
        return map(cls.from_row, session.get(url).json()['rows'])

    @classmethod
    def from_row(cls, row):
        self = cls(row['project'])
        self.downloads = row['download_count']
        return self

    @classmethod
    def unprocessed(cls):
        query = {"updated": {"$exists": False}}
        return map(cls, map(operator.itemgetter('id'), store().find(query)))

    def refresh(self):
        vars(self).update(self.from_wheel())

    def save(self):
        return store().update_one({"id": self}, {"$set": self.__json__()}, upsert=True)

    def from_wheel(self):
        updated = tempora.utc.now()
        try:
            return dict(
                name=self._get_name(),
                roots=list(find_roots(*find_names(self.wheel))),
                updated=updated,
            )
        except (ValueError, HTTPError, KeyError) as exc:
            return dict(
                error=str(exc),
                updated=updated,
            )

    def __json__(self):
        keys = ['name', 'roots', 'error', 'downloads', 'updated']
        return dict(id=self, **jaraco.collections.Projection(keys, vars(self)))

    def _get_name(self):
        info = one(self.wheel.glob('*.dist-info'))
        return importlib.metadata.PathDistribution(info).name

    def __str__(self):
        return json.dumps(self.__json__())


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


def open(path: zipfile.Path):
    """
    Modeled after tokenize.open, open the path using detected encoding.
    """
    buffer = path.open('rb')
    try:
        encoding, lines = tokenize.detect_encoding(buffer.readline)
        buffer.seek(0)
        text = io.TextIOWrapper(buffer, encoding, line_buffering=True)
        text.mode = 'r'
        return text
    except Exception:
        buffer.close()
        raise


@apply(bool)
@suppress(SyntaxError)
def is_namespace(init: zipfile.Path) -> bool:
    r"""
    Is the init file one of the namespace package declarations.

    >>> pkgutil = getfixture('tmp_path') / 'pkgutil'
    >>> pkgutil_decl = "__path__ = __import__('pkgutil').extend_path(__path__, __name__)"
    >>> _ = pkgutil.write_text(pkgutil_decl)
    >>> is_namespace(pkgutil)
    True

    >>> pkg_res = getfixture('tmp_path') / 'pkg_res'
    >>> _ = pkg_res.write_text("import pkg_resources\npkg_resources.declare_namespace(__name__)")
    >>> is_namespace(pkg_res)
    True

    In case the file cannot be parsed, return False.

    >>> invalid = getfixture('tmp_path') / 'invalid'
    >>> empty_rar = b'Rar!\x1a\x07\x01\x00\xc1\xdf_V\x03\x01\x04\x00\x1dwVQ\x03\x05\x04\x00'
    >>> _ = invalid.write_bytes(empty_rar)
    >>> is_namespace(invalid)
    False

    The encoding should be honored.

    >>> latin1 = getfixture('tmp_path') / 'latin1'
    >>> latin1_hdr = '# -*- coding: latin-1 -*-\n"Æ"\n'
    >>> _ = latin1.write_text(latin1_hdr, encoding='latin1')
    >>> is_namespace(latin1)
    False
    >>> _ = latin1.write_text(latin1_hdr + pkgutil_decl, encoding='latin1')
    >>> is_namespace(latin1)
    True
    """
    with open(init) as strm:
        text = strm.read()
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
