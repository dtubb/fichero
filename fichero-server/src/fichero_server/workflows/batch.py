from fichero_server.execution.batch import *  # noqa
import sys
sys.modules[__name__] = sys.modules["fichero_server.execution.batch"]
