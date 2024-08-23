import logging
import re

import autocommand
import tqdm
from more_itertools import split_before

from . import pypi

log = logging.getLogger(__name__)


@autocommand.autocommand(__name__)
def run(include: re.compile = re.compile('.*'), url=pypi.top_8k, jump: str = ''):
    logging.basicConfig()
    dists = filter(include.match, pypi.Distribution.query(url=url))
    if jump:
        skipped, dists = split_before(dists, lambda dist: dist == jump, maxsplit=1)
        print('skipped', len(skipped))
    for dist in tqdm.tqdm(dists):
        dist.load() or dist.save()
