(AI generated. Not reviewed.)

# Device Pairing Smoke

Use this after backend pairing changes or before a release candidate.

1. Launch the Mac host with remote pairing enabled and a configured TLS SPKI pin.
2. On the Mac, sign in as the owner and open the pairing flow.
3. Confirm the QR payload shows a fresh code, expiry, and the expected reachable HTTPS host.
4. Scan or enter the pairing payload from an iPad/iPhone/visionOS client.
5. Confirm pairing succeeds and the client can browse a library route immediately after receiving its device token.
6. Reconnect with the same paired device and confirm browsing still works without re-pairing.
7. Revoke the paired device on the Mac and confirm the client’s next library request fails with `401`.
8. Confirm non-HTTPS remote pairing, a missing/mismatched SPKI configuration, and non-loopback bootstrap-token use are all rejected fail-closed.

Reference: the automated backend gate for this flow lives in
`fichero-server/tests/integration/test_device_pairing_e2e.py`.
