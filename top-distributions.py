"""
Resolve the top-level packages supplied by the most popular distributions.
"""

__requires__ = ['requests_toolbelt', 'autocommand']

import functools
import io
import itertools
import json
import logging
import operator
import pathlib
import re
import sys
import zipfile

from typing import Iterator

import autocommand
from more_itertools import first
from requests_toolbelt import sessions

session = sessions.BaseUrlSession('https://pypi.python.org/pypi/')
log = logging.getLogger(__name__)

url = 'https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json'


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

    @property
    def roots(self):
        return find_roots(*find_names(self.wheel))

    def report(self):
        json.dump({str(self): list(self.roots)}, sys.stdout)
        print(flush=True)


def top(package_name: str) -> str:
    """
    >>> top(foo.bar')
    'foo'
    >>> top(foo.bar.baz')
    'foo'
    >>> top('foo')
    None
    """
    top, sep, name = package_name.partition('.')
    return sep and top


def parent(package_name: str) -> str:
    """
    >>> parent(foo.bar')
    'foo'
    >>> parent(foo.bar.baz')
    'foo.bar'
    >>> parent('foo')
    None
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
    )


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
            dist.report()
        except Exception as exc:
            log.exception(f"{exc} loading {dist}")


__name__ == "__main__" and run()
