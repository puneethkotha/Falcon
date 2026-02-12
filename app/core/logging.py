"""Structured logging configuration."""
import logging
import sys
from typing import Any, Dict

from pythonjsonlogger import jsonlogger

from app.core.config import settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields."""

    def add_fields(
        self,
        log_record: Dict[str, Any],
        record: logging.LogRecord,
        message_dict: Dict[str, Any],
    ) -> None:
        """Add custom fields to log record."""
        super().add_fields(log_record, record, message_dict)
        log_record["worker_id"] = settings.worker_id
        log_record["app_name"] = settings.app_name
        log_record["environment"] = settings.environment


def setup_logging() -> None:
    """Configure structured logging."""
    # Remove existing handlers
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    
    # Create formatter
    formatter = CustomJsonFormatter(
        "%(timestamp)s %(level)s %(name)s %(message)s %(worker_id)s",
        rename_fields={
            "levelname": "level",
            "name": "logger",
            "asctime": "timestamp",
        },
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    
    handler.setFormatter(formatter)
    
    # Set handler
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper()))
    
    # Set third-party loggers to WARNING
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
