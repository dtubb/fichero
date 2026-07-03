import sys

from fichero.importers.sergio_import import *  # noqa: F403

sys.modules[__name__] = sys.modules["fichero.importers.sergio_import"]  # noqa
