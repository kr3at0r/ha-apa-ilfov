"""Senzori Apă Ilfov."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ApaData, ApaIlfovCoordinator
from .parser import Factura


def _rezumat(f: Factura) -> dict[str, Any]:
    return {
        "perioada": f.perioada,
        "emisa": f.emisa,
        "scadenta": f.scadenta,
        "total": f.total,
        "apa_m3": f.apa.cantitate if f.apa else None,
        "canal_m3": f.canal.cantitate if f.canal else None,
        "apa_lei": round(f.apa.valoare + f.apa.tva, 2) if f.apa else None,
        "canal_lei": round(f.canal.valoare + f.canal.tva, 2) if f.canal else None,
        "pret_apa": f.apa.pret if f.apa else None,
        "pret_canal": f.canal.pret if f.canal else None,
        "index_vechi": f.apa.index_vechi if f.apa else None,
        "index_nou": f.apa.index_nou if f.apa else None,
        "tip_citire": f.apa.tip if f.apa else None,
        "ajustare": f.ajustare,
    }


def _ultima_cu_pdf(d: ApaData) -> Factura | None:
    return d.istoric[-1] if d.istoric else None


def _ultima_scadenta(d: ApaData) -> date | None:
    if d.ultima and d.ultima.scadenta:
        return date.fromisoformat(d.ultima.scadenta)
    return None


def _total_12(d: ApaData) -> float | None:
    if not d.istoric:
        return None
    ultima = d.istoric[-1]
    limita = ultima.an * 12 + ultima.luna - 11
    return round(sum(f.total for f in d.istoric if f.an * 12 + f.luna >= limita), 2)


@dataclass(frozen=True, kw_only=True)
class ApaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[ApaData], Any]
    attrs_fn: Callable[[ApaData], dict[str, Any]] | None = None


SENSORS: tuple[ApaSensorDescription, ...] = (
    ApaSensorDescription(
        key="ultima_factura",
        translation_key="ultima_factura",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="RON",
        suggested_display_precision=2,
        value_fn=lambda d: d.ultima.total if d.ultima else None,
        attrs_fn=lambda d: (
            {
                "serie_numar": d.ultima.cheie if d.ultima and d.ultima.sursa == "pdf" else None,
                "provizorie": bool(d.ultima and d.ultima.sursa != "pdf"),
                "emisa": d.ultima.emisa if d.ultima else None,
                "scadenta": d.ultima.scadenta if d.ultima else None,
                "perioada": d.ultima.perioada if d.ultima and d.ultima.luna else None,
                "facturi": [_rezumat(f) for f in d.istoric],
            }
        ),
    ),
    ApaSensorDescription(
        key="scadenta",
        translation_key="scadenta",
        device_class=SensorDeviceClass.DATE,
        value_fn=_ultima_scadenta,
    ),
    ApaSensorDescription(
        key="index_apometru",
        translation_key="index_apometru",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        value_fn=lambda d: (
            _ultima_cu_pdf(d).apa.index_nou
            if _ultima_cu_pdf(d) and _ultima_cu_pdf(d).apa
            else None
        ),
        attrs_fn=lambda d: {
            "tip_citire": (
                _ultima_cu_pdf(d).apa.tip if _ultima_cu_pdf(d) and _ultima_cu_pdf(d).apa else None
            ),
            "perioada": _ultima_cu_pdf(d).perioada if _ultima_cu_pdf(d) else None,
        },
    ),
    ApaSensorDescription(
        key="consum_apa",
        translation_key="consum_apa",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: (
            _ultima_cu_pdf(d).apa.cantitate
            if _ultima_cu_pdf(d) and _ultima_cu_pdf(d).apa
            else None
        ),
    ),
    ApaSensorDescription(
        key="consum_canal",
        translation_key="consum_canal",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: (
            _ultima_cu_pdf(d).canal.cantitate
            if _ultima_cu_pdf(d) and _ultima_cu_pdf(d).canal
            else None
        ),
    ),
    ApaSensorDescription(
        key="total_12_luni",
        translation_key="total_12_luni",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="RON",
        suggested_display_precision=2,
        value_fn=_total_12,
    ),
    ApaSensorDescription(
        key="numar_facturi",
        translation_key="numar_facturi",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.istoric),
        attrs_fn=lambda d: {"ignorate_fara_canal": d.ignorate},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ApaIlfovCoordinator = entry.runtime_data
    async_add_entities(ApaSensor(coordinator, entry, d) for d in SENSORS)


class ApaSensor(CoordinatorEntity[ApaIlfovCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: ApaSensorDescription

    def __init__(self, coordinator, entry, description: ApaSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Apă Ilfov",
            manufacturer="Apa-Canal Ilfov",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self):
        fn = self.entity_description.attrs_fn
        return fn(self.coordinator.data) if fn else None
