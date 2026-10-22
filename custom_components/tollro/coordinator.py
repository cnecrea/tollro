"""DataUpdateCoordinator pentru CNAIR eToll (TollRo)."""

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TollRoApiClient, TollRoAuthError, TollRoError
from homeassistant.util import dt as dt_util

from .const import (
    ARCHIVE_YEARS,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HISTORY_TOLL_STATUSES,
    LICENSE_DATA_KEY,
    TOLL_STATUS_ACTIVE,
    TOLL_VIGNETTE,
)
from .helpers import parse_dt, payments_by_year, spending_by_vehicle

_LOGGER = logging.getLogger(__name__)


class TollRoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Adună periodic datele contului eToll (doar citire)."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: TollRoApiClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.entry = entry
        self.client = client
        self._country_names: dict[str, str] | None = None

    async def _async_country_names(self) -> dict[str, str]:
        """Cod ISO → numele țării în limba Home Assistant (încărcat o singură dată)."""
        if self._country_names is not None:
            return self._country_names
        language = "ro" if (self.hass.config.language or "").startswith("ro") else "en"
        try:
            countries = await self.client.async_get_countries()
        except TollRoError as err:
            _LOGGER.debug("Nomenclatorul de țări nu a putut fi încărcat: %s", err)
            return {}
        self._country_names = {
            c["countryCode"]: c.get(language) or c.get("en") or c["countryCode"]
            for c in countries
            if c.get("countryCode")
        }
        # API-ul trimite "Romania" fără diacritice în câmpul `ro` (lista din aplicație are „România”)
        if language == "ro" and "RO" in self._country_names:
            self._country_names["RO"] = "România"
        _LOGGER.debug("Nomenclator de țări încărcat: %d țări (%s)", len(self._country_names), language)
        return self._country_names

    async def _async_history_tolls(self, tolls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Completează lista cu serviciile expirate și consumate (unite după `id`).

        Nu e verificat dacă lista nefiltrată le include; filtrul pe status e verificat.
        O eroare aici nu oprește actualizarea: totalurile se calculează din ce avem.
        """
        merged = {t.get("id"): t for t in tolls if t.get("id")}
        for status in HISTORY_TOLL_STATUSES:
            try:
                extra = await self.client.async_get_tolls(status=status)
            except TollRoAuthError:
                raise
            except TollRoError as err:
                _LOGGER.debug("Serviciile cu status %s nu au putut fi citite: %s", status, err)
                continue
            new = [t for t in extra if t.get("id") and t["id"] not in merged]
            merged.update({t["id"]: t for t in new})
            _LOGGER.debug("Servicii cu status %s: %d (dintre care %d noi)", status, len(extra), len(new))
        return list(merged.values())

    async def _async_update_data(self) -> dict[str, Any]:
        # Fără licență/trial valid nu se fac apeluri către eToll
        license_mgr = self.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        if license_mgr and not license_mgr.is_valid:
            _LOGGER.debug("Licență invalidă — se omit apelurile către eToll")
            return self.data or {}

        started = time.monotonic()
        current_year = dt_util.now().year
        # Interval verificat pe server (format yyyy-MM-dd); capătul `to` e anul următor,
        # ca să nu depindem de faptul (neverificat) că `to` ar fi inclusiv.
        invoices_from = f"{current_year - ARCHIVE_YEARS + 1}-01-01"
        invoices_to = f"{current_year + 1}-01-01"
        try:
            profiles = await self.client.async_get_profiles()
            vehicles = await self.client.async_get_vehicles()
            tolls = await self._async_history_tolls(await self.client.async_get_tolls())
            invoices = await self.client.async_get_invoices(invoices_from, invoices_to)
            notifications = await self.client.async_get_notifications_count()
            session = await self.client.async_get_current_session()
        except TollRoAuthError as err:
            raise ConfigEntryAuthFailed(f"Autentificarea la eToll a eșuat: {err}") from err
        except TollRoError as err:
            raise UpdateFailed(f"Datele eToll nu au putut fi actualizate: {err}") from err

        # Pagina publică de status e auxiliară: o eroare aici nu oprește restul actualizării.
        try:
            service_status = await self.client.async_get_service_status()
        except TollRoError as err:
            _LOGGER.debug("Starea serviciului nu a putut fi citită: %s", err)
            service_status = {}

        country_names = await self._async_country_names()
        self._persist_tokens()

        tolls_by_vehicle: dict[str, list[dict[str, Any]]] = {}
        for toll in tolls:
            vid = (toll.get("vehicle") or {}).get("id")
            if vid:
                tolls_by_vehicle.setdefault(vid, []).append(toll)

        current_profile = next((p for p in profiles if p.get("isCurrent")), None)
        data = {
            "profile": current_profile or (profiles[0] if profiles else {}),
            "vehicles": vehicles,
            "tolls_by_vehicle": tolls_by_vehicle,
            "vignette_by_vehicle": {
                vid: _pick_vignette(items) for vid, items in tolls_by_vehicle.items()
            },
            "invoices": invoices,
            "notifications_count": notifications,
            "service_status": service_status,
            "session": session,
            "country_names": country_names,
            "current_year": current_year,
            "spending_by_vehicle": spending_by_vehicle(tolls, current_year),
            "payments": payments_by_year(invoices, current_year),
        }
        _LOGGER.debug(
            "Actualizare eToll în %.1f s: %d vehicule, %d servicii, %d facturi, "
            "%d notificări necitite, sesiune per km activă: %s; plătit în %d: %.2f lei",
            time.monotonic() - started,
            len(vehicles),
            len(tolls),
            len(invoices),
            notifications,
            "da" if session else "nu",
            current_year,
            data["payments"]["current_year"]["total"],
        )
        return data

    def _persist_tokens(self) -> None:
        """Salvează în config entry tokenurile reîmprospătate, ca să supraviețuiască unui restart."""
        new = {
            CONF_ACCESS_TOKEN: self.client.access_token,
            CONF_REFRESH_TOKEN: self.client.refresh_token,
        }
        if all(self.entry.data.get(k) == v for k, v in new.items()):
            return
        self.hass.config_entries.async_update_entry(self.entry, data={**self.entry.data, **new})
        _LOGGER.debug("Tokenurile reîmprospătate au fost salvate în configurație")


def _pick_vignette(tolls: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Rovinieta relevantă a unui vehicul: cea activă cu valabilitatea cea mai lungă,
    altfel cea mai recentă (după data de sfârșit)."""
    vignettes = [t for t in tolls if t.get("type") == TOLL_VIGNETTE]
    if not vignettes:
        return None
    active = [t for t in vignettes if t.get("status") == TOLL_STATUS_ACTIVE]
    pool = active or vignettes

    def _end(toll: dict[str, Any]) -> float:
        moment = parse_dt(toll.get("validUntil"))
        return moment.timestamp() if moment else 0.0

    return max(pool, key=_end)
