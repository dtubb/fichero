BLOCKED: All remaining 0.0.2 tasks require Daniel's on-device verification

## Why

All autonomous code for milestone 0.0.2 is merged. Remaining open issues are:
- Drag/drop gesture bugs (#598, #607, #610, #612) — require live on-device testing
- Image zoom regression (#599) — requires live on-device testing
- Run Workflow toolbar (#609) — code already fixed, needs running-app verification
- Settings layout (#556) — code already fixed (.formStyle(.grouped)), needs running-app screenshot
- PDF navigation (#595) — requires Daniel's architecture decision
- Sparkle auto-update (#520) — requires release-signing cert from Daniel
- PDF hover loupe (#590) — deferred to 0.0.3

## Next Steps

Daniel runs the on-device sweep, closes verified issues, then resumes the loop.
Do NOT start 0.0.3 until Daniel approves 0.0.2.
