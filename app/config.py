from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = f"sqlite:///{(BASE_DIR / 'tiktok.db').as_posix()}"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"
PROFILE_DIR = BASE_DIR / ".playwright-profile"
GUEST_PROFILE_DIR = BASE_DIR / ".playwright-guest-profile"
OUTPUT_DIR = BASE_DIR / "output"
