"""Data coordinator для интеграции Призрак."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PrizrakAPI, PrizrakAPIError
from .const import (
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    SIGNALR_PING_INTERVAL,
    SIGNALR_SET_CONNECTION_ACTIVITY,
)

_LOGGER = logging.getLogger(__name__)


class PrizrakDataUpdateCoordinator(DataUpdateCoordinator):
    """Координатор для обновления данных от API Призрак."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Инициализация координатора."""
        self.entry = entry
        self.api = PrizrakAPI(
            async_get_clientsession(hass),
            entry.data[CONF_EMAIL],
            entry.data[CONF_PASSWORD],
        )
        self.device_id = entry.data[CONF_DEVICE_ID]

        super().__init__(
            hass,
            _LOGGER,
            name="prizrak",
            update_interval=None,  # Отключаем polling, данные через SignalR
        )

        self._ping_task: asyncio.Task | None = None

    async def _async_update_data(self) -> dict:
        """Получение данных от API."""
        # Возвращаем кешированные данные (обновляются через SignalR EventObject)
        if self.data:
            return self.data
        
        # Первоначальная загрузка — пустое состояние
        return self.api._get_empty_state()

    async def async_config_entry_first_refresh(self) -> None:
        """Первоначальное обновление и подключение SignalR."""
        await super().async_config_entry_first_refresh()

        # Подключение к SignalR для real-time обновлений
        try:
            await self.api.async_connect_signalr()
            
            # Добавление обработчика сообщений для обновления данных
            self.api.add_message_handler(self._handle_signalr_message)
            
            # Подписка на обновления устройства
            await self.api.async_watch_device(self.device_id)
            
            self._ping_task = asyncio.create_task(self._signalr_ping())
        except Exception as err:
            _LOGGER.warning("Не удалось подключиться к SignalR: %s", err)

    def _handle_signalr_message(self, message: dict) -> None:
        """Обработка сообщения от SignalR и обновление данных."""
        try:
            message_type = message.get("type")
            target = message.get("target")
            
            # Обработка EventObject (телеметрия от WatchDevice)
            if message_type == 1 and target == "EventObject":
                arguments = message.get("arguments", [])
                for arg in arguments:
                    device_id = arg.get("device_id")
                    device_state = arg.get("device_state")
                    
                    if device_id == self.device_id and device_state:
                        # Парсим и обновляем данные
                        parsed_state = self.api._parse_device_state({"device_state": device_state})
                        self.async_set_updated_data(parsed_state)
                        _LOGGER.debug("Данные обновлены через EventObject")
                return
            
            if message_type == 7:  # Close
                _LOGGER.warning("SignalR соединение закрыто сервером")
                            
        except Exception as err:
            _LOGGER.error("Ошибка при обработке сообщения SignalR: %s", err)

    async def _signalr_ping(self) -> None:
        """Периодическая отправка ping для поддержания соединения."""
        try:
            while True:
                await asyncio.sleep(SIGNALR_PING_INTERVAL)
                try:
                    await self.api.async_send_signalr_command(
                        SIGNALR_SET_CONNECTION_ACTIVITY, [{}]
                    )
                except Exception as err:
                    _LOGGER.warning("Ошибка при отправке ping: %s", err)
        except asyncio.CancelledError:
            _LOGGER.debug("SignalR ping остановлен")

    async def async_shutdown(self) -> None:
        """Остановка координатора."""
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        await self.api.async_disconnect()

