from fichero.security.security_scoped_access import *  # noqa: F401,F403
import sys
sys.modules[__name__] = sys.modules["fichero.security.security_scoped_access"]
