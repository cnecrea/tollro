"""Utilitare pentru integrarea CNAIR eToll (TollRo)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.util import dt as dt_util

from .const import (
    ARCHIVE_YEARS,
    EXCLUDED_SPENDING_STATUSES,
    TOLL_STATUS_ACTIVE,
    VEHICLE_TYPE_CAR,
    VIGNETTE_CATEGORIES,
)

# Datele eToll sunt în ora României (serverul le trimite cu offset +02:00 / +03:00)
RO_TZ = ZoneInfo("Europe/Bucharest")


def enum_key(value: Any) -> str | None:
    """Transformă o valoare de enum din API (ex. "TWELVE_MONTHS", "Electric") într-o cheie
    de traducere Home Assistant (ex. "twelve_months", "electric")."""
    if value is None:
        return None
    text = str(value).strip()
    return text.lower() if text else None


def _in_romania(moment: datetime) -> datetime:
    """Momentul exprimat în ora României (o dată fără fus orar e considerată deja ora României)."""
    return moment.astimezone(RO_TZ) if moment.tzinfo else moment


def days_until(moment: datetime | None) -> int | None:
    """Câte zile calendaristice mai sunt până la `moment` (negativ dacă a trecut).

    Ziua se socotește în ora României, nu în fusul Home Assistant: rovinieta expiră la
    sfârșitul zilei, ora României.
    """
    if moment is None:
        return None
    today = dt_util.now().astimezone(RO_TZ).date()
    return (_in_romania(moment).date() - today).days


def ro_format(value: Any, *, with_time: bool = True) -> str | None:
    """Dată în format românesc, în ora României: „29/05/2027 23:59” (sau „29/05/2027”).

    Text gata formatat, ca să arate la fel indiferent de limba, profilul sau fusul orar al
    instalației Home Assistant (un senzor de tip dată e formatat de HA după profil, iar un
    șir ISO din atribute e afișat de HA în fusul instalației).
    """
    moment = value if isinstance(value, datetime) else parse_dt(value)
    if moment is None:
        return None
    return _in_romania(moment).strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")


def parse_dt(value: Any) -> datetime | None:
    """Parsează o dată ISO-8601 (ex. 2027-10-10T23:59:59.000+03:00) în datetime aware."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def mask(value: Any, keep: int = 2) -> Any:
    """Maschează un identificator, păstrând ultimele `keep` caractere (pentru diagnostics)."""
    if not isinstance(value, str) or len(value) <= keep:
        return value
    return "***" + value[-keep:]


def vignette_applicable(vehicle: dict[str, Any]) -> bool:
    """Rovinieta se aplică autovehiculelor din categoriile A–D.

    Categoriile I, II și III plătesc tariful per km și nu au rovinietă (mesaj oficial
    din aplicația TollRo); remorcile nu au rovinietă proprie.
    """
    category = enum_key(vehicle.get("category"))
    vehicle_type = vehicle.get("vehicleType")
    if vehicle_type and vehicle_type != VEHICLE_TYPE_CAR:
        return False
    return category is None or category in VIGNETTE_CATEGORIES


def vignette_expiry(vehicle: dict[str, Any], toll: dict[str, Any] | None) -> datetime | None:
    """Data de expirare a rovinietei curente.

    Sursa principală e `vignetteEligibility.expirationDateCurrentVignette` de pe vehicul:
    există și pentru roviniete care nu apar în lista de servicii a contului (ex. vehiculul
    înmatriculat în Spania din contul de test). Rezerva e `validUntil` al rovinietei active.
    """
    eligibility = vehicle.get("vignetteEligibility") or {}
    moment = parse_dt(eligibility.get("expirationDateCurrentVignette"))
    if moment is None and toll and toll.get("status") == TOLL_STATUS_ACTIVE:
        moment = parse_dt(toll.get("validUntil"))
    return moment


def vehicle_label(vehicle: dict[str, Any]) -> str:
    """Etichetă lizibilă pentru un vehicul (numărul de înmatriculare, altfel id scurtat)."""
    plate = vehicle.get("plateNumber")
    if plate:
        return str(plate)
    vid = vehicle.get("id") or ""
    return f"vehicul {vid[:8]}" if vid else "vehicul"


# ─────────────────────────── Cheltuieli și plăți pe ani ───────────────────────────


def _local_year(value: Any) -> int | None:
    moment = parse_dt(value)
    return dt_util.as_local(moment).year if moment else None


def _fill_years(totals: dict[int, float], current_year: int) -> dict[str, float]:
    """Totaluri pe ani, de la primul an cu date (cel mult ARCHIVE_YEARS în urmă) până azi."""
    first_allowed = current_year - ARCHIVE_YEARS + 1
    start = max(first_allowed, min(totals)) if totals else current_year
    return {str(year): round(totals.get(year, 0.0), 2) for year in range(start, current_year + 1)}


def _latest(values: list[str]) -> str | None:
    """Cea mai recentă dată dintr-o listă de date ISO (comparată ca moment, nu ca text)."""
    dated = [(parse_dt(v), v) for v in values if parse_dt(v)]
    return max(dated, key=lambda pair: pair[0])[1] if dated else None


def empty_spending(current_year: int) -> dict[str, Any]:
    return {
        "yearly_totals": {str(current_year): 0.0},
        "current_year": {"total": 0.0, "by_type": {}, "count": 0, "last_purchase": None},
    }


def spending_by_vehicle(tolls: list[dict[str, Any]], current_year: int) -> dict[str, dict[str, Any]]:
    """Cheltuielile fiecărui vehicul, din serviciile cumpărate pentru el.

    Sursa e lista de servicii (prețul fiecărui serviciu e atribuit direct vehiculului; o
    factură de coș poate cuprinde mai multe vehicule). Anul e cel al datei de achiziție.
    Ciornele, serviciile anulate și cele restituite nu sunt bani cheltuiți.
    """
    first_allowed = current_year - ARCHIVE_YEARS + 1
    per_vehicle: dict[str, dict[str, Any]] = {}
    for toll in tolls:
        if toll.get("status") in EXCLUDED_SPENDING_STATUSES:
            continue
        vehicle_id = (toll.get("vehicle") or {}).get("id")
        amount = (toll.get("price") or {}).get("totalPrice")
        purchased = toll.get("purchasedAt") or toll.get("validFrom")
        year = _local_year(purchased)
        if not vehicle_id or amount is None or year is None:
            continue
        if not first_allowed <= year <= current_year:
            continue
        bucket = per_vehicle.setdefault(vehicle_id, {"totals": {}, "by_type": {}, "count": 0, "dates": []})
        bucket["totals"][year] = bucket["totals"].get(year, 0.0) + float(amount)
        if year == current_year:
            toll_type = toll.get("type") or "OTHER"
            bucket["by_type"][toll_type] = bucket["by_type"].get(toll_type, 0.0) + float(amount)
            bucket["count"] += 1
            bucket["dates"].append(purchased)

    return {
        vehicle_id: {
            "yearly_totals": _fill_years(b["totals"], current_year),
            "current_year": {
                "total": round(b["totals"].get(current_year, 0.0), 2),
                "by_type": {k: round(v, 2) for k, v in b["by_type"].items()},
                "count": b["count"],
                "last_purchase": _latest(b["dates"]),
            },
        }
        for vehicle_id, b in per_vehicle.items()
    }


def payments_by_year(invoices: list[dict[str, Any]], current_year: int) -> dict[str, Any]:
    """Banii plătiți efectiv, din facturi, grupați pe anul datei de plată (calcul local)."""
    first_allowed = current_year - ARCHIVE_YEARS + 1
    totals: dict[int, float] = {}
    current = {"total": 0.0, "count": 0, "without_vat": 0.0, "vat": 0.0, "dates": []}
    for invoice in invoices:
        total = invoice.get("total") or {}
        amount = total.get("totalPrice")
        year = _local_year(invoice.get("paymentDate"))
        if amount is None or year is None or not first_allowed <= year <= current_year:
            continue
        totals[year] = totals.get(year, 0.0) + float(amount)
        if year == current_year:
            current["total"] += float(amount)
            current["count"] += 1
            current["without_vat"] += float(total.get("priceWithoutVat") or 0.0)
            current["vat"] += float(total.get("vat") or 0.0)
            current["dates"].append(invoice.get("paymentDate"))
    return {
        "yearly_totals": _fill_years(totals, current_year),
        "current_year": {
            "total": round(current["total"], 2),
            "count": current["count"],
            "without_vat": round(current["without_vat"], 2),
            "vat": round(current["vat"], 2),
            "last_payment": _latest(current["dates"]),
        },
    }


# ─────────────────────────── Atribute ───────────────────────────


def clean_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
    """Atributele fără valoare nu se afișează (în loc de un „None” fără sens în UI)."""
    return {key: value for key, value in attrs.items() if value is not None}


def vehicle_details(vehicle: dict[str, Any], country_names: dict[str, str] | None) -> dict[str, Any]:
    """Datele de identificare ale vehiculului, ca atribute ale senzorului „Datele vehiculului”."""
    mtma = vehicle.get("mtma")
    if isinstance(mtma, float) and mtma.is_integer():
        mtma = int(mtma)
    country_code = vehicle.get("countryCode")
    return clean_attributes(
        {
            "plate_number": vehicle.get("plateNumber"),
            "vin": vehicle.get("vin"),
            "registration_certificate": vehicle.get("registrationSerial"),
            "vehicle_type": enum_key(vehicle.get("vehicleType")),
            "emission_standard": enum_key(vehicle.get("emissionStandard")),
            "registration_country": (country_names or {}).get(country_code) or vehicle.get("country"),
            # MTMA 0 înseamnă „nedeclarată” (ex. vehiculul înmatriculat în Spania), nu 0 kg
            "max_authorised_mass": mtma or None,
            "bridge_toll_category": vehicle.get("strrPeajCategoryCode"),
            "temporary_plate": vehicle.get("temporaryPlate"),
            "favorite": vehicle.get("favorite"),
        }
    )
