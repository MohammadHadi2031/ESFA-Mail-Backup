from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import log_dir, log_path


def configure_logging() -> logging.Logger:
    logger = logging.getLogger('mailbackup')
    if logger.handlers:
        return logger
    log_dir().mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_path(), maxBytes=2_000_000, backupCount=5, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    return logger

