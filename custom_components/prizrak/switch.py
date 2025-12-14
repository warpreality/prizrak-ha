"""Switches для интеграции Призрак."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_PUK_CODE,
    DOMAIN,
    SIGNALR_AUTOLAUNCH_OFF,
    SIGNALR_AUTOLAUNCH_ON,
    SIGNALR_VALET_OFF,
    SIGNALR_VALET_ON,
    STATE_AUTOLAUNCH_ON,
    STATE_SERVICE_MODE,
)
from .coordinator import PrizrakDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка switches из конфигурации."""
    coordinator: PrizrakDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    switches = [
        PrizrakAutolaunchSwitch(coordinator),
        PrizrakServiceModeSwitch(coordinator, entry),
    ]

    async_add_entities(switches)


class PrizrakSwitch(CoordinatorEntity, SwitchEntity):
    """Базовый класс для switches Призрак."""

    def __init__(
        self,
        coordinator: PrizrakDataUpdateCoordinator,
        key: str,
        name: str,
        icon: str | None = None,
    ) -> None:
        """Инициализация switch."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"Призрак {name}"
        self._attr_unique_id = f"{coordinator.device_id}_{key}"
        self._attr_icon = icon

    @property
    def device_info(self) -> dict:
        """Информация об устройстве."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.device_id)},
            "name": f"Призрак {self.coordinator.device_id}",
            "manufacturer": "Призрак",
        }


class PrizrakAutolaunchSwitch(PrizrakSwitch):
    """Switch для управления автозапуском."""

    def __init__(self, coordinator: PrizrakDataUpdateCoordinator) -> None:
        """Инициализация switch автозапуска."""
        super().__init__(coordinator, "autolaunch", "Автозапуск", "mdi:car-key")

    @property
    def is_on(self) -> bool:
        """Текущее состояние автозапуска."""
        state = self.coordinator.data.get("state")
        return state == STATE_AUTOLAUNCH_ON

    async def async_turn_on(self, **kwargs) -> None:
        """Включение автозапуска."""
        try:
            await self.coordinator.api.async_send_signalr_command(
                SIGNALR_AUTOLAUNCH_ON,
                [{"device_id": self.coordinator.device_id}],
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            self._log_error("включения автозапуска", err)

    async def async_turn_off(self, **kwargs) -> None:
        """Выключение автозапуска."""
        try:
            await self.coordinator.api.async_send_signalr_command(
                SIGNALR_AUTOLAUNCH_OFF,
                [{"device_id": self.coordinator.device_id}],
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            self._log_error("выключения автозапуска", err)

    def _log_error(self, action: str, err: Exception) -> None:
        """Логирование ошибки."""
        self.coordinator.logger.error(
            "Ошибка при %s: %s", action, err, exc_info=True
        )


class PrizrakServiceModeSwitch(PrizrakSwitch):
    """Switch для управления сервисным режимом."""

    def __init__(
        self, coordinator: PrizrakDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Инициализация switch сервисного режима."""
        super().__init__(
            coordinator, "service_mode", "Сервисный режим", "mdi:wrench"
        )
        self._puk_code = entry.data.get(CONF_PUK_CODE)

    @property
    def is_on(self) -> bool:
        """Текущее состояние сервисного режима."""
        state = self.coordinator.data.get("state")
        return state == STATE_SERVICE_MODE

    async def async_turn_on(self, **kwargs) -> None:
        """Включение сервисного режима."""
        if not self._puk_code:
            self.coordinator.logger.error("PUK-код не настроен")
            return

        try:
            await self.coordinator.api.async_send_signalr_command(
                SIGNALR_VALET_ON,
                [
                    {
                        "device_id": self.coordinator.device_id,
                        "puk": int(self._puk_code),
                        "distance": 2,
                    }
                ],
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            self._log_error("включения сервисного режима", err)

    async def async_turn_off(self, **kwargs) -> None:
        """Выключение сервисного режима."""
        if not self._puk_code:
            self.coordinator.logger.error("PUK-код не настроен")
            return

        try:
            await self.coordinator.api.async_send_signalr_command(
                SIGNALR_VALET_OFF,
                [
                    {
                        "device_id": self.coordinator.device_id,
                        "puk": int(self._puk_code),
                        "distance": 2,
                    }
                ],
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            self._log_error("выключения сервисного режима", err)

    def _log_error(self, action: str, err: Exception) -> None:
        """Логирование ошибки."""
        self.coordinator.logger.error(
            "Ошибка при %s: %s", action, err, exc_info=True
        )

