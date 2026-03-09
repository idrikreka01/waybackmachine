import os

from dotenv import load_dotenv

load_dotenv()


FORUM_INDEX_URL = os.environ.get(
    "FORUM_INDEX_URL",
    "https://web.archive.org/web/20160111013726/http://www.fullsizechevy.com/forum/forum.php?s=931416f578f3df8ba961974484327e8f",
)


REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "45.0"))
REQUEST_DELAY = float(os.environ.get("REQUEST_DELAY", "1.0"))
RETRY_ATTEMPTS = int(os.environ.get("RETRY_ATTEMPTS", "5"))
RETRY_BACKOFF_BASE = float(os.environ.get("RETRY_BACKOFF_BASE", "2.0"))
COOLDOWN_BACKOFF_SECONDS = float(os.environ.get("COOLDOWN_BACKOFF_SECONDS", "300"))
COOLDOWN_EXTRA_ATTEMPTS = int(os.environ.get("COOLDOWN_EXTRA_ATTEMPTS", "2"))

RETRYABLE_STATUSES = (429, 502, 503, 504)

HEADLESS = os.environ.get("HEADLESS", "true").lower() in ("1", "true", "yes")
USE_WEBDRIVER_MANAGER = os.environ.get("USE_WEBDRIVER_MANAGER", "false").lower() in (
    "1",
    "true",
    "yes",
)
BROWSER_WAIT_TIMEOUT = float(os.environ.get("BROWSER_WAIT_TIMEOUT", "30.0"))
BROWSER_PAGE_LOAD_TIMEOUT = float(os.environ.get("BROWSER_PAGE_LOAD_TIMEOUT", "45.0"))
_chrome_ver = os.environ.get("CHROME_VERSION_MAIN", "").strip()
CHROME_VERSION_MAIN = int(_chrome_ver) if _chrome_ver.isdigit() else None

LOG_FILE = os.environ.get("LOG_FILE", "logs/logs.log").strip() or None

EVERGREEN_SAVE_DECISIONS = (
    os.environ.get("EVERGREEN_SAVE_DECISIONS", "PROMOTE,HOLD").strip().upper() or "PROMOTE,HOLD"
)
EVERGREEN_SAVE_DECISION_SET = frozenset(
    d.strip() for d in EVERGREEN_SAVE_DECISIONS.split(",") if d.strip()
)
_evergreen_min = os.environ.get("EVERGREEN_MIN_SCORE", "").strip()
EVERGREEN_MIN_SCORE = int(_evergreen_min) if _evergreen_min.isdigit() else None
LOG_FILE_SESSION = os.environ.get("LOG_FILE_SESSION", "true").lower() in (
    "1",
    "true",
    "yes",
)


def get_database_url() -> str:
    path = os.environ.get("DATABASE_PATH", "wayback.sqlite")
    if path == ":memory:":
        return "sqlite:///:memory:"
    if not path.startswith("/") and ":" not in path:
        path = os.path.abspath(path)
    return f"sqlite:///{path}"
