"""Buttons для интеграции Призрак."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PrizrakDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка buttons из конфигурации."""
    coordinator: PrizrakDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    buttons = [
        # TODO: Добавить кнопки для других команд после изучения их методов SignalR
        # PrizrakSearchButton(coordinator),
        # PrizrakLocationButton(coordinator),
    ]

    async_add_entities(buttons)


class PrizrakButton(CoordinatorEntity, ButtonEntity):
    """Базовый класс для buttons Призрак."""

    def __init__(
        self,
        coordinator: PrizrakDataUpdateCoordinator,
        key: str,
        name: str,
        icon: str | None = None,
    ) -> None:
        """Инициализация button."""
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

    async def async_press(self) -> None:
        """Обработка нажатия кнопки."""
        # Реализация в подклассах
        pass

