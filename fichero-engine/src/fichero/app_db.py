from fichero.db.app import *; import sys; sys.modules[__name__] = sys.modules["fichero.db.app"]  # noqa
