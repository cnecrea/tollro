"""Senzori pentru CNAIR eToll (TollRo).

Valorile de tip enum din API sunt expuse ca chei cu litere mici (ex. `twelve_months`),
traduse în `translations/*.json` → atât starea, cât și atributele apar lizibil în UI.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TollRoConfigEntry
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    LICENSE_DATA_KEY,
    SERVICE_STATUS_BY_VALUE,
    SERVICE_STATUS_OPTIONS,
    SPENDING_TYPE_ATTRS,
    VEHICLE_CATEGORIES,
)
from .coordinator import TollRoCoordinator
from .entity import (
    account_device,
    find_vehicle,
    license_sensor_unique_id,
    license_valid,
    remove_entities_without_license,
    vehicle_device,
)
from .helpers import (
    clean_attributes as _clean,
    days_until,
    empty_spending,
    enum_key,
    parse_dt,
    ro_format,
    vignette_applicable,
    vignette_expiry,
)


def _start_of_year(year: int) -> datetime:
    """1 ianuarie, ora 00:00 local — momentul de resetare al totalurilor anuale."""
    return dt_util.start_of_local_day(date(year, 1, 1))


class TollRoSensor(CoordinatorEntity[TollRoCoordinator], SensorEntity):
    """Bază comună."""

    _attr_has_entity_name = True

    @property
    def available(self) -> bool:
        # Licența verificată în timp real: dacă expiră între două reîncărcări,
        # senzorul devine indisponibil (un text în locul unei valori numerice /
        # enum ar da eroare în HA) până când reload-ul pune „Licență necesară”.
        return super().available and license_valid(self.hass)


class LicentaNecesaraSensor(SensorEntity):
    """Apare DOAR când licența nu e validă (STANDARD-LICENTA.md)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:license"

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id
        self._attr_unique_id = license_sensor_unique_id(entry_id)
        self._attr_name = "Licență necesară"
        # entity_id explicit, ca la celelalte integrări (litere mici: entry_id e un ULID)
        self.entity_id = f"sensor.{DOMAIN}_licenta_{entry_id.lower()}"

    @property
    def device_info(self) -> DeviceInfo:
        # Pe același dispozitiv „cont” ca senzorii normali
        return account_device(self._entry_id)

    @property
    def native_value(self) -> str:
        mgr = self.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        if mgr is not None:
            if mgr.status == "expired":
                return "Licență expirată"
            if mgr.status == "trial":
                days = mgr.trial_days_remaining
                return f"Trial — {days} zile rămase" if days > 0 else "Trial expirat"
        return "Licență necesară"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"nr_identificare": self._entry_id}
        mgr = self.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        if mgr is not None:
            attrs["status_licență"] = mgr.status
            if mgr.status == "trial":
                attrs["zile_trial_rămase"] = mgr.trial_days_remaining
            attrs["informații"] = (
                "Achiziționează o licență de pe hubinteligent.org "
                "sau din Buy Me a Coffee."
            )
        return attrs


# ─────────────────────────────── Senzori de cont ───────────────────────────────


class TollRoAccountSensor(TollRoSensor):
    def __init__(
        self, coordinator: TollRoCoordinator, entry_id: str, unique_suffix: str, translation_key: str
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        self._attr_translation_key = translation_key

    @property
    def device_info(self) -> DeviceInfo:
        return account_device(self._entry_id)


class UnreadNotificationsSensor(TollRoAccountSensor):
    """Numărul notificărilor necitite din aplicația TollRo."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:bell-outline"

    def __init__(self, coordinator: TollRoCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "notifications", "unread_notifications")

    @property
    def native_value(self) -> int:
        return int(self.coordinator.data.get("notifications_count") or 0)

    @property
    def icon(self) -> str:
        return "mdi:bell-badge" if self.native_value else "mdi:bell-outline"


class ServiceStatusSensor(TollRoAccountSensor):
    """Starea serviciului eToll, de pe pagina publică de status CNAIR."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = SERVICE_STATUS_OPTIONS
    _attr_icon = "mdi:server-network"

    def __init__(self, coordinator: TollRoCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "service_status", "service_status")

    @property
    def _status(self) -> dict[str, Any]:
        return self.coordinator.data.get("service_status") or {}

    @property
    def native_value(self) -> str:
        value = (self._status.get("status") or {}).get("value")
        return SERVICE_STATUS_BY_VALUE.get(value, "unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return _clean({"last_updated": ro_format((self._status.get("updated") or {}).get("string"))})


class LatestInvoiceSensor(TollRoAccountSensor):
    """Valoarea celei mai recente facturi (după data plății)."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "RON"
    _attr_icon = "mdi:receipt-text-outline"

    def __init__(self, coordinator: TollRoCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "last_invoice", "latest_invoice")

    @property
    def _invoice(self) -> dict[str, Any] | None:
        invoices = self.coordinator.data.get("invoices") or []
        if not invoices:
            return None

        def _paid(inv: dict[str, Any]) -> float:
            moment = parse_dt(inv.get("paymentDate"))
            return moment.timestamp() if moment else 0.0

        return max(invoices, key=_paid)

    @property
    def native_value(self) -> float | None:
        invoice = self._invoice
        return (invoice.get("total") or {}).get("totalPrice") if invoice else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        invoice = self._invoice
        if not invoice:
            return {}
        total = invoice.get("total") or {}
        types = invoice.get("types") or []
        series = invoice.get("externalSeries") or ""
        number = invoice.get("externalNumber")
        return _clean(
            {
                "invoice_number": f"{series} {number}".strip() if number is not None else series or None,
                "payment_date": ro_format(invoice.get("paymentDate")),
                "payment_method": enum_key(invoice.get("paymentMethod")),
                "billed_service": enum_key(types[0]) if len(types) == 1 else ("multiple" if types else None),
                "amount_without_vat": total.get("priceWithoutVat"),
                "vat_amount": total.get("vat"),
                "vat_rate": total.get("vatPercentage"),
            }
        )


class TotalPaidSensor(TollRoAccountSensor):
    """Banii plătiți efectiv în anul curent, din facturi (inclusiv alimentările per km)."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "RON"
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, coordinator: TollRoCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "payments_year", "total_paid")

    @property
    def _payments(self) -> dict[str, Any]:
        return self.coordinator.data.get("payments") or {}

    @property
    def native_value(self) -> float:
        return (self._payments.get("current_year") or {}).get("total", 0.0)

    @property
    def last_reset(self) -> datetime:
        return _start_of_year(self.coordinator.data.get("current_year") or dt_util.now().year)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        current = self._payments.get("current_year") or {}
        return _clean(
            {
                "invoices_count": current.get("count", 0),
                "amount_without_vat": current.get("without_vat"),
                "vat_amount": current.get("vat"),
                "last_payment": ro_format(current.get("last_payment")),
                "yearly_totals": self._payments.get("yearly_totals"),
            }
        )


# ─────────────────────────────── Senzori per vehicul ───────────────────────────────


class TollRoVehicleSensor(TollRoSensor):
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
        # vehiculul a fost șters din cont → entitatea devine indisponibilă, nu „necunoscută”
        return super().available and bool(self._vehicle)


class VehicleCategorySensor(TollRoVehicleSensor):
    """Categoria de tarifare a vehiculului (A, B, C, D, I, II, III).

    Fără atribute proprii: datele de identificare (număr, VIN, normă de poluare etc.) sunt pe
    senzorul binar „Datele vehiculului”. HA adaugă singur atributul „Stări posibile”.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = VEHICLE_CATEGORIES
    _attr_icon = "mdi:car-info"

    def __init__(self, coordinator: TollRoCoordinator, vehicle_id: str) -> None:
        # sufixul „vehicle_info” e păstrat ca să nu apară o entitate nouă față de v0.1
        super().__init__(coordinator, vehicle_id, "vehicle_info", "vehicle_category")

    @property
    def native_value(self) -> str | None:
        category = enum_key(self._vehicle.get("category"))
        return category if category in VEHICLE_CATEGORIES else None


class VignetteValidUntilSensor(TollRoVehicleSensor):
    """Până când e valabilă rovinieta vehiculului, ca text în format românesc („29/05/2027 23:59”).

    Text, nu `timestamp` sau `date`: un timestamp e afișat de HA relativ („peste 7 luni”) și
    în fusul instalației (23:59 ora României apare 22:59 pe Madrid), iar un `date` e formatat
    după profilul utilizatorului. Ora e întotdeauna ora României. Pentru automatizări:
    atributul „Zile rămase” și senzorul binar „Valabilitate rovinietă”.
    """

    _attr_icon = "mdi:calendar-check"

    def __init__(self, coordinator: TollRoCoordinator, vehicle_id: str) -> None:
        super().__init__(coordinator, vehicle_id, "vignette_expiry", "vignette_valid_until")

    @property
    def _vignette(self) -> dict[str, Any] | None:
        return (self.coordinator.data.get("vignette_by_vehicle") or {}).get(self._vehicle_id)

    @property
    def _expiry(self) -> datetime | None:
        return vignette_expiry(self._vehicle, self._vignette)

    @property
    def native_value(self) -> str | None:
        return ro_format(self._expiry)

    @property
    def icon(self) -> str:
        remaining = days_until(self._expiry)
        if remaining is None or remaining < 0:
            return "mdi:calendar-remove"
        return "mdi:calendar-alert" if remaining <= 30 else "mdi:calendar-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"days_remaining": days_until(self._expiry)}
        vignette = self._vignette
        if vignette:
            attrs.update(
                {
                    # tot o zi, nu un moment: „11/10/2026”
                    "valid_from": ro_format(vignette.get("validFrom"), with_time=False),
                    "validity_period": enum_key(vignette.get("duration")),
                    "vignette_status": enum_key(vignette.get("status")),
                    "price_paid": (vignette.get("price") or {}).get("totalPrice"),
                    "vignette_serial": (vignette.get("issuance") or {}).get("serialNo"),
                    "purchased_at": ro_format(vignette.get("purchasedAt")),
                }
            )
        return _clean(attrs)


class VehicleSpendingSensor(TollRoVehicleSensor):
    """Cât s-a cheltuit pentru vehicul în anul curent (servicii cumpărate pentru el)."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "RON"
    _attr_icon = "mdi:cash-register"

    def __init__(self, coordinator: TollRoCoordinator, vehicle_id: str) -> None:
        super().__init__(coordinator, vehicle_id, "spending_year", "vehicle_spending")

    @property
    def _spending(self) -> dict[str, Any]:
        year = self.coordinator.data.get("current_year") or dt_util.now().year
        return (self.coordinator.data.get("spending_by_vehicle") or {}).get(
            self._vehicle_id
        ) or empty_spending(year)

    @property
    def native_value(self) -> float:
        return self._spending["current_year"]["total"]

    @property
    def last_reset(self) -> datetime:
        return _start_of_year(self.coordinator.data.get("current_year") or dt_util.now().year)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        current = self._spending["current_year"]
        by_type = current.get("by_type") or {}
        attrs: dict[str, Any] = {
            attr: by_type.get(toll_type, 0.0) for toll_type, attr in SPENDING_TYPE_ATTRS.items()
        }
        attrs.update(
            {
                "purchases_count": current.get("count", 0),
                "last_purchase": ro_format(current.get("last_purchase")),
                "yearly_totals": self._spending.get("yearly_totals"),
            }
        )
        return _clean(attrs)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TollRoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Creează senzorii contului și pe cei ai fiecărui vehicul."""
    if not license_valid(hass):
        # Licență invalidă: DOAR „Licență necesară”, senzorii normali ies din registry
        remove_entities_without_license(hass, entry.entry_id, "sensor")
        async_add_entities([LicentaNecesaraSensor(entry.entry_id)])
        return

    # Licență validă: „Licență necesară” rămas dintr-o sesiune anterioară se șterge
    registry = er.async_get(hass)
    orphan = registry.async_get_entity_id("sensor", DOMAIN, license_sensor_unique_id(entry.entry_id))
    if orphan is not None:
        registry.async_remove(orphan)

    coordinator = entry.runtime_data
    entities: list[TollRoSensor] = [
        UnreadNotificationsSensor(coordinator, entry.entry_id),
        ServiceStatusSensor(coordinator, entry.entry_id),
        LatestInvoiceSensor(coordinator, entry.entry_id),
        TotalPaidSensor(coordinator, entry.entry_id),
    ]
    for vehicle in (coordinator.data or {}).get("vehicles") or []:
        vehicle_id = vehicle.get("id")
        if not vehicle_id:
            continue
        entities.append(VehicleCategorySensor(coordinator, vehicle_id))
        entities.append(VehicleSpendingSensor(coordinator, vehicle_id))
        if vignette_applicable(vehicle):
            entities.append(VignetteValidUntilSensor(coordinator, vehicle_id))
    async_add_entities(entities)
