import tomlkit

from . import metadata


def render(metadata: metadata.Message):
    system = {
        'build-system': {
            'requires': ['flit-core >=3.11, <4'],
            'build-backend': 'flit_core.buildapi',
        }
    }
    return tomlkit.dumps(system | metadata.render_toml())
