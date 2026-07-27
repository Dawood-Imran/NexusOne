#!/usr/bin/env python
"""Run the NexusOne Phase 1 web app."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.runtime.config import load_dotenv


# Resolve the repository file before importing the HTTP module: its handler
# constructs the default ChatService at import time.  Existing shell values
# remain authoritative, while a repository-launched process gets .env values.
load_dotenv(ROOT / ".env")

from app.api.dev_server import main  # noqa: E402 - .env must load before ChatService import.


if __name__ == "__main__":
    raise SystemExit(main())
