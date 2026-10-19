"""프로젝트 `.env` 값을 환경변수로 읽는 공용 함수(추가 패키지 없음)."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path) -> None:
    """`KEY=VALUE` 줄을 읽어 아직 설정되지 않은 환경변수만 채운다. 파일이 없으면 아무것도 하지 않는다."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)
