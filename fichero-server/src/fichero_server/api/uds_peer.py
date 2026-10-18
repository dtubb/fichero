"""Who is on the other end of the Unix socket (multiuser-always-on, slice 6b).

The kernel, not the client, says which user and process connected. uvicorn does not put that in the ASGI scope, so the
UDS server runs a protocol subclass that reads the peer's credentials when the connection is made and stamps them onto
every request of that connection as `fichero.peer` = {uid, pid, token}: the user, the pid and the kernel's AUDIT TOKEN
(`LOCAL_PEERTOKEN`, which carries the pid version, so a reused pid is a different token). The program's identity (its
executable and code signature) is then read FROM THAT TOKEN through Security.framework, never by mapping the pid to a
path (review 98). The local-client routes read the stamp and refuse a request without one. TCP connections never get it,
so they can never ask.
"""

from __future__ import annotations

import ctypes
import struct
import sys
from typing import Any

PEER_SCOPE_KEY = "fichero.peer"

_SOL_LOCAL = 0  # macOS
_LOCAL_PEERCRED = 0x001
_LOCAL_PEERPID = 0x002
_LOCAL_PEERTOKEN = 0x006
_AUDIT_TOKEN_BYTES = 32
_PID_WORD = 5  # audit_token_t.val[5] is the pid


def peer_of_socket(sock: Any) -> dict | None:
    """{uid, pid, token} of the process on the other end of a connected Unix socket, or None if the OS will not say."""
    import socket

    try:
        if sys.platform == "darwin":
            cred = sock.getsockopt(_SOL_LOCAL, _LOCAL_PEERCRED, 76)  # struct xucred: version, uid, ...
            uid = struct.unpack_from("=II", cred)[1]
            token = sock.getsockopt(_SOL_LOCAL, _LOCAL_PEERTOKEN, _AUDIT_TOKEN_BYTES)
            pid = struct.unpack("=8I", token)[_PID_WORD]
            return {"uid": uid, "pid": pid, "token": token.hex()}
        pid, uid, _gid = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
    except (OSError, struct.error):
        return None
    return {"uid": uid, "pid": pid, "token": f"pid:{pid}"}  # non-macOS (tests, Linux CI): no audit token exists


def identify(peer: dict) -> dict:
    """What to show the owner about a peer: {pid, exe, signer}. A peer that already names `exe` is returned as is.

    On macOS the executable and signing authority come from the code object the kernel binds to the AUDIT TOKEN."""
    if "exe" in peer:
        return {"pid": peer["pid"], "exe": peer["exe"], "signer": peer.get("signer")}
    exe, signer = _code_identity(peer["token"]) if sys.platform == "darwin" else ("", None)
    return {"pid": peer["pid"], "exe": exe, "signer": signer}


def _code_identity(token_hex: str) -> tuple[str, str | None]:
    """(executable path, "Authority (Team)" or None when unsigned) of the process the audit token names."""
    try:
        token = bytes.fromhex(token_hex)
        cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        sec = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    except (ValueError, OSError):
        return "", None
    try:
        return _code_identity_of(token, cf, sec)
    except (AttributeError, ValueError, OSError):  # a missing symbol: no identity, never a 500
        return "", None


def _code_identity_of(token: bytes, cf: Any, sec: Any) -> tuple[str, str | None]:
    vp, up = ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
    cf.CFDataCreate.restype = vp
    cf.CFDataCreate.argtypes = [vp, ctypes.c_char_p, ctypes.c_long]
    cf.CFDictionaryCreate.restype = vp
    cf.CFDictionaryCreate.argtypes = [vp, up, up, ctypes.c_long, vp, vp]
    cf.CFDictionaryGetValue.restype = vp
    cf.CFDictionaryGetValue.argtypes = [vp, vp]
    cf.CFStringCreateWithCString.restype = vp
    cf.CFStringCreateWithCString.argtypes = [vp, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [vp, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    cf.CFURLCopyFileSystemPath.restype = vp
    cf.CFURLCopyFileSystemPath.argtypes = [vp, ctypes.c_long]
    cf.CFRelease.argtypes = [vp]
    sec.SecCodeCopyGuestWithAttributes.argtypes = [vp, vp, ctypes.c_uint32, up]
    sec.SecCodeCopySigningInformation.argtypes = [vp, ctypes.c_uint32, up]
    audit_key = ctypes.c_void_p.in_dll(sec, "kSecGuestAttributeAudit")
    utf8 = 0x08000100

    def text(value: Any) -> str | None:
        if not value:
            return None
        buffer = ctypes.create_string_buffer(4096)
        return buffer.value.decode() if cf.CFStringGetCString(value, buffer, 4096, utf8) else None

    data = cf.CFDataCreate(None, token, len(token))
    keys, values = (vp * 1)(audit_key.value), (vp * 1)(data)
    attrs = cf.CFDictionaryCreate(None, ctypes.cast(keys, up), ctypes.cast(values, up), 1, None, None)
    code, info = vp(), vp()
    try:
        if sec.SecCodeCopyGuestWithAttributes(None, attrs, 0, ctypes.byref(code)) != 0:
            return "", None
        # kSecCSSigningInformation = 1 << 1
        if sec.SecCodeCopySigningInformation(code, 2, ctypes.byref(info)) != 0:
            return "", None

        def field(name: bytes) -> Any:
            key = cf.CFStringCreateWithCString(None, name, utf8)
            try:
                return cf.CFDictionaryGetValue(info, key)
            finally:
                cf.CFRelease(key)

        executable = field(b"main-executable")
        path_ref = cf.CFURLCopyFileSystemPath(executable, 0) if executable else None
        exe = (text(path_ref) or "") if path_ref else ""
        if path_ref:
            cf.CFRelease(path_ref)
        ident, team = text(field(b"identifier")), text(field(b"teamid"))
        return exe, (f"{ident} ({team})" if ident and team else None)
    finally:
        for ref in (data, attrs, code.value, info.value):
            if ref:
                cf.CFRelease(ref)


class PeerStampingApp:
    """ASGI wrapper for one connection: every http/websocket scope carries that connection's peer."""

    def __init__(self, app: Any, peer: dict | None) -> None:
        self._app = app
        self._peer = peer

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") in ("http", "websocket") and self._peer is not None:
            scope[PEER_SCOPE_KEY] = dict(self._peer)
        await self._app(scope, receive, send)


def peer_aware_http_protocol() -> type:
    """uvicorn's own HTTP protocol (httptools when installed, else h11) that stamps the peer on each connection."""
    try:
        import httptools  # noqa: F401
        from uvicorn.protocols.http.httptools_impl import HttpToolsProtocol as Base
    except ImportError:
        from uvicorn.protocols.http.h11_impl import H11Protocol as Base

    class PeerAwareProtocol(Base):  # type: ignore[misc, valid-type]
        def connection_made(self, transport: Any) -> None:
            super().connection_made(transport)
            # A surprise here must never drop the connection (every UDS request, the embedded app's too): no peer instead.
            try:
                sock = transport.get_extra_info("socket")
                peer = peer_of_socket(sock) if sock is not None else None
            except Exception:  # noqa: BLE001
                peer = None
            self.app = PeerStampingApp(self.app, peer)

    return PeerAwareProtocol
