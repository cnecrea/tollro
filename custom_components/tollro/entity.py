"""Elemente comune entităților CNAIR eToll: dispozitivele (cont, vehicule)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, LICENSE_DATA_KEY, MANUFACTURER, NAME
from .helpers import vehicle_label


def license_valid(hass: HomeAssistant) -> bool:
    """Licența (sau trial-ul) e validă acum — verificare în timp real."""
    mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    return bool(mgr and mgr.is_valid)


def license_sensor_unique_id(entry_id: str) -> str:
    return f"{DOMAIN}_licenta_{entry_id}"


def remove_entities_without_license(hass: HomeAssistant, entry_id: str, domain: str) -> None:
    """Licență invalidă: scoate din registry entitățile normale ale platformei."""
    registry = er.async_get(hass)
    keep = license_sensor_unique_id(entry_id)
    for reg in er.async_entries_for_config_entry(registry, entry_id):
        if reg.domain == domain and reg.unique_id != keep:
            registry.async_remove(reg.entity_id)


def account_device(entry_id: str) -> DeviceInfo:
    """Dispozitivul „cont”: notificări, facturi, starea serviciului."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"account_{entry_id}")},
        name=f"{NAME} — Date cont",
        manufacturer=MANUFACTURER,
    )


def vehicle_device(vehicle: dict[str, Any], vehicle_id: str) -> DeviceInfo:
    """Câte un dispozitiv pentru fiecare vehicul; numele e numărul de înmatriculare."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"vehicle_{vehicle_id}")},
        name=f"{NAME} — {vehicle_label(vehicle or {'id': vehicle_id})}",
        manufacturer=MANUFACTURER,
        serial_number=(vehicle or {}).get("vin"),
    )


def find_vehicle(data: dict[str, Any] | None, vehicle_id: str) -> dict[str, Any]:
    for vehicle in (data or {}).get("vehicles") or []:
        if vehicle.get("id") == vehicle_id:
            return vehicle
    return {}
