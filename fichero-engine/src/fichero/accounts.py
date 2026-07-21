from fichero.security.accounts import *  # noqa: F401,F403
import sys
sys.modules[__name__] = sys.modules["fichero.security.accounts"]
