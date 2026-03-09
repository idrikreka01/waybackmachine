import logging
import os
import sys
from datetime import datetime


def configure_logging(
    log_level: str = "INFO", log_file: str | None = None
) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    log_format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    date_format = "%Y-%m-%dT%H:%M:%S"
    logging.basicConfig(
        format=log_format,
        datefmt=date_format,
        level=level,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    if log_file is None:
        log_file = os.environ.get("LOG_FILE", "logs/logs.log").strip() or None
    if log_file and os.environ.get("LOG_FILE_SESSION", "true").lower() in (
        "1",
        "true",
        "yes",
    ):
        d = os.path.dirname(log_file)
        base = os.path.basename(log_file)
        stem, ext = os.path.splitext(base)
        if not ext:
            ext = ".log"
        ts = datetime.now().strftime("%d%m%Y%H%M")
        log_file = os.path.join(d, f"{stem}{ts}{ext}") if d else f"{stem}{ts}{ext}"
    if log_file:
        d = os.path.dirname(log_file)
        if d:
            os.makedirs(d, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
        logging.getLogger().addHandler(file_handler)
