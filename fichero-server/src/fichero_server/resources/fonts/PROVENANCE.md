# Bundled fonts (#5210)

Fallback fonts for scripts the system fonts leave as ⍰ or ▦. Served by `GET /api/fonts/<file>`
and listed by `GET /api/fonts` (`api/routes/system/fonts.py`, which holds the fallback order).

Each file is the upstream release **unmodified**, so its sha256 is upstream's. Every licence is
the **SIL Open Font License 1.1** (checked 2026-09-28: the GitHub licence field of each repository
and the `OFL.txt` inside each release), and each font's own OFL text, with its copyright line, sits
beside it. OpenType (CFF) rather than WOFF2: none of the Noto releases ships WOFF2, re-encoding
would make a file whose hash no upstream can confirm, and the set is small either way.

**Size budget: 1.3 MB in all.** Junicode is 0.96 MB of it; the six Noto files are 0.33 MB.

| File | Family | Source (release asset → path in the zip) | Version | sha256 | Licence file |
|---|---|---|---|---|---|
| `Junicode-Regular.otf` | Junicode | https://github.com/psb1558/Junicode-font/releases/tag/v2.226 → `Junicode_2.226.zip` → `Junicode/OTF/Junicode-Regular.otf` | 2.226 | `63980018a8981d02c879bffa3da3dfcd261ebf8f3fee81684877cbfc25745559` | `OFL-Junicode.txt` |
| `NotoSansSyriac-Regular.otf` | Noto Sans Syriac (Estrangela) | https://github.com/notofonts/syriac/releases/tag/NotoSansSyriac-v3.000 → `NotoSansSyriac/unhinted/otf/` | 3.000 | `a75908fd4762ee3ec534fd2df2b58419688ab3454bce47a3abc23eeae7ffe76d` | `OFL-NotoSansSyriac.txt` |
| `NotoSansSyriacWestern-Regular.otf` | Noto Sans Syriac Western (Serto) | https://github.com/notofonts/syriac/releases/tag/NotoSansSyriacWestern-v3.001 → `NotoSansSyriacWestern/unhinted/otf/` | 3.001 | `0768fc7c41605fbd8414d6ec6406ac73fccfd077e463c7e99c32fc766ce6a2b3` | `OFL-NotoSansSyriacWestern.txt` |
| `NotoSansSyriacEastern-Regular.otf` | Noto Sans Syriac Eastern | https://github.com/notofonts/syriac/releases/tag/NotoSansSyriacEastern-v3.001 → `NotoSansSyriacEastern/unhinted/otf/` | 3.001 | `977966153cd374a5bf1d7b28aed5ab0cbdd19114483c7b197a621d5705fdb462` | `OFL-NotoSansSyriacEastern.txt` |
| `NotoSansMongolian-Regular.otf` | Noto Sans Mongolian | https://github.com/notofonts/mongolian/releases/tag/NotoSansMongolian-v3.002 → `NotoSansMongolian/unhinted/otf/` | 3.002 | `b902038425c40d24d8e4ba3843fe7a40b254381196b7356c22207eb88aa9121a` | `OFL-NotoSansMongolian.txt` |
| `NotoSansCoptic-Regular.otf` | Noto Sans Coptic | https://github.com/notofonts/coptic/releases/tag/NotoSansCoptic-v2.004 → `NotoSansCoptic/unhinted/otf/` | 2.004 | `23992dd7d967637d11b4e7fae9db6172ff29dcb195350a14f92496b751c561d9` | `OFL-NotoSansCoptic.txt` |
| `NotoSansCherokee-Regular.otf` | Noto Sans Cherokee | https://github.com/notofonts/cherokee/releases/tag/NotoSansCherokee-v2.001 → `NotoSansCherokee/unhinted/otf/` | 2.001 | `90d55ebb3a6d2d8ea3ee03ec518f1b76073a1cc2d9b0af385c94069ba539a56a` | `OFL-NotoSansCherokee.txt` |

**Not bundled:** Junicode's italic, bold and variable files (a fallback needs one face; the variable
Roman is 1.2 MB as WOFF2). Add them when a surface needs styled MUFI text.
