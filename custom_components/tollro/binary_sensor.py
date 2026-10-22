"""Senzori binari pentru CNAIR eToll (TollRo).

Stările on/off au traduceri proprii (ex. „Valabilă” / „Nevalabilă”), ca să nu apară
„Pornit” / „Oprit” acolo unde n-ar avea sens.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import TollRoConfigEntry
from .coordinator import TollRoCoordinator
from .entity import find_vehicle, license_valid, remove_entities_without_license, vehicle_device
from .helpers import vehicle_details, vignette_applicable, vignette_expiry


class TollRoBinarySensor(CoordinatorEntity[TollRoCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    @property
    def available(self) -> bool:
        # Licența verificată în timp real (vezi TollRoSensor.available)
        return super().available and license_valid(self.hass)


class TollRoVehicleBinarySensor(TollRoBinarySensor):
    def __init__(
        self, coordinator: TollRoCoordinator, vehicle_id: str, unique_suffix: str, translation_key: str
    ) -> None:
        super().__init__(coordinator)
        self._vehicle_id = vehicle_id
        self._attr_unique_id = f"{vehicle_id}_{unique_suffix}"
        self._attr_translation_key = translation_key

    @property
    def _vehicle(self) -> dict[str, Any]:
        return find_vehicle(self.coordinator.data, self._vehicle_id)

    @property
    def device_info(self) -> DeviceInfo:
        return vehicle_device(self._vehicle, self._vehicle_id)

    @property
    def available(self) -> bool:
        return super().available and bool(self._vehicle)


class VehicleDataBinarySensor(TollRoVehicleBinarySensor):
    """Datele vehiculului: dacă sunt valide (`isValid`) și, ca atribute, datele de identificare
    (număr, VIN, certificat, tip, normă de poluare, țară, MTMA, categorie pentru poduri)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:card-account-details-outline"

    def __init__(self, coordinator: TollRoCoordinator, vehicle_id: str) -> None:
        # sufixul „valid” e păstrat ca să nu apară o entitate nouă față de v0.1
        super().__init__(coordinator, vehicle_id, "valid", "vehicle_data")

    @property
    def is_on(self) -> bool | None:
        is_valid = self._vehicle.get("isValid")
        return None if is_valid is None else not is_valid

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return vehicle_details(self._vehicle, self.coordinator.data.get("country_names"))


class VignetteValidBinarySensor(TollRoVehicleBinarySensor):
    """Dacă vehiculul are în acest moment o rovinietă valabilă."""

    def __init__(self, coordinator: TollRoCoordinator, vehicle_id: str) -> None:
        super().__init__(coordinator, vehicle_id, "vignette_valid", "vignette_valid")

    @property
    def is_on(self) -> bool:
        vignette = (self.coordinator.data.get("vignette_by_vehicle") or {}).get(self._vehicle_id)
        expiry = vignette_expiry(self._vehicle, vignette)
        return expiry is not None and expiry > dt_util.now()

    @property
    def icon(self) -> str:
        return "mdi:check-decagram" if self.is_on else "mdi:alert-decagram-outline"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TollRoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if not license_valid(hass):
        # Licență invalidă: senzorii binari ies din registry; „Licență necesară” e în sensor.py
        remove_entities_without_license(hass, entry.entry_id, "binary_sensor")
        return

    coordinator = entry.runtime_data
    entities: list[TollRoBinarySensor] = []
    for vehicle in (coordinator.data or {}).get("vehicles") or []:
        vehicle_id = vehicle.get("id")
        if not vehicle_id:
            continue
        entities.append(VehicleDataBinarySensor(coordinator, vehicle_id))
        if vignette_applicable(vehicle):
            entities.append(VignetteValidBinarySensor(coordinator, vehicle_id))
    async_add_entities(entities)
