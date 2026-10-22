"""Constante pentru integrarea CNAIR eToll (TollRo)."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "tollro"
NAME = "CNAIR eToll"
MANUFACTURER = "CNAIR eToll"

# ── Endpointuri (confirmate prin analiză + debug, vezi tollro.md §10–§11, §20.1) ──
API_BASE = "https://portal.etoll.ro/api/"
STATUS_BASE = "https://portal.etoll.ro/status/api/"
SSO_REALM = "https://sso.etoll.ro/auth/realms/external"
TOKEN_ENDPOINT = f"{SSO_REALM}/protocol/openid-connect/token"
CLIENT_ID = "ddcm-authz-client"
SCOPE = "openid profile offline_access"

API_HOST = "portal.etoll.ro"
SSO_HOST = "sso.etoll.ro"

# Componenta de status pentru aplicația mobilă (endpoint public, fără auth)
STATUS_COMPONENT_ID = 3

# ── Licențiere (STANDARD-LICENTA.md) ──
CONF_LICENSE_KEY = "license_key"
LICENSE_DATA_KEY = "tollro_license_manager"
LICENSE_PURCHASE_URL = "https://hubinteligent.org/donate?ref=tollro"

# ── Config entry ──
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"

# ── Rețea / actualizare ──
DEFAULT_TIMEOUT = 15
DEFAULT_SCAN_INTERVAL = timedelta(minutes=30)
# Access token-ul expiră la 30 min (confirmat §20.1) → reîmprospătare proactivă
TOKEN_REFRESH_MARGIN = timedelta(minutes=5)

# ── Platforme ──
PLATFORMS = ["sensor", "binary_sensor"]

# ── Tipuri de servicii (TollType) ──
TOLL_VIGNETTE = "VIGNETTE"
TOLL_BRIDGE = "BRIDGE"
TOLL_ROUTE = "ROUTE"
TOLL_PER_KM = "PER_KM"

TOLL_STATUS_ACTIVE = "ACTIVE"
VEHICLE_TYPE_CAR = "CAR"

# ── Cheltuieli și arhivă ──
# Câți ani (inclusiv anul curent) se păstrează în totalurile pe ani
ARCHIVE_YEARS = 5
# Statusuri cerute explicit pe lângă lista nefiltrată: nu e verificat dacă lista
# nefiltrată include și serviciile vechi (tollro.md §20.1, verificările pentru arhivă)
HISTORY_TOLL_STATUSES = ("EXPIRED", "CONSUMED")
# Servicii care nu reprezintă bani cheltuiți: ciorne neplătite, anulate, restituite
EXCLUDED_SPENDING_STATUSES = {"DRAFT", "CANCELLED", "REFUNDED"}
# Tipurile de servicii cumpărate per vehicul și cheia atributului corespunzător
SPENDING_TYPE_ATTRS = {
    "VIGNETTE": "vignette_amount",
    "BRIDGE": "bridge_amount",
    "ROUTE": "route_amount",
}

# ── Valori enum expuse în Home Assistant (chei de traducere, litere mici) ──
# Categoriile oficiale STRR (etichete din aplicația TollRo, vezi tollro.md §16.1)
VEHICLE_CATEGORIES = ["a", "b", "c", "d", "i", "ii", "iii"]
# Categoriile I, II, III plătesc tariful per km și nu au rovinietă (mesaj oficial din aplicație)
VIGNETTE_CATEGORIES = {"a", "b", "c", "d"}

# Starea componentei de pe pagina de status (format Cachet: 1 = funcțional)
SERVICE_STATUS_BY_VALUE = {
    1: "operational",
    2: "performance_issues",
    3: "partial_outage",
    4: "major_outage",
}
SERVICE_STATUS_OPTIONS = [
    "operational",
    "performance_issues",
    "partial_outage",
    "major_outage",
    "unknown",
]
