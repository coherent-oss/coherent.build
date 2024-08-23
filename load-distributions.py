import logging
import re

import autocommand

from . import pypi

log = logging.getLogger(__name__)


@autocommand.autocommand(__name__)
def run(include: re.compile = re.compile('.*'), url=pypi.top_8k):
    logging.basicConfig()
    for dist in filter(include.match, pypi.Distribution.query(url=url)):
        try:
            dist.load() or dist.save()
            print(dist)
        except Exception as exc:
            log.error(f"{exc} loading {dist}")
