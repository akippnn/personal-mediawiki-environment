"""
Logger - Unified logging for Local MediaWiki Tools
"""
import sys
from datetime import datetime
from typing import Optional, TextIO
from dataclasses import dataclass
from enum import IntEnum


class LogLevel(IntEnum):
    DEBUG = 0
    INFO = 1
    WARN = 2
    ERROR = 3


@dataclass
class Logger:
    """Configurable logger with optional file output."""
    name: str
    level: LogLevel = LogLevel.INFO
    stream: TextIO = sys.stderr
    show_timestamp: bool = True
    show_level: bool = True
    
    def _format(self, level: str, msg: str) -> str:
        parts = []
        if self.show_timestamp:
            parts.append(f"[{datetime.now().strftime('%H:%M:%S')}]")
        if self.show_level:
            parts.append(f"[{level}]")
        parts.append(f"[{self.name}]")
        parts.append(msg)
        return ' '.join(parts)
    
    def debug(self, msg: str):
        if self.level <= LogLevel.DEBUG:
            print(self._format('DEBUG', msg), file=self.stream)
    
    def info(self, msg: str):
        if self.level <= LogLevel.INFO:
            print(self._format('INFO', msg), file=self.stream)
    
    def warn(self, msg: str):
        if self.level <= LogLevel.WARN:
            print(self._format('WARN', msg), file=self.stream)
    
    def error(self, msg: str):
        if self.level <= LogLevel.ERROR:
            print(self._format('ERROR', msg), file=self.stream)
    
    def __call__(self, msg: str):
        """Shortcut for info-level logging."""
        self.info(msg)


# Global loggers registry
_loggers: dict = {}


def get_logger(name: str, level: Optional[LogLevel] = None) -> Logger:
    """Get or create a logger by name."""
    if name not in _loggers:
        _loggers[name] = Logger(name=name, level=level or LogLevel.INFO)
    elif level is not None:
        _loggers[name].level = level
    return _loggers[name]


def set_global_level(level: LogLevel):
    """Set log level for all existing loggers."""
    for logger in _loggers.values():
        logger.level = level
