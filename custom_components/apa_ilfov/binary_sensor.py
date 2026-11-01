"""Senzor binar: factură de verificat."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([FacturaDeVerificat(entry.runtime_data, entry)])


class FacturaDeVerificat(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "factura_de_verificat"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_de_verificat"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Apă Ilfov",
            manufacturer="Apa-Canal Ilfov",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.de_verificat)

    @property
    def extra_state_attributes(self):
        return {
            "facturi": [
                {"serie_numar": f.cheie, "perioada": f.perioada, "motive": f.avertismente}
                for f in self.coordinator.data.de_verificat
            ]
        }
