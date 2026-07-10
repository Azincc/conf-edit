from __future__ import annotations

import hashlib
from pathlib import Path
import urllib.request


BASE_URL = "https://cdn.jsdelivr.net/npm/codemirror@5.65.18/"
FILES = {
    "lib/codemirror.min.js": (
        "9eb3d93e642327e5f350342a60e6810aa1543644ba003e41bad2f372ead3b372"
    ),
    "lib/codemirror.min.css": (
        "d8fddcfca0ccaeea67ddd557d22340530a1daae8a09843e8f4c25d7def06efa8"
    ),
    "mode/javascript/javascript.min.js": (
        "b96dd971a4c0b083fd65bf361ab5958a74010bafb629eaa1592e20797f53995b"
    ),
    "mode/sql/sql.min.js": (
        "74a69758a1555997dcbcb8f8ab5d0cb1d7d80ccdcdde7af223186921a021c2af"
    ),
    "addon/edit/matchbrackets.min.js": (
        "3c9e6befa28b77612e4541effc48988137505070cda12ee7644749afb4db070f"
    ),
    "addon/dialog/dialog.min.css": (
        "94ecb2e6f83cad6ec25b6f27651983e9e94cd52b4e9ce13cc96999914c9cf67e"
    ),
    "LICENSE": (
        "168a4becc968f5001e2ee2e0291b6e4daabafc1894a11ade1e11d56e96096e07"
    ),
}


def main() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "conf_edit"
        / "static"
        / "vendor"
        / "codemirror"
    )
    for relative, expected in FILES.items():
        request = urllib.request.Request(
            BASE_URL + relative,
            headers={"User-Agent": "ConfEdit asset vendor/0.1"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise SystemExit(
                f"checksum mismatch for {relative}: {actual} != {expected}"
            )
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        print(f"vendored {relative}")


if __name__ == "__main__":
    main()
