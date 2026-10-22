"""Diagnostics pentru CNAIR eToll (TollRo)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import TollRoConfigEntry
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_USERNAME,
    DOMAIN,
    LICENSE_DATA_KEY,
)

# Câmpuri sensibile (credențiale, tokenuri, date personale)
TO_REDACT = {
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    "plateNumber",
    "vin",
    "cnp",
    "email",
    "firstName",
    "lastName",
    "name",
    "buyerName",
    "fullAddress",
    "street",
    "phoneNo",
    "number",
    "sub",
    "lat",
    "lon",
    "startLocation",
    "endLocation",
    "lastLocation",
    "gpsLocation",
    "sub",
    "serialNo",
    "externalId",
    "registrationSerial",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TollRoConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    license_mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    # as_dict(): fingerprint trunchiat, cheie mascată — fără secrete
    license_info = license_mgr.as_dict() if license_mgr else {"status": "indisponibil"}
    data = dict(coordinator.data or {})
    country_names = data.pop("country_names", None) or {}
    client = coordinator.client
    return {
        "summary": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_s": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
            "vehicles": len(data.get("vehicles") or []),
            "vehicles_with_tolls": len(data.get("tolls_by_vehicle") or {}),
            "invoices": len(data.get("invoices") or []),
            "unread_notifications": data.get("notifications_count"),
            "active_session": bool(data.get("session")),
            "countries_loaded": len(country_names),
            # doar prezența tokenurilor, niciodată valorile
            "has_access_token": bool(client.access_token),
            "has_refresh_token": bool(client.refresh_token),
        },
        "license": license_info,
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "data": async_redact_data(data, TO_REDACT),
    }
