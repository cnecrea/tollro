"""Config flow pentru CNAIR eToll (TollRo).

Două metode de autentificare, aceeași verificare (citirea profilurilor contului):
- cu e-mail (sau telefon) și parolă — grant `password`, ca până acum;
- prin pagina oficială eToll, în browser — pentru conturile create prin ROeID, Google sau
  eIDAS, care nu au parolă eToll (vezi oauth.py). Se salvează doar tokenurile.

Fluxuri:
- `user`: adăugarea contului (alegerea metodei);
- `reconfigure`: schimbarea datelor sau a metodei din meniul integrării, fără ștergerea ei;
- `reauth`: pornit automat de Home Assistant când autentificarea nu mai reușește — cu parola
  actuală sau din nou prin browser, după cum a fost conectat contul.

OptionsFlow („Configurează”): activarea / vizualizarea licenței.
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow, selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import TollRoApiClient, TollRoAuthError, TollRoError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_LICENSE_KEY,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_USERNAME,
    DOMAIN,
    LICENSE_DATA_KEY,
    LICENSE_PURCHASE_URL,
    NAME,
)
from .license import LicenseManager
from .oauth import TollRoBrowserAuth

_LOGGER = logging.getLogger(__name__)


class _ValidationError(Exception):
    """Eroare de validare, cu cheia de traducere din `config.error`."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def _token_subject(access_token: str) -> str | None:
    """`sub` din access token — doar ca identificator; semnătura o verifică serverul eToll."""
    try:
        payload = access_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return None
    return claims.get("sub") if isinstance(claims, dict) else None


def _uses_browser(entry: ConfigEntry) -> bool:
    """Contul a fost conectat prin pagina eToll: are tokenuri, dar nu are parolă salvată."""
    return not entry.data.get(CONF_PASSWORD)


class TollRoConfigFlow(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Gestionează configurarea prin UI."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TollRoOptionsFlow:
        return TollRoOptionsFlow()

    async def _async_validate(
        self, username: str, password: str
    ) -> tuple[TollRoApiClient, list[dict[str, Any]]]:
        """Se autentifică și citește profilurile; aruncă _ValidationError cu cheia erorii."""
        client = TollRoApiClient(
            async_get_clientsession(self.hass), username=username, password=password
        )
        try:
            await client.async_login()
            profiles = await client.async_get_profiles()
        except TollRoAuthError as err:
            _LOGGER.debug("Configurare: autentificare refuzată (%s)", err)
            raise _ValidationError("invalid_auth") from err
        except TollRoError as err:
            _LOGGER.debug("Configurare: serviciul eToll nu a putut fi contactat (%s)", err)
            raise _ValidationError("cannot_connect") from err
        except Exception as err:  # noqa: BLE001 — orice altceva trebuie să ajungă în jurnal
            _LOGGER.exception("Configurare: eroare neașteptată la autentificare")
            raise _ValidationError("unknown") from err
        _LOGGER.debug("Configurare: autentificare reușită, %d profil(uri) găsite", len(profiles))
        return client, profiles or []

    @staticmethod
    def _entry_data(username: str, password: str, client: TollRoApiClient) -> dict[str, Any]:
        return {
            CONF_USERNAME: username,
            CONF_PASSWORD: password,
            CONF_ACCESS_TOKEN: client.access_token,
            CONF_REFRESH_TOKEN: client.refresh_token,
        }

    @staticmethod
    def _current_profile(profiles: list[dict[str, Any]]) -> dict[str, Any]:
        return next((p for p in profiles if p.get("isCurrent")), profiles[0] if profiles else {})

    @staticmethod
    def _same_account(unique_id: str | None, profiles: list[dict[str, Any]]) -> bool:
        """Același cont dacă oricare dintre profiluri are id-ul înregistrării.

        Comparația nu se face doar cu profilul curent: dacă utilizatorul a schimbat între
        timp profilul activ în aplicație, contul rămâne același.
        """
        if not unique_id:
            return True
        return any(p.get("id") == unique_id for p in profiles)

    # ── Adăugarea contului: alegerea metodei ──
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["password", "browser"])

    async def async_step_password(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username, password = user_input[CONF_USERNAME].strip(), user_input[CONF_PASSWORD]
            try:
                client, profiles = await self._async_validate(username, password)
            except _ValidationError as err:
                errors["base"] = err.key
            else:
                profile = self._current_profile(profiles)
                await self.async_set_unique_id(profile.get("id") or username.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=profile.get("email") or username or NAME,
                    data=self._entry_data(username, password, client),
                )

        return self.async_show_form(
            step_id="password",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_browser(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_start_browser_auth()

    # ── Autentificarea prin pagina oficială eToll ──
    async def _async_start_browser_auth(self) -> ConfigFlowResult:
        """Deschide pagina de login eToll; revenirea continuă în async_oauth_create_entry.

        Fiecare flux are propria implementare (deci propriul cod PKCE); nu se înregistrează
        global, ca două configurări simultane să nu-și împartă codul.
        """
        _LOGGER.debug("Autentificare prin browser: se deschide pagina de login eToll")
        self.flow_impl = TollRoBrowserAuth(self.hass)
        return await self.async_step_auth()

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Contul a fost autorizat în browser: verifică tokenurile citind profilurile, apoi salvează."""
        token = data["token"]
        if not token.get("refresh_token"):
            # fără el, integrarea s-ar deconecta la expirarea access token-ului (30 min)
            _LOGGER.debug("Autentificare prin browser: serverul nu a emis refresh token")
            return self.async_abort(reason="no_refresh_token")

        client = TollRoApiClient(
            async_get_clientsession(self.hass),
            access_token=token["access_token"],
            refresh_token=token["refresh_token"],
        )
        try:
            profiles = await client.async_get_profiles() or []
        except TollRoAuthError as err:
            _LOGGER.debug("Autentificare prin browser: tokenul a fost refuzat (%s)", err)
            return self.async_abort(reason="invalid_auth")
        except TollRoError as err:
            _LOGGER.debug("Autentificare prin browser: serviciul eToll nu răspunde (%s)", err)
            return self.async_abort(reason="cannot_connect")
        except Exception:  # noqa: BLE001 — orice altceva trebuie să ajungă în jurnal
            _LOGGER.exception("Autentificare prin browser: eroare neașteptată")
            return self.async_abort(reason="unknown")
        _LOGGER.debug("Autentificare prin browser reușită, %d profil(uri) găsite", len(profiles))

        # Doar tokenurile: fără parolă salvată, contul rămâne pe autentificarea prin browser
        # (de aceea `data=` la actualizare — înlocuiește și o eventuală parolă veche)
        entry_data = {
            CONF_ACCESS_TOKEN: client.access_token,
            CONF_REFRESH_TOKEN: client.refresh_token,
        }
        if self.source in (SOURCE_REAUTH, SOURCE_RECONFIGURE):
            entry = (
                self._get_reauth_entry()
                if self.source == SOURCE_REAUTH
                else self._get_reconfigure_entry()
            )
            if not self._same_account(entry.unique_id, profiles):
                return self.async_abort(reason="wrong_account")
            return self.async_update_reload_and_abort(entry, data=entry_data)

        profile = self._current_profile(profiles)
        await self.async_set_unique_id(profile.get("id") or _token_subject(client.access_token or ""))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=profile.get("email") or NAME, data=entry_data)

    # ── Reconfigurare (din meniul integrării) ──
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = ["reconfigure_password", "reconfigure_browser"]
        if _uses_browser(self._get_reconfigure_entry()):
            options.reverse()  # metoda folosită acum, prima
        return self.async_show_menu(step_id="reconfigure", menu_options=options)

    async def async_step_reconfigure_password(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            username, password = user_input[CONF_USERNAME].strip(), user_input[CONF_PASSWORD]
            try:
                client, profiles = await self._async_validate(username, password)
            except _ValidationError as err:
                errors["base"] = err.key
            else:
                if not self._same_account(entry.unique_id, profiles):
                    return self.async_abort(reason="wrong_account")
                _LOGGER.debug("Reconfigurare: datele de autentificare au fost actualizate")
                return self.async_update_reload_and_abort(
                    entry, data_updates=self._entry_data(username, password, client)
                )

        return self.async_show_form(
            step_id="reconfigure_password",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure_browser(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_start_browser_auth()

    # ── Reautentificare (pornită automat de Home Assistant) ──
    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        _LOGGER.debug("Reautentificare: Home Assistant a cerut reconectarea contului")
        if entry_data.get(CONF_PASSWORD):
            return await self.async_step_reauth_confirm()
        return await self.async_step_reauth_browser()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        username = entry.data.get(CONF_USERNAME, "")
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            try:
                client, profiles = await self._async_validate(username, password)
            except _ValidationError as err:
                errors["base"] = err.key
            else:
                if not self._same_account(entry.unique_id, profiles):
                    return self.async_abort(reason="wrong_account")
                _LOGGER.debug("Reautentificare: contul a fost reconectat")
                return self.async_update_reload_and_abort(
                    entry, data_updates=self._entry_data(username, password, client)
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"username": username},
            errors=errors,
        )

    async def async_step_reauth_browser(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Contul conectat prin browser se reconectează tot prin pagina eToll."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_browser",
                description_placeholders={"account": self._get_reauth_entry().title},
            )
        return await self._async_start_browser_auth()


# ── Licență ──

_ETICHETE_TIP_LICENTA = {
    # Tipurile emise de WebAPI (LICENSE_DURATION)
    "perpetual": ("perpetuă", "perpetual"),
    "annual": ("anuală", "annual"),
    "semi_annual": ("semestrială", "semi-annual"),
    "monthly": ("lunară", "monthly"),
}

# Codurile WebAPI /activate + erorile locale → cheile din `options.error`
_ERORI_ACTIVARE = {
    "invalid_key": "license_key_invalid",
    "already_used": "license_already_used",
    "expired_key": "license_key_expired",
    "fingerprint_mismatch": "license_fingerprint_mismatch",
    "network_error": "license_network_error",
    "http_502": "license_network_error",
    "http_503": "license_network_error",  # server temporar ocupat
    "http_504": "license_network_error",
}


def _eticheta_tip_licenta(tip: str | None, is_ro: bool) -> str:
    """Eticheta afișată pentru tipul de licență primit de la server."""
    if not tip:
        return "necunoscut" if is_ro else "unknown"
    ro, en = _ETICHETE_TIP_LICENTA.get(tip, (tip, tip))
    return ro if is_ro else en


def _data(timestamp: float) -> str:
    return dt_util.as_local(dt_util.utc_from_timestamp(timestamp)).strftime("%d.%m.%Y")


def _status_licenta(mgr: LicenseManager, is_ro: bool) -> str:
    """Textul de stare afișat deasupra câmpului pentru cheie."""
    cumpara = f"🛒 {'Obține licență' if is_ro else 'Get a license'}: {LICENSE_PURCHASE_URL}"
    if mgr.status == "licensed":
        tip = _eticheta_tip_licenta(mgr.license_type, is_ro)
        linii = [f"✅ {'Licență activă' if is_ro else 'Active license'} ({tip})"]
        if mgr.license_key_masked:
            linii[0] += f" — {mgr.license_key_masked}"
        if mgr.activated_at:
            linii.append(f"{'Activată la' if is_ro else 'Activated on'}: {_data(mgr.activated_at)}")
        if mgr.license_expires_at:
            linii.append(f"📅 {'Expiră la' if is_ro else 'Expires on'}: {_data(mgr.license_expires_at)}")
        elif mgr.license_type == "perpetual":
            linii.append("Valabilitate: nelimitată (perpetuă)" if is_ro else "Validity: unlimited (perpetual)")
        return "\n".join(linii)
    if mgr.status == "trial":
        zile = mgr.trial_days_remaining
        stare = f"⏳ Evaluare — {zile} zile rămase" if is_ro else f"⏳ Trial — {zile} days remaining"
        return "\n".join([stare, "", cumpara])
    if mgr.status == "expired":
        return "\n".join(["❌ Licență expirată" if is_ro else "❌ License expired", "", cumpara])
    stare = "❌ Fără licență — funcționalitate blocată" if is_ro else "❌ No license — functionality blocked"
    return "\n".join([stare, "", cumpara])


class TollRoOptionsFlow(OptionsFlow):
    """Opțiuni: activarea licenței (STANDARD-LICENTA.md)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_licenta()

    async def async_step_licenta(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        is_ro = (self.hass.config.language or "").startswith("ro")

        mgr: LicenseManager | None = self.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        if mgr is None:
            # Intrarea nu rulează (ex. setup eșuat) — managerul se citește din stocare
            mgr = LicenseManager(self.hass)
            await mgr.async_load()

        if user_input is not None:
            cheie = (user_input.get(CONF_LICENSE_KEY) or "").strip()
            if not cheie:
                errors["base"] = "license_key_empty"
            elif len(cheie) < 10:
                errors["base"] = "license_key_invalid"
            else:
                result = await mgr.async_activate(cheie)
                if result.get("success"):
                    persistent_notification.async_create(
                        self.hass,
                        f"Licența {NAME} a fost activată cu succes! "
                        f"Tip: {_eticheta_tip_licenta(mgr.license_type, True)}.",
                        title="Licență activată",
                        notification_id="tollro_license_activated",
                    )
                    # Opțiunile rămân neschimbate; managerul reîncarcă singur intrările
                    return self.async_create_entry(data=dict(self.config_entry.options))
                errors["base"] = _ERORI_ACTIVARE.get(
                    result.get("error", ""), "license_server_error"
                )

        return self.async_show_form(
            step_id="licenta",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LICENSE_KEY): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                            suffix="ETOLL-XXXX-XXXX-XXXX-XXXX",
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"license_status": _status_licenta(mgr, is_ro)},
        )
