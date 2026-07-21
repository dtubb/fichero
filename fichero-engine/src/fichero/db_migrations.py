from fichero.db.migrations.schema import *; import sys; sys.modules[__name__] = sys.modules["fichero.db.migrations.schema"]  # noqa
