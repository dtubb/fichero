from fichero.security.url_security import *  # noqa: F401,F403
import sys
sys.modules[__name__] = sys.modules["fichero.security.url_security"]
