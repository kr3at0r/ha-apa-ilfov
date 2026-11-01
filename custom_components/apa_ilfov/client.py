"""Client IMAP (sincron; se rulează în executor) pentru e-mailurile Apa-Canal Ilfov."""
from __future__ import annotations

import email
import imaplib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.utils import parsedate_to_datetime
from typing import Callable

from .parser import Factura, ParseError, parse_body, parse_pdf

_LOGGER = logging.getLogger(__name__)


class AuthError(Exception):
    """Utilizator / parolă de aplicație greșite."""


class ConnectError(Exception):
    """Nu m-am putut conecta la serverul IMAP."""


@dataclass
class Mesaj:
    uid: int
    primit: datetime | None
    facturi: list[Factura]
    erori: list[str]


def proceseaza_mesaj(uid: int, raw: bytes) -> Mesaj:
    """Extrage facturile dintr-un e-mail brut (PDF atașat sau, în lipsă, text)."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    try:
        primit = parsedate_to_datetime(msg["Date"]) if msg["Date"] else None
    except (TypeError, ValueError):
        primit = None

    facturi: list[Factura] = []
    erori: list[str] = []
    pdfs = [
        p.get_payload(decode=True)
        for p in msg.walk()
        if (p.get_filename() or "").lower().endswith(".pdf")
        or p.get_content_type() == "application/pdf"
    ]
    for data in pdfs:
        if not data:
            continue
        try:
            facturi.append(parse_pdf(data))
        except ParseError as err:
            erori.append(str(err))
        except Exception as err:  # PDF corupt etc.
            erori.append(f"PDF ilizibil: {err}")

    if not facturi:
        body = msg.get_body(preferencelist=("plain", "html"))
        text = ""
        if body is not None:
            try:
                text = body.get_content()
            except (LookupError, UnicodeDecodeError):
                text = ""
        prov = parse_body(text, primit)
        if prov:
            facturi.append(prov)
        else:
            erori.append("nici PDF, nici sumă în text")
    return Mesaj(uid, primit, facturi, erori)


class ApaIlfovClient:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        sender: str,
        folder: str = "INBOX",
        imap_factory: Callable[[str, int], imaplib.IMAP4] | None = None,
    ) -> None:
        self._host, self._port = host, port
        self._user, self._password = user, password
        self._sender, self._folder = sender, folder
        self._factory = imap_factory or (lambda h, p: imaplib.IMAP4_SSL(h, p, timeout=30))

    def _connect(self) -> imaplib.IMAP4:
        try:
            imap = self._factory(self._host, self._port)
        except (OSError, imaplib.IMAP4.error) as err:
            raise ConnectError(str(err)) from err
        try:
            imap.login(self._user, self._password)
        except imaplib.IMAP4.error as err:
            try:
                imap.shutdown()
            except Exception:  # noqa: BLE001
                pass
            raise AuthError(str(err)) from err
        return imap

    def test(self) -> None:
        imap = self._connect()
        try:
            typ, _ = imap.select(self._folder, readonly=True)
            if typ != "OK":
                raise ConnectError(f"folderul {self._folder} nu există")
        finally:
            _inchide(imap)

    def fetch(self, state: dict) -> tuple[list[Mesaj], dict]:
        """Citește mesajele noi (UID > last_uid). Nu marchează nimic ca citit."""
        imap = self._connect()
        try:
            typ, _ = imap.select(self._folder, readonly=True)
            if typ != "OK":
                raise ConnectError(f"folderul {self._folder} nu există")
            validity = _uidvalidity(imap)
            last_uid = int(state.get("last_uid", 0))
            if state.get("uidvalidity") not in (None, validity):
                last_uid = 0  # căsuța a fost renumerotată: reiau tot
            typ, data = imap.uid("SEARCH", None, "FROM", f'"{self._sender}"')
            if typ != "OK":
                raise ConnectError("căutarea IMAP a eșuat")
            uids = sorted(int(x) for x in (data[0] or b"").split())
            noi = [u for u in uids if u > last_uid]
            mesaje: list[Mesaj] = []
            for uid in noi:
                typ, parts = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
                raw = _raw(parts)
                if typ != "OK" or raw is None:
                    _LOGGER.warning("Nu am putut citi mesajul UID %s", uid)
                    continue
                mesaje.append(proceseaza_mesaj(uid, raw))
            new_state = {
                "uidvalidity": validity,
                "last_uid": max([last_uid, *noi]) if noi else last_uid,
            }
            return mesaje, new_state
        except imaplib.IMAP4.error as err:
            raise ConnectError(str(err)) from err
        finally:
            _inchide(imap)


def _uidvalidity(imap: imaplib.IMAP4) -> int | None:
    try:
        typ, data = imap.response("UIDVALIDITY")
        if data and data[0]:
            return int(data[0])
    except Exception:  # noqa: BLE001
        pass
    return None


def _raw(parts) -> bytes | None:
    for p in parts or []:
        if isinstance(p, tuple) and len(p) >= 2 and isinstance(p[1], (bytes, bytearray)):
            return bytes(p[1])
    return None


def _inchide(imap: imaplib.IMAP4) -> None:
    try:
        imap.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        imap.logout()
    except Exception:  # noqa: BLE001
        pass


_ = re  # păstrat pentru extinderi viitoare (filtrare subiect)
