"""ssh's `SSH_ASKPASS` program (`compute.connect.second-factor-passes-through`): print the answer the person gave.

    python askpass.py "<ssh's prompt>"

Sends the prompt to the engine over the socket in $FICHERO_ASKPASS_SOCKET and prints the reply. Exit 1 (no answer)
when the person refused, did not answer, or the engine is not there. Standard library only.
"""
import json
import os
import socket
import sys


def main() -> int:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(os.environ["FICHERO_ASKPASS_SOCKET"])
            s.sendall((json.dumps({"prompt": sys.argv[1] if len(sys.argv) > 1 else ""}) + "\n").encode())
            line = s.makefile("r").readline()
        answer = json.loads(line)["answer"]
    except (KeyError, OSError, ValueError):
        return 1
    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
