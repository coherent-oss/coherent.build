import logging
import runpy

from . import bootstrap


def run():
    logging.basicConfig()
    with bootstrap.write_pyproject():
        runpy.run_module('build', run_name='__main__')


__name__ == '__main__' and run()
