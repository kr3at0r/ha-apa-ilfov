"""Coordinator: citește e-mailurile, ține istoricul facturilor și anunță facturile noi."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ApaIlfovClient, AuthError, ConnectError
from .const import (
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SENDER,
    CONF_SERVER,
    CONF_USERNAME,
    DEFAULT_FOLDER,
    DEFAULT_SCAN_MINUTES,
    DOMAIN,
    EVENT_NEW_INVOICE,
    OPT_FOLDER,
    OPT_ONLY_SEWER,
    OPT_SCAN_MINUTES,
    STORAGE_VERSION,
)
from .parser import Factura

PARSER_VERSION = 2  # crește când se schimbă regulile de parsare: se reciti tot istoricul

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass
class ApaData:
    istoric: list[Factura] = field(default_factory=list)  # PDF, cu canal (dacă e setat), sortate
    ultima: Factura | None = None  # ultima factură de orice fel (inclusiv provizorie)
    de_verificat: list[Factura] = field(default_factory=list)
    ignorate: int = 0


class ApaIlfovCoordinator(DataUpdateCoordinator[ApaData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        minutes = int(entry.options.get(OPT_SCAN_MINUTES, DEFAULT_SCAN_MINUTES))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(minutes=max(15, minutes)),
        )
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._state: dict = {}
        self._facturi: dict[str, Factura] = {}
        self._init_done = False
        self._reindex = False
        self._client = ApaIlfovClient(
            entry.data[CONF_SERVER],
            int(entry.data[CONF_PORT]),
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            entry.data[CONF_SENDER],
            folder=entry.options.get(OPT_FOLDER, DEFAULT_FOLDER),
        )

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        if data.get("parser_version") != PARSER_VERSION:
            # reguli noi de parsare: reiau citirea tuturor mailurilor (fără notificări)
            self._reindex = bool(data)
            data = {"init_done": bool(data.get("init_done"))}
        self._state = data.get("state", {})
        self._init_done = bool(data.get("init_done"))
        for k, v in data.get("facturi", {}).items():
            try:
                self._facturi[k] = Factura.from_dict(v)
            except TypeError:
                _LOGGER.warning("Factură salvată ilizibilă (%s), o ignor", k)

    async def _save(self) -> None:
        await self._store.async_save(
            {
                "state": self._state,
                "init_done": self._init_done,
                "parser_version": PARSER_VERSION,
                "facturi": {k: v.to_dict() for k, v in self._facturi.items()},
            }
        )

    async def _async_update_data(self) -> ApaData:
        try:
            mesaje, new_state = await self.hass.async_add_executor_job(
                self._client.fetch, self._state
            )
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ConnectError as err:
            raise UpdateFailed(f"Nu mă pot conecta la e-mail: {err}") from err

        noi: list[Factura] = []
        for msg in mesaje:
            for err_txt in msg.erori:
                _LOGGER.debug("Mesaj UID %s ignorat: %s", msg.uid, err_txt)
            for f in msg.facturi:
                if self._adauga(f):
                    noi.append(f)

        self._state = new_state
        first_run = not self._init_done or self._reindex
        self._init_done = True
        self._reindex = False
        if mesaje or first_run:
            await self._save()

        if not first_run:
            for f in noi:
                self._anunta(f)
        return self._calculeaza()

    def _adauga(self, f: Factura) -> bool:
        """Returnează True dacă e o factură nouă (nu doar o înlocuire de provizorie)."""
        if f.sursa == "pdf":
            # PDF-ul înlocuiește varianta provizorie (doar din text) cu același total/dată
            for k, old in list(self._facturi.items()):
                if old.sursa == "mail" and abs(old.total - f.total) < 0.01 and old.emisa == f.emisa:
                    del self._facturi[k]
                    self._facturi[f.cheie] = f
                    return False
        if f.cheie in self._facturi:
            self._facturi[f.cheie] = f
            return False
        self._facturi[f.cheie] = f
        return True

    def _anunta(self, f: Factura) -> None:
        self.hass.bus.async_fire(
            EVENT_NEW_INVOICE,
            {
                "total": f.total,
                "scadenta": f.scadenta,
                "emisa": f.emisa,
                "perioada": f.perioada if f.luna else None,
                "serie_numar": f.cheie if f.sursa == "pdf" else None,
                "consum_apa": f.apa.cantitate if f.apa else None,
                "consum_canal": f.canal.cantitate if f.canal else None,
                "index_apa": f.apa.index_nou if f.apa else None,
                "tip_citire": f.apa.tip if f.apa else None,
                "provizorie": f.sursa != "pdf",
                "de_verificat": bool(f.avertismente) and f.sursa == "pdf",
                "avertismente": f.avertismente,
            },
        )

    def _calculeaza(self) -> ApaData:
        doar_canal = bool(self.config_entry.options.get(OPT_ONLY_SEWER, True))
        pdfs = [f for f in self._facturi.values() if f.sursa == "pdf"]
        istoric = [f for f in pdfs if (f.canal is not None or not doar_canal)]
        istoric.sort(key=lambda f: (f.an, f.luna))
        ignorate = len(pdfs) - len(istoric)

        candidati = istoric + [f for f in self._facturi.values() if f.sursa == "mail"]
        ultima = max(candidati, key=lambda f: (f.emisa or "", f.sursa == "pdf"), default=None)
        # o provizorie veche, înlocuită deja de PDF, nu mai există; una mai veche decât
        # ultima factură cu PDF nu are sens să rămână "ultima"
        de_verificat = [f for f in istoric if f.avertismente]
        return ApaData(istoric=istoric, ultima=ultima, de_verificat=de_verificat, ignorate=ignorate)
