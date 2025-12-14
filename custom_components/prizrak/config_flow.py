"""Config flow для интеграции Призрак."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PrizrakAPI
from .const import CONF_DEVICE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class PrizrakConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Обработка конфигурации для Призрак."""

    VERSION = 1

    def __init__(self) -> None:
        """Инициализация config flow."""
        self._email: str | None = None
        self._password: str | None = None
        self._devices: dict[int, str] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Шаг ввода учетных данных."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]

            try:
                session = async_get_clientsession(self.hass)
                api = PrizrakAPI(session, self._email, self._password)

                # Попытка авторизации
                await api.async_authenticate()

                # Получение списка устройств
                devices = await api.async_get_devices()
                self._devices = {device["id"]: device["name"] for device in devices}

                if not self._devices:
                    errors["base"] = "no_devices"
                else:
                    # Переход к выбору устройства
                    return await self.async_step_device()

            except Exception as ex:
                _LOGGER.exception("Ошибка при авторизации: %s", ex)
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Шаг выбора устройства."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]

            # Проверка на дубликат
            await self.async_set_unique_id(f"{self._email}_{device_id}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Призрак - {self._devices[device_id]}",
                data={
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_DEVICE_ID: device_id,
                },
            )

        # Формирование схемы с устройствами
        device_schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.In(
                    {str(k): v for k, v in self._devices.items()}
                ),
            }
        )

        return self.async_show_form(
            step_id="device",
            data_schema=device_schema,
            errors=errors,
        )

