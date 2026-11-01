"""Constante pentru Apă Ilfov."""
from __future__ import annotations

DOMAIN = "apa_ilfov"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SERVER = "server"
CONF_PORT = "port"
CONF_SENDER = "sender"

OPT_FROM_YEAR = "from_year"
OPT_SCAN_MINUTES = "scan_minutes"
OPT_FOLDER = "folder"

DEFAULT_SERVER = "imap.gmail.com"
DEFAULT_PORT = 993
DEFAULT_SENDER = "no-reply@acilfov.ro"
DEFAULT_SCAN_MINUTES = 60
DEFAULT_FOLDER = "INBOX"
DEFAULT_FROM_YEAR = 2026

EVENT_NEW_INVOICE = "apa_ilfov_factura_noua"
STORAGE_VERSION = 1
