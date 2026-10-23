<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Manual upload page

`index.html` is a hand-driven page for trying the editor's WebSocket file upload against a running `cuems-editor` (or
`cuems-editor-manual`). `static/` holds what it loads (CryptoJS, for the MD5 the upload verifies; a style sheet).

**Nothing here is a test, is packaged, or is run by CI.** It lives under `dev/scripts/`, the developer tools of every CUEMS
repository.

```bash
cuems-editor-manual --port 9093            # or the service on :9092
cd dev/scripts/manual-ui && python3 -m http.server 8000
# open http://localhost:8000/index.html and point it at the WebSocket
```

The reverse-proxy example for serving the WebSocket over TLS is `docs/deploy/000-default-le-ssl.conf`.
