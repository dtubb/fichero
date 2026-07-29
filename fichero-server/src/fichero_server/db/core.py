from fichero_server.db import *; import sys; sys.modules[__name__] = sys.modules["fichero_server.db"]  # noqa
