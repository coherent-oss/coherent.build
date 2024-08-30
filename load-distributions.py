"""
Load distributions into the database.
"""

import tqdm
from jaraco.ui.main import main

from . import pypi


@main
def run(
    url: str = pypi.top_8k,
):
    for dist in tqdm.tqdm(list(pypi.Distribution.query(url=url))):
        dist.save()
