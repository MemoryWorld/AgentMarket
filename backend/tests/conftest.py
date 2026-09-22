"""All integration tests use disposable local state and the built-in AI fallback."""

import os
import tempfile
from pathlib import Path

from app.core.config import Settings

_test_root = Path(tempfile.mkdtemp(prefix="agentmarket-tests-"))
Settings.model_config["env_file"] = None
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_test_root / 'test.db').as_posix()}"
os.environ["OPENAI_API_KEY"] = ""
os.environ["EXPOSE_DEBUG_OTP"] = "true"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["MEDIA_ROOT"] = str(_test_root / "media")
os.environ["UPLOAD_ROOT"] = str(_test_root / "media" / "uploads")
os.environ["GENERATED_ROOT"] = str(_test_root / "media" / "generated")
