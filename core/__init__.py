"""
Core - Shared utilities for Local MediaWiki Tools
"""
from .client import MediaWikiClient
from .logger import get_logger, Logger

__all__ = ['MediaWikiClient', 'get_logger', 'Logger']
