"""Autentificarea prin pagina oficială eToll (ROeID, Google, eIDAS sau parolă).

Conturile create prin ROeID, Google sau eIDAS nu au parolă proprie la eToll, deci nu pot folosi
autentificarea cu parolă. Aplicația TollRo se autentifică prin browser: OpenID Connect,
Authorization Code cu PKCE, clientul public `ddcm-authz-client` (tollro.md §10.1). Integrarea
face la fel: pagina de login e cea oficială, iar Home Assistant primește doar tokenurile.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from .const import AUTHORIZE_ENDPOINT, CLIENT_ID, DOMAIN, NAME, SCOPE, TOKEN_ENDPOINT


class TollRoBrowserAuth(config_entry_oauth2_flow.LocalOAuth2ImplementationWithPkce):
    """Clientul public al aplicației TollRo, fără secret, cu PKCE (S256)."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(hass, DOMAIN, CLIENT_ID, AUTHORIZE_ENDPOINT, TOKEN_ENDPOINT)

    @property
    def name(self) -> str:
        return NAME

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            # offline_access → refresh token care nu expiră odată cu sesiunea din browser
            "scope": SCOPE,
            "ui_locales": "ro" if (self.hass.config.language or "").startswith("ro") else "en",
            # pagina de login apare mereu, chiar dacă browserul are deja o sesiune eToll
            # (altfel s-ar conecta tăcut contul din browser, poate altul decât cel dorit)
            "prompt": "login",
        }
        data.update(super().extra_authorize_data)
        return data
