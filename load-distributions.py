import itertools
import logging
import re

import autocommand
import tqdm
from more_itertools import split_before

from . import pypi

log = logging.getLogger(__name__)


@autocommand.autocommand(__name__)
def run(
    include: re.compile = re.compile('.*'),
    url=pypi.top_8k,
    jump: str = '',
    skip: int = 0,
):
    logging.basicConfig()
    dists = filter(include.match, pypi.Distribution.query(url=url))
    dists = itertools.islice(dists, skip, None)
    if jump:
        skipped, dists = split_before(dists, lambda dist: dist == jump, maxsplit=1)
        print('skipped', len(skipped))
    try:
        for dist in tqdm.tqdm(list(dists)):
            dist.load() or dist.save()
    except Exception:
        print(f"Unhandled exception processing {dist}")
        raise
