"""Тесты для API клиента."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

# Импорт модуля для тестирования
import sys
from pathlib import Path

# Добавляем путь к custom_components для правильного импорта пакета
custom_components_path = Path(__file__).parent.parent / "custom_components"
sys.path.insert(0, str(custom_components_path.parent))

# Мокаем homeassistant модули перед импортом prizrak
from unittest.mock import MagicMock

# Создаем mock для homeassistant модулей
sys.modules['homeassistant'] = MagicMock()
sys.modules['homeassistant.config_entries'] = MagicMock()
sys.modules['homeassistant.const'] = MagicMock()
sys.modules['homeassistant.core'] = MagicMock()
sys.modules['homeassistant.helpers'] = MagicMock()
sys.modules['homeassistant.helpers.aiohttp_client'] = MagicMock()
sys.modules['homeassistant.helpers.update_coordinator'] = MagicMock()
sys.modules['homeassistant.helpers.entity_platform'] = MagicMock()

# Теперь можем импортировать api напрямую
from custom_components.prizrak.api import (
    PrizrakAPI,
    PrizrakAPIError,
    PrizrakAuthenticationError,
)


@pytest.fixture
def mock_session():
    """Создание mock сессии."""
    session = AsyncMock(spec=aiohttp.ClientSession)
    return session


@pytest.fixture
def api_client(mock_session):
    """Создание API клиента для тестирования."""
    return PrizrakAPI(mock_session, "test@example.com", "test_password")


@pytest.mark.asyncio
async def test_authentication_success(mock_session, api_client):
    """Тест успешной авторизации."""
    # Mock ответ авторизации в формате JSON-RPC с session_id
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.cookies = {"sessionId": MagicMock(value="test_session_123")}
    mock_response.headers = {"X-AToken": "encrypted_token_from_server"}
    mock_response.json = AsyncMock(
        return_value={
            "jsonrpc": "2.0",
            "id": 123456789,
            "result": {
                "session_id": "test-session-uuid",
                "created": "2025-12-14T12:00:00",
                "user_title": "test@example.com",
                "access": {"control": True, "tracks": True},
                "profile": {"profile_id": "test-profile-uuid", "title": "test@example.com"},
            },
        }
    )
    mock_response.text = AsyncMock(return_value="")
    
    # Настройка async context manager для mock_response
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    
    # Настройка mock_session.post как async context manager
    mock_session.post.return_value = mock_response
    mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_session.post.return_value.__aexit__ = AsyncMock(return_value=False)

    # Выполнение авторизации
    await api_client.async_authenticate()

    # Проверки
    assert api_client._session_id == "test_session_123"
    assert api_client._access_token is not None
    assert api_client._access_token["Atoken"] == "encrypted_token_from_server"
    assert api_client._access_token["Type"] == 2154785295


@pytest.mark.asyncio
async def test_authentication_failure(mock_session, api_client):
    """Тест неудачной авторизации."""
    # Mock ответ с ошибкой
    mock_response = AsyncMock()
    mock_response.status = 401
    mock_response.text = AsyncMock(return_value="Invalid credentials")
    
    # Настройка async context manager
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    
    # Настройка mock_session.post как async context manager
    mock_session.post.return_value = mock_response
    mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_session.post.return_value.__aexit__ = AsyncMock(return_value=False)

    # Проверка исключения
    with pytest.raises(PrizrakAuthenticationError):
        await api_client.async_authenticate()


@pytest.mark.asyncio
async def test_get_devices(mock_session, api_client):
    """Тест получения списка устройств (с кэшированными данными)."""
    # Mock авторизации
    api_client._access_token = {"Type": 2154785295, "Atoken": "test_token"}
    api_client._session_id = "test_session"

    # Предзаполняем кэш устройств (так как GetDevices использует SignalR)
    api_client._devices_cache = [
        {"device_id": 320980, "name": "Velar", "model": "Призрак-8L/Smart/8.2"}
    ]

    # Выполнение
    devices = await api_client.async_get_devices()

    # Проверки
    assert len(devices) > 0
    assert devices[0]["device_id"] == 320980
    assert devices[0]["name"] == "Velar"


@pytest.mark.asyncio
async def test_signalr_command_format(api_client):
    """Тест формата команды SignalR."""
    # Mock WebSocket
    mock_websocket = AsyncMock()
    api_client._websocket = mock_websocket

    # Отправка команды
    await api_client.async_send_signalr_command(
        "AutolaunchOn", [{"device_id": 320980}]
    )

    # Проверка формата отправленного сообщения
    assert mock_websocket.send.called
    sent_message = mock_websocket.send.call_args[0][0]

    # Проверка формата (должен заканчиваться на \u001e)
    assert sent_message.endswith("\u001e")

    # Проверка JSON структуры
    message_json = json.loads(sent_message.rstrip("\u001e"))
    assert message_json["target"] == "AutolaunchOn"
    assert message_json["type"] == 1
    assert "invocationId" in message_json
    assert message_json["arguments"] == [{"device_id": 320980}]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

