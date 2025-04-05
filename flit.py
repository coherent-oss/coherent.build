import sys

import tomlkit

from . import metadata


def write():
    md = metadata.Message.discover()
    system = {
        'build-system': {
            'requires': ['flit-core >=3.11, <4'],
            'build-backend': 'flit_core.buildapi',
        }
    }
    tomlkit.dump(system | md.render_toml(), sys.stdout)


__name__ == '__main__' and write()
