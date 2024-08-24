"""
Load distributions into the database.
"""

import autocommand
import tqdm

from . import pypi


@autocommand.autocommand(__name__)
def run(
    url=pypi.top_8k,
):
    for dist in tqdm.tqdm(list(pypi.Distribution.query(url=url))):
        pypi.store().update_one({"id": dist}, {"$set": dist.__json__()}, upsert=True)
