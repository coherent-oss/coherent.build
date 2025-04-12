import pathlib
import re

import tomlkit

from . import layouts, metadata


def render(metadata: metadata.Message):
    system = {
        'build-system': {
            'requires': ['flit-core >=3.11, <4'],
            'build-backend': 'flit_core.buildapi',
        }
    }
    return tomlkit.dumps(system | metadata.render_toml())


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
