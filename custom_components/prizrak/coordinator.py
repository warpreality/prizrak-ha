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
            update_interval=timedelta(seconds=30),
        )

        self._ping_task: asyncio.Task | None = None

    async def _async_update_data(self) -> dict:
        """Получение данных от API."""
        try:
            data = await self.api.async_get_device_state(self.device_id)
            return data
        except PrizrakAPIError as err:
            raise UpdateFailed(f"Ошибка при обновлении данных: {err}") from err

    async def async_config_entry_first_refresh(self) -> None:
        """Первоначальное обновление и подключение SignalR."""
        await super().async_config_entry_first_refresh()

        # Подключение к SignalR для real-time обновлений
        try:
            await self.api.async_connect_signalr()
            
            # Добавление обработчика сообщений для обновления данных
            self.api.add_message_handler(self._handle_signalr_message)
            
            self._ping_task = asyncio.create_task(self._signalr_ping())
        except Exception as err:
            _LOGGER.warning("Не удалось подключиться к SignalR: %s", err)

    def _handle_signalr_message(self, message: dict) -> None:
        """Обработка сообщения от SignalR и обновление данных."""
        try:
            # Обработка различных типов сообщений от SignalR
            message_type = message.get("type")
            
            if message_type == 1:  # Invocation
                # Ответ на команду
                invocation_id = message.get("invocationId")
                result = message.get("result")
                error = message.get("error")
                
                if error:
                    _LOGGER.error("Ошибка в ответе SignalR: %s", error)
                elif result:
                    _LOGGER.debug("Результат команды: %s", result)
                    
            elif message_type == 3:  # Completion
                # Завершение вызова
                pass
                
            elif message_type == 6:  # Ping
                # Ping сообщение, отвечаем pong
                pass
                
            elif message_type == 7:  # Close
                # Закрытие соединения
                _LOGGER.warning("SignalR соединение закрыто сервером")
                
            else:
                # Обновление состояния устройства
                # Пытаемся извлечь данные о состоянии из сообщения
                if "arguments" in message:
                    state_data = message["arguments"]
                    if isinstance(state_data, list) and len(state_data) > 0:
                        device_data = state_data[0]
                        if isinstance(device_data, dict):
                            # Обновляем данные координатора
                            current_data = self.data.copy() if self.data else {}
                            current_data.update(device_data)
                            self.async_set_updated_data(current_data)
                            _LOGGER.debug("Данные обновлены через SignalR: %s", device_data)
                            
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

