"""
Load metadata for unprocessed distributions.
"""

import tqdm
from jaraco.ui.main import main

from .. import pypi


@main
def run():
    for dist in tqdm.tqdm(pypi.Distribution.unprocessed()):
        dist.refresh()
        dist.save()
