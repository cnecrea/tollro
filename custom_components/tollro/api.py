"""Client API read-only pentru CNAIR eToll (TollRo).

Portat din logica verificată în debug_etollro.py și tollro.md (§10, §15.5).
Doar GET pe portal.etoll.ro; autentificare la Keycloak (token endpoint).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp
from yarl import URL

from .const import (
    API_BASE,
    API_HOST,
    CLIENT_ID,
    DEFAULT_TIMEOUT,
    SCOPE,
    SSO_HOST,
    STATUS_BASE,
    STATUS_COMPONENT_ID,
    TOKEN_ENDPOINT,
    TOKEN_REFRESH_MARGIN,
)

_LOGGER = logging.getLogger(__name__)

# Santinele interne pentru răspunsuri speciale (nu date reale)
_UNAUTHORIZED = object()
_NOT_FOUND = object()
NOT_FOUND = _NOT_FOUND  # expus pentru apelanți (ex. sesiune inexistentă)


async def _backend_code(resp: aiohttp.ClientResponse) -> str:
    """Codul de eroare din corpul backend-ului ({"message": "COD", ...}), dacă există."""
    try:
        body = await resp.json(content_type=None)
    except (aiohttp.ClientError, ValueError):
        return "fără detalii"
    if isinstance(body, dict):
        return str(body.get("message") or body.get("error") or "fără detalii")
    return "fără detalii"


class TollRoError(Exception):
    """Eroare generică a clientului TollRo."""


class TollRoAuthError(TollRoError):
    """Autentificare eșuată sau sesiune expirată irecuperabil."""


class TollRoApiClient:
    """Client minimal, read-only, pentru API-ul TollRo."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        username: str | None = None,
        password: str | None = None,
        access_token: str | None = None,
        refresh_token: str | None = None,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._access_token = access_token
        self._refresh_token = refresh_token
        # momentul (time.monotonic) la care expiră access token-ul; None = necunoscut
        self._expires_at: float | None = None

    @property
    def access_token(self) -> str | None:
        return self._access_token

    @property
    def refresh_token(self) -> str | None:
        return self._refresh_token

    @staticmethod
    def _check_host(url: str) -> None:
        """Gardă: permite doar gazdele TollRo (evită SSRF / trimiterea tokenului aiurea)."""
        host = URL(url).host
        if host not in (API_HOST, SSO_HOST):
            raise TollRoError(f"Gazdă neautorizată: {host}")

    def _token_expiring(self) -> bool:
        if self._expires_at is None:
            return False
        return time.monotonic() >= self._expires_at - TOKEN_REFRESH_MARGIN.total_seconds()

    async def _ensure_token(self) -> None:
        """Obține sau reîmprospătează tokenul înainte de cerere, dacă e cazul."""
        if not self._access_token:
            _LOGGER.debug("Nu există access token; mă autentific")
            await self.async_login()
        elif self._token_expiring():
            _LOGGER.debug("Access token-ul expiră în curând; îl reîmprospătez preventiv")
            await self._async_reauthenticate()

    async def _get(self, url: str, *, authed: bool = True, allow_not_found: bool = False) -> Any:
        """GET read-only, cu reîmprospătarea tokenului la 401 (o singură reîncercare).

        aiohttp trimite implicit Accept-Encoding: gzip și decomprimă răspunsul,
        ceea ce evită resetarea observată la resources/countries (tollro.md §20.1).
        """
        self._check_host(url)
        if authed:
            await self._ensure_token()
        data = await self._raw_get(url, authed=authed)
        if data is _UNAUTHORIZED and authed:
            _LOGGER.debug("401 la %s; reîmprospătez sesiunea și reîncerc o dată", URL(url).path)
            await self._async_reauthenticate()
            data = await self._raw_get(url, authed=authed)
        if data is _UNAUTHORIZED:
            raise TollRoAuthError("Serverul a refuzat sesiunea și după reautentificare")
        if data is _NOT_FOUND and not allow_not_found:
            raise TollRoError(f"Resursa nu există: {URL(url).path}")
        return data

    async def _raw_get(self, url: str, *, authed: bool) -> Any:
        headers = {"Accept": "application/json, text/plain, */*"}
        if authed and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
        path = URL(url).path
        started = time.monotonic()
        try:
            async with self._session.get(url, headers=headers, timeout=timeout) as resp:
                elapsed_ms = (time.monotonic() - started) * 1000
                _LOGGER.debug("GET %s → HTTP %s (%.0f ms)", path, resp.status, elapsed_ms)
                if resp.status == 401:
                    return _UNAUTHORIZED
                if resp.status == 404:
                    return _NOT_FOUND
                if resp.status >= 400:
                    raise TollRoError(
                        f"GET {path} → HTTP {resp.status} ({await _backend_code(resp)})"
                    )
                # „json” acoperă și application/vnd.api+json (pagina de status, format JSON:API)
                if "json" in (resp.headers.get("Content-Type") or "").lower():
                    return await resp.json(content_type=None)
                return await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("GET %s a eșuat la nivel de rețea: %r", path, err)
            raise TollRoError(f"Eroare de rețea la {path}: {err}") from err

    async def _token_request(self, form: dict[str, str]) -> None:
        """Cerere la token endpoint-ul Keycloak. Nu jurnalizează niciodată tokenuri sau parole."""
        self._check_host(TOKEN_ENDPOINT)
        grant = form.get("grant_type")
        timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
        try:
            async with self._session.post(TOKEN_ENDPOINT, data=form, timeout=timeout) as resp:
                body = await resp.json(content_type=None)
                status = resp.status
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Autentificarea (%s) a eșuat la nivel de rețea: %r", grant, err)
            raise TollRoError(f"Serverul de autentificare nu răspunde: {err}") from err

        if status != 200 or not isinstance(body, dict) or not body.get("access_token"):
            reason = "răspuns invalid"
            if isinstance(body, dict):
                reason = body.get("error_description") or body.get("error") or f"HTTP {status}"
            _LOGGER.debug("Autentificarea (%s) a fost refuzată: %s", grant, reason)
            raise TollRoAuthError(str(reason))

        self._access_token = body["access_token"]
        if body.get("refresh_token"):
            self._refresh_token = body["refresh_token"]
        expires_in = body.get("expires_in")
        self._expires_at = time.monotonic() + float(expires_in) if expires_in else None
        _LOGGER.debug(
            "Autentificare (%s) reușită; access token valabil %s s, refresh token %s",
            grant,
            expires_in,
            "primit" if body.get("refresh_token") else "neschimbat",
        )

    async def async_login(self) -> None:
        """Autentificare inițială: cu refresh token dacă există, altfel cu utilizator și parolă."""
        await self._async_reauthenticate()

    async def _async_reauthenticate(self) -> None:
        """Reîmprospătează sesiunea; dacă refresh token-ul e respins, revine la parolă."""
        if self._refresh_token:
            try:
                await self._async_refresh()
                return
            except TollRoAuthError as err:
                if not (self._username and self._password):
                    raise
                _LOGGER.debug("Refresh token respins (%s); mă autentific din nou cu parola", err)
                self._refresh_token = None
        await self._async_password_login()

    async def _async_password_login(self) -> None:
        if not (self._username and self._password):
            raise TollRoAuthError("Lipsesc utilizatorul sau parola")
        await self._token_request(
            {
                "grant_type": "password",
                "client_id": CLIENT_ID,
                "username": self._username,
                "password": self._password,
                "scope": SCOPE,
            }
        )

    async def _async_refresh(self) -> None:
        if not self._refresh_token:
            raise TollRoAuthError("Nu există refresh token")
        await self._token_request(
            {
                "grant_type": "refresh_token",
                "client_id": CLIENT_ID,
                "refresh_token": self._refresh_token,
            }
        )

    # ── Metode de citire (read-only) ──
    async def async_get_profiles(self) -> list[dict[str, Any]]:
        return await self._get(f"{API_BASE}profiles")

    async def _get_paged(
        self, endpoint: str, list_key: str, params: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """Toate elementele unei liste paginate pe cursor (`nextCursor`).

        Fără parametrul `size`: dimensiunea implicită a paginii nu e cunoscută, iar forma
        fără `size` e cea folosită în rulările debug_etollro.py.
        """
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        for page_no in range(1, 21):  # plafon de siguranță
            query = dict(params or {})
            if cursor:
                query["cursor"] = cursor
            url = f"{API_BASE}{endpoint}"
            if query:
                url = str(URL(url).with_query(query))
            page = await self._get(url)
            if not isinstance(page, dict):
                break
            page_items = page.get(list_key) or []
            items.extend(page_items)
            cursor = page.get("nextCursor")
            # Serverul dă `nextCursor` ori de câte ori pagina e plină, chiar și pe ultima;
            # sfârșitul listei e o pagină goală (așa se oprește și aplicația, W7/m.java).
            if not cursor or not page_items:
                break
            _LOGGER.debug("%s: pagina %s are continuare, cer pagina următoare", endpoint, page_no)
        return items

    async def async_get_vehicles(self) -> list[dict[str, Any]]:
        return await self._get_paged("vehicles", "vehicles")

    async def async_get_tolls(self, status: str | None = None) -> list[dict[str, Any]]:
        """Serviciile contului; `status` (ex. "EXPIRED") e un filtru verificat pe server."""
        return await self._get_paged("tolls", "tolls", {"status": status} if status else None)

    async def async_get_countries(self) -> list[dict[str, Any]]:
        """Nomenclatorul de țări, cu numele în română și engleză."""
        data = await self._get(f"{API_BASE}resources/countries")
        return (data.get("countries") or []) if isinstance(data, dict) else []

    async def async_get_notifications_count(self) -> int:
        data = await self._get(f"{API_BASE}notifications/summary")
        return int(data.get("count", 0)) if isinstance(data, dict) else 0

    async def async_get_invoices(
        self, date_from: str | None = None, date_to: str | None = None
    ) -> list[dict[str, Any]]:
        """Facturile contului, opțional într-un interval (format verificat: `yyyy-MM-dd`)."""
        url = f"{API_BASE}invoices"
        if date_from and date_to:
            url = str(URL(url).with_query({"from": date_from, "to": date_to}))
        data = await self._get(url)
        return data if isinstance(data, list) else []

    async def async_get_current_session(self) -> dict[str, Any] | None:
        """Sesiunea per-km activă, sau None dacă nu există (404 NO_ACTIVE_SESSION)."""
        data = await self._get(f"{API_BASE}sessions/current", allow_not_found=True)
        return None if data is _NOT_FOUND else data

    async def async_get_service_status(self) -> dict[str, Any]:
        """Starea componentei Android (endpoint public, fără auth)."""
        data = await self._get(
            f"{STATUS_BASE}components/{STATUS_COMPONENT_ID}", authed=False
        )
        if not isinstance(data, dict):
            _LOGGER.debug(
                "Pagina de status a întors un răspuns neașteptat (%s), nu un obiect JSON",
                type(data).__name__,
            )
            return {}
        attributes = (data.get("data") or {}).get("attributes") or {}
        _LOGGER.debug("Starea serviciului: %s", (attributes.get("status") or {}).get("value"))
        return attributes
