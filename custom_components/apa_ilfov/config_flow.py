"""Config flow pentru Apă Ilfov."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .client import ApaIlfovClient, AuthError, ConnectError
from .const import (
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SENDER,
    CONF_SERVER,
    CONF_USERNAME,
    DEFAULT_FOLDER,
    DEFAULT_PORT,
    DEFAULT_SCAN_MINUTES,
    DEFAULT_SENDER,
    DEFAULT_SERVER,
    DOMAIN,
    OPT_FOLDER,
    OPT_ONLY_SEWER,
    OPT_SCAN_MINUTES,
)


async def _test(hass, data: dict[str, Any], folder: str = DEFAULT_FOLDER) -> str | None:
    client = ApaIlfovClient(
        data[CONF_SERVER],
        int(data[CONF_PORT]),
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        data[CONF_SENDER],
        folder=folder,
    )
    try:
        await hass.async_add_executor_job(client.test)
    except AuthError:
        return "invalid_auth"
    except ConnectError:
        return "cannot_connect"
    except Exception:  # noqa: BLE001
        return "unknown"
    return None


class ApaIlfovConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ApaIlfovOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_USERNAME] = user_input[CONF_USERNAME].strip()
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()
            err = await _test(self.hass, user_input)
            if err is None:
                return self.async_create_entry(title="Apă Ilfov", data=user_input)
            errors["base"] = err
        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=(user_input or {}).get(CONF_USERNAME, "")): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_SERVER, default=DEFAULT_SERVER): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_SENDER, default=DEFAULT_SENDER): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            err = await _test(self.hass, data)
            if err is None:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = err
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )


class ApaIlfovOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        o = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(OPT_ONLY_SEWER, default=o.get(OPT_ONLY_SEWER, True)): bool,
                vol.Required(
                    OPT_SCAN_MINUTES, default=o.get(OPT_SCAN_MINUTES, DEFAULT_SCAN_MINUTES)
                ): vol.All(int, vol.Range(min=15, max=1440)),
                vol.Required(OPT_FOLDER, default=o.get(OPT_FOLDER, DEFAULT_FOLDER)): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
