from __future__ import annotations

import contextlib
import email.message
import email.policy
import functools
import importlib.metadata
import pathlib
import re
from collections.abc import Iterable, Mapping

import packaging

from . import discovery


def _normalize(name):
    return packaging.utils.canonicalize_name(name).replace('-', '_')


@functools.singledispatch
def always_items(
    values: Mapping | email.message.Message | Iterable[tuple[str, str]],
) -> Iterable[tuple[str, str]]:
    """
    Always emit an iterable of pairs, even for Mapping or Message.
    """
    return values


@always_items.register
def _(values: Mapping) -> Iterable[tuple[str, str]]:
    return values.items()


@always_items.register
def _(values: email.message.Message) -> Iterable[tuple[str, str]]:
    return values._headers


class Policy(email.policy.EmailPolicy):
    def header_store_parse(self, name, value):
        return (name, self.header_factory(name, value))


class Message(email.message.Message):
    """
    >>> md = Message.discover()
    >>> md['Summary']
    'A zero-config Python project build backend'

    >>> msg = Message({'Material': 'Kokuyōseki'})
    >>> print(msg.render().strip())
    Material: Kokuyōseki
    """

    def __init__(self, values):
        super().__init__(policy=Policy(utf8=True))
        for item in always_items(values):
            self.add_header(*item)

    def _description_in_payload(self):
        if 'Description' in self:
            self.set_payload(self['Description'])
            del self['Description']

    @property
    def id(self):
        """
        >>> Message(dict(Name='foo.bar', Version='1.0.0')).id
        'foo_bar-1.0.0'
        """
        return f"{_normalize(self['Name'])}-{self['Version']}"

    @classmethod
    def discover(cls):
        """
        >>> md = Message.discover()
        """
        return cls(cls._discover_fields())

    @property
    def author(self):
        return self.parse_contributor(self['Author-Email'])

    @staticmethod
    def parse_contributor(combined):
        exp = re.compile(r'"?(?P<name>.*?)"? <(?P<email>.*)>$')
        return exp.match(combined).groupdict()

    @staticmethod
    def _discover_fields():
        yield 'Metadata-Version', '2.3'
        yield 'Name', discovery.best_name()
        yield 'Version', discovery.version_from_vcs()
        yield 'Author-Email', discovery.author_from_vcs()
        yield 'Summary', discovery.summary()
        yield 'Requires-Python', discovery.python_requires_supported()
        deps = list(discovery.combined_deps())
        for dep in deps:
            yield 'Requires-Dist', dep
        for extra in discovery.full_extras(discovery.extras_from_deps(deps)):
            yield 'Provides-Extra', extra
        yield 'Project-URL', f'Source, {discovery.source_url()}'
        yield from discovery.description_from_readme()
        for classifier in discovery.generate_classifiers():
            yield 'Classifier', classifier

    @classmethod
    def load(cls, info: str | pathlib.Path = pathlib.Path()):
        md = importlib.metadata.PathDistribution(pathlib.Path(info)).metadata
        return (md or None) and cls(md)

    def render(self):
        self._description_in_payload()
        return str(self)

    def render_wheel(self):
        """
        Yield (name, contents) pairs for all metadata files.
        """
        yield 'METADATA', self.render()
        wheel_md = Message({
            'Wheel-Version': '1.0',
            'Generator': 'coherent.build',
            'Root-Is-Purelib': 'true',
            'Tag': 'py3-none-any',
        })
        yield 'WHEEL', wheel_md.render()
        with contextlib.suppress(FileNotFoundError):
            yield (
                'entry_points.txt',
                pathlib.Path('(meta)/entry_points.txt').read_text(),
            )

    def render_toml(self):
        # todo: probably need to write out this file in case it was loaded elsewhere
        (readme,) = pathlib.Path().glob('README*')

        project = {
            "name": self["Name"],
            "version": self["Version"],
            "description": self["Summary"],
            "authors": [self.author],
            "readme": str(readme),
            "requires-python": self["Requires-Python"],
            "dependencies": self.get_all("Requires-Dist"),
            "classifiers": self.get_all("Classifier"),
            'urls': self.urls,
        }

        return project

    @property
    def urls(self):
        return dict(url.split(', ', 1) for url in self.get_all('Project-URL'))
