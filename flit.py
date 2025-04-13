import pathlib
import re

import importlib_metadata as ilm
import jaraco.functools
import tomlkit
from jaraco.context import suppress

from . import layouts, metadata
from .discovery import none_as

unique = dict.fromkeys


@jaraco.functools.apply(none_as({}))
@suppress(FileNotFoundError)
def entry_points(source='(meta)/entry_points.txt') -> dict[str, str]:
    """
    Parse any entry points found in (meta) as pyproject metadata.

    >>> doc = entry_points('tests/entry points.txt')
    >>> len(doc)
    2
    >>> doc['scripts']['flit']
    'flit:main'
    >>> doc['entry-points']['pygments.lexers']
    {'dogelang': 'dogelang.lexer:DogeLexer'}

    >>> entry_points('tests/does-not-exist')
    {}
    """
    eps = ilm.EntryPoints(ilm.EntryPoints._from_text(pathlib.Path(source).read_text()))
    scripts_keys = {'console_scripts', 'gui_scripts'}
    scripts = {ep.name: ep.value for ep in eps if ep.group in scripts_keys}
    other_groups = unique(ep.group for ep in eps if ep.group not in scripts_keys)
    other_eps = {
        group: {ep.name: ep.value for ep in eps.select(group=group)}
        for group in other_groups
    }
    return dict(
        {'entry-points': other_eps},
        scripts=scripts,
    )


def render(metadata: metadata.Message):
    system = {
        'build-system': {
            'requires': ['flit-core >=3.11, <4'],
            'build-backend': 'flit_core.buildapi',
        }
    }
    project = dict(project=metadata.render_toml() | entry_points())
    return tomlkit.dumps(system | project)


class SDist(layouts.SDist):
    """
    Customize the handling to generate a flit-compatible layout.

    Puts README in the root, but the rest in the package.

    >>> import types
    >>> from .metadata import Message
    >>> md = Message((('Name', 'foo'), ('Version', '1.0')))

    >>> sf = SDist(metadata=md)

    >>> sf(types.SimpleNamespace(name='./bar.py'))
    namespace(name='foo-1.0/foo/bar.py')

    >>> sf(types.SimpleNamespace(name='./README.md'))
    namespace(name='foo-1.0/README.md')
    """

    ignored = layouts.SDist.ignored + [re.escape('pyproject.toml')]

    def prefix(self, name):
        package = self.metadata['Name'].replace('.', '/')
        root_pattern = '|'.join(layouts.Wheel.ignored)
        if re.match(root_pattern, name):
            return pathlib.PurePath(self.metadata.id)
        return pathlib.PurePath(self.metadata.id, package)

    def add_files(self):
        yield from super().add_files()
        yield layouts.make_tarinfo(
            f'{self.metadata.id}/pyproject.toml', render(self.metadata)
        )
