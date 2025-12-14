"""API клиент для системы мониторинга Призрак."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
import urllib.parse
import uuid
from typing import Any, Callable

import aiohttp
import websockets
from websockets.legacy.client import WebSocketClientProtocol

from .const import (
    API_BASE,
    CONTROL_NEGOTIATE,
    CONTROL_WS,
    PASSPORT_API,
    SIGNALR_GET_DEVICES,
    SIGNALR_GET_DEVICE_INFO,
    SIGNALR_SET_CONNECTION_ACTIVITY,
    SIGNALR_WATCH_DEVICE,
)

_LOGGER = logging.getLogger(__name__)


class PrizrakAPIError(Exception):
    """Базовое исключение для API ошибок."""

    pass


class PrizrakAuthenticationError(PrizrakAPIError):
    """Ошибка аутентификации."""

    pass


class PrizrakAPI:
    """Клиент API для системы мониторинга Призрак."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
    ) -> None:
        """Инициализация API клиента."""
        self._session = session
        self._email = email
        self._password = password
        self._access_token: dict[str, Any] | None = None
        self._session_id: str | None = None
        self._websocket: WebSocketClientProtocol | None = None
        self._connection_id: str | None = None
        self._message_handlers: list[Callable[[dict], None]] = []
        self._websocket_task: asyncio.Task | None = None
        self._pending_requests: dict[str, asyncio.Future] = {}
        self._devices_cache: list[dict[str, Any]] = []
        self._device_states: dict[int, dict[str, Any]] = {}

    def _generate_vtoken(self) -> str:
        """Генерация X-VToken заголовка."""
        # Генерируем fingerprint на основе случайных данных
        fingerprint = hashlib.md5(uuid.uuid4().bytes).hexdigest()
        
        # Генерируем UniqId (4 части по 8 символов)
        uniq_parts = [uuid.uuid4().hex[:8] for _ in range(4)]
        uniq_id = "".join(uniq_parts)
        
        vtoken_data = {
            "VTokenKey": "x-vtoken",
            "FingerPrint": fingerprint,
            "UniqId": uniq_id,
            "AppVersion": "268.0.0.0",
            "Service": "",
        }
        
        # Сохраняем fingerprint для генерации Atoken
        self._fingerprint = fingerprint
        
        vtoken_json = json.dumps(vtoken_data, separators=(',', ':'))
        return base64.b64encode(vtoken_json.encode()).decode()
    
    def _generate_atoken(self, session_id: str) -> str:
        """Генерация Atoken на основе session_id.
        
        Atoken - это зашифрованный токен с использованием CryptoJS.AES.
        Ключ шифрования - reCAPTCHA site key.
        
        Формат: U2FsdGVkX1... (CryptoJS OpenSSL формат)
        
        Шифруется JSON объект с данными сессии, а не просто session_id.
        """
        try:
            from Crypto.Cipher import AES
            from Crypto.Random import get_random_bytes
            
            # Данные для шифрования - JSON с данными сессии
            # Формат похож на то, что шифруется браузером
            session_data = {
                "session_id": session_id,
                "created": int(time.time() * 1000),
            }
            data = json.dumps(session_data, separators=(',', ':')).encode('utf-8')
            
            # Ключ - reCAPTCHA site key (используется в passport.js)
            key = b'6LfV7EshAAAAAHVoAh3ZdDIsr0TfizlqZGrKxZ2k'
            
            # Генерируем соль (8 байт для OpenSSL формата)
            salt = get_random_bytes(8)
            
            # Деривация ключа и IV (как в CryptoJS)
            # CryptoJS использует EVP_BytesToKey
            key_iv = self._evp_bytes_to_key(key, salt, 32, 16)
            derived_key = key_iv[:32]
            iv = key_iv[32:48]
            
            # Паддинг PKCS7
            pad_len = 16 - (len(data) % 16)
            data = data + bytes([pad_len] * pad_len)
            
            # Шифрование
            cipher = AES.new(derived_key, AES.MODE_CBC, iv)
            encrypted = cipher.encrypt(data)
            
            # Формат OpenSSL: "Salted__" + salt + encrypted
            result = b"Salted__" + salt + encrypted
            
            return base64.b64encode(result).decode()
            
        except ImportError:
            # Если pycryptodome не установлен, используем session_id как есть
            _LOGGER.warning("pycryptodome не установлен, используется session_id напрямую")
            return session_id
        except Exception as err:
            _LOGGER.warning("Ошибка генерации Atoken: %s, используется session_id", err)
            return session_id
    
    def _evp_bytes_to_key(self, password: bytes, salt: bytes, key_len: int, iv_len: int) -> bytes:
        """Реализация EVP_BytesToKey как в OpenSSL/CryptoJS."""
        d = b''
        d_i = b''
        while len(d) < key_len + iv_len:
            d_i = hashlib.md5(d_i + password + salt).digest()
            d += d_i
        return d[:key_len + iv_len]

    async def async_authenticate(self) -> None:
        """Авторизация в системе."""
        try:
            _LOGGER.debug("Авторизация пользователя %s", self._email)

            # Генерация X-VToken
            vtoken = self._generate_vtoken()
            
            # Подготовка данных для авторизации
            # API использует JSON-RPC 2.0 формат
            request_id = int(time.time() * 1000)
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "Authorization",
                "params": {
                    "login": self._email,
                    "password": self._password,
                    "forever": True,
                    "language_code": "RU",
                },
            }

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-VToken": vtoken,
            }

            async with self._session.post(
                PASSPORT_API, json=payload, headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error(
                        "Ошибка авторизации: статус %s, ответ: %s",
                        response.status,
                        error_text,
                    )
                    raise PrizrakAuthenticationError(
                        f"Ошибка авторизации: статус {response.status}"
                    )

                # Получение cookies (sessionId)
                cookies = response.cookies
                if "sessionId" in cookies:
                    self._session_id = cookies["sessionId"].value
                    _LOGGER.debug("Получен sessionId: %s", self._session_id)

                # Получение X-AToken из заголовков ответа
                atoken = response.headers.get("X-AToken") or response.headers.get("x-atoken")
                if atoken:
                    _LOGGER.debug("Получен X-AToken из заголовков")
                else:
                    _LOGGER.debug("X-AToken не найден в заголовках, заголовки: %s", dict(response.headers))

                # Получение данных ответа
                data = await response.json()
                _LOGGER.debug("Ответ авторизации: %s", data)

                # Проверка на ошибку JSON-RPC
                if "error" in data:
                    error_msg = data["error"].get("message", "Unknown error")
                    _LOGGER.error("Ошибка авторизации: %s", error_msg)
                    raise PrizrakAuthenticationError(f"Ошибка авторизации: {error_msg}")

                # Извлечение результата из JSON-RPC ответа
                result = data.get("result", data)
                
                if not isinstance(result, dict) or "session_id" not in result:
                    _LOGGER.error("Неверный формат ответа авторизации: %s", data)
                    raise PrizrakAuthenticationError("Неверный формат ответа авторизации")
                
                # Сохраняем session_id
                server_session_id = result.get("session_id")
                _LOGGER.debug("Получен session_id: %s", server_session_id)
                
                # Если X-AToken не получен из заголовков, генерируем его
                if not atoken:
                    atoken = self._generate_atoken(server_session_id)

                # Формирование access_token в формате Bearer
                self._access_token = {
                    "Type": 2154785295,
                    "Atoken": atoken,
                    "ClientData": {
                        "AppName": "Home Assistant Prizrak",
                        "AppVersion": "0.1.0",
                        "AppHost": "homeassistant.local",
                        "IsUserDataAvailable": True,
                        "AdditionalInfo": {},
                    },
                    "Lang": "ru",
                }

                _LOGGER.debug("Авторизация успешна, получен токен")

        except aiohttp.ClientError as err:
            _LOGGER.error("Ошибка при авторизации: %s", err)
            raise PrizrakAuthenticationError(f"Ошибка авторизации: {err}") from err
        except json.JSONDecodeError as err:
            _LOGGER.error("Ошибка парсинга JSON ответа: %s", err)
            raise PrizrakAuthenticationError("Неверный формат ответа сервера") from err

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Получение списка устройств (автомобилей) через SignalR."""
        try:
            if not self._access_token:
                await self.async_authenticate()

            _LOGGER.debug("Получение списка устройств")

            # Если есть кэш, возвращаем его
            if self._devices_cache:
                return self._devices_cache

            # Подключаемся к SignalR если ещё не подключены
            if not self._websocket:
                await self.async_connect_signalr()

            # Отправляем запрос GetDevices через SignalR
            try:
                result = await self.async_invoke_signalr(SIGNALR_GET_DEVICES, [{}])
                _LOGGER.debug("GetDevices result: %s", result)
                
                devices = []
                if result:
                    # Формат: {"data": {"devices": [...]}}
                    if isinstance(result, dict):
                        if "data" in result and "devices" in result["data"]:
                            devices = result["data"]["devices"]
                        elif "devices" in result:
                            devices = result["devices"]
                    elif isinstance(result, list):
                        devices = result
                
                if devices:
                    self._devices_cache = devices
                    # Обновляем состояния устройств
                    for device in devices:
                        device_id = device.get("device_id") or device.get("id")
                        if device_id:
                            self._device_states[device_id] = device
                    return devices
                    
            except asyncio.TimeoutError:
                _LOGGER.warning("Таймаут при получении устройств через SignalR")
            except Exception as err:
                _LOGGER.warning("Ошибка при получении устройств через SignalR: %s", err)

            # Fallback: возвращаем кэш если есть
            if self._devices_cache:
                return self._devices_cache

            _LOGGER.warning("Не удалось получить список устройств")
            return []

        except Exception as err:
            _LOGGER.error("Ошибка при получении устройств: %s", err)
            raise PrizrakAPIError(f"Ошибка получения устройств: {err}") from err

    async def async_get_device_state(self, device_id: int) -> dict[str, Any]:
        """Получение текущего состояния устройства."""
        try:
            _LOGGER.debug("Получение состояния устройства %s", device_id)

            # Возвращаем кэшированное состояние если есть
            if device_id in self._device_states:
                return self._parse_device_state(self._device_states[device_id])

            # Запрашиваем через SignalR
            if self._websocket:
                try:
                    result = await self.async_invoke_signalr(
                        SIGNALR_GET_DEVICE_INFO, [{"device_id": device_id}]
                    )
                    if result:
                        self._device_states[device_id] = result
                        return self._parse_device_state(result)
                except Exception as err:
                    _LOGGER.warning("Ошибка получения состояния через SignalR: %s", err)

            # Возвращаем пустое состояние
            return self._get_empty_state()

        except Exception as err:
            _LOGGER.error("Ошибка при получении состояния: %s", err)
            raise PrizrakAPIError(f"Ошибка получения состояния: {err}") from err

    def _parse_device_state(self, data: dict[str, Any]) -> dict[str, Any]:
        """Парсинг состояния устройства из данных SignalR (EventObject)."""
        # Извлекаем device_state из EventObject или используем data напрямую
        state_data = data.get("device_state") or data.get("state") or data.get("data") or data
        
        # Маппинг состояния охраны
        guard_state = state_data.get("guard", "")
        state_text = "Неизвестно"
        if "SafeGuard" in str(guard_state):
            state_text = "В охране"
        elif guard_state == "Off":
            state_text = "Снято с охраны"
        
        valet = state_data.get("valet", "")
        if valet == "On":
            state_text = "Сервисный режим"
        
        return {
            "state": state_text,
            "balance": state_data.get("balance"),
            "temperature_outside": state_data.get("outside_temp"),
            "temperature_engine": state_data.get("engine_temp"),
            "temperature_interior": state_data.get("inside_temp"),
            "voltage": state_data.get("accum_voltage"),
            "rpm": state_data.get("rpm") or 0,
            "fuel": state_data.get("fuel_level"),
            "speed": state_data.get("speed") or 0,
            "mileage": state_data.get("mileage"),
            "autolaunch": state_data.get("autolaunch"),
            "guard": guard_state,
            "valet": valet,
            "engine": state_data.get("ignition_switch"),
            "lat": state_data.get("latitude"),
            "lon": state_data.get("longitude"),
            "connected": state_data.get("connected"),
        }

    async def async_watch_device(self, device_id: int) -> None:
        """Подписка на обновления устройства через WatchDevice."""
        try:
            if not self._websocket:
                await self.async_connect_signalr()
            
            _LOGGER.debug("Подписка на устройство %s", device_id)
            await self.async_send_signalr_command(
                SIGNALR_WATCH_DEVICE, [{"device_id": device_id}]
            )
        except Exception as err:
            _LOGGER.warning("Ошибка при подписке на устройство: %s", err)

    def _get_empty_state(self) -> dict[str, Any]:
        """Возвращает пустое состояние."""
        return {
            "state": "Неизвестно",
            "balance": None,
            "temperature_outside": None,
            "temperature_engine": None,
            "temperature_interior": None,
            "voltage": None,
            "rpm": 0,
            "fuel": None,
            "speed": 0,
            "mileage": None,
            "autolaunch": None,
            "guard": None,
            "valet": None,
            "engine": None,
            "lat": None,
            "lon": None,
        }

    async def async_invoke_signalr(
        self, method: str, arguments: list[Any], timeout: float = 10.0
    ) -> Any:
        """Отправка запроса через SignalR и ожидание ответа."""
        if not self._websocket:
            await self.async_connect_signalr()

        if not self._websocket:
            raise PrizrakAPIError("WebSocket не подключен")

        # Генерация уникального invocationId
        invocation_id = str(int(time.time() * 1000))

        # Создаём Future для ожидания ответа
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[invocation_id] = future

        try:
            # Формирование сообщения в формате SignalR
            message = {
                "arguments": arguments,
                "invocationId": invocation_id,
                "target": method,
                "type": 1,
            }

            # Отправка
            message_str = json.dumps(message) + "\u001e"
            await self._websocket.send(message_str)
            _LOGGER.debug("SignalR invoke отправлен: %s", method)

            # Ожидание ответа с таймаутом
            result = await asyncio.wait_for(future, timeout=timeout)
            return result

        except asyncio.TimeoutError:
            _LOGGER.warning("Таймаут ожидания ответа SignalR для %s", method)
            raise
        except websockets.exceptions.ConnectionClosed:
            _LOGGER.error("WebSocket закрыт при вызове %s", method)
            raise PrizrakAPIError("WebSocket соединение закрыто")
        finally:
            # Удаляем pending запрос
            self._pending_requests.pop(invocation_id, None)

    def update_device_state(self, device_id: int, state_data: dict[str, Any]) -> None:
        """Обновление кэшированного состояния устройства."""
        if device_id in self._device_states:
            self._device_states[device_id].update(state_data)
        else:
            self._device_states[device_id] = state_data

    def _get_bearer_token(self) -> str:
        """Получение Bearer токена для авторизации."""
        if not self._access_token:
            return ""
        return f"Bearer {json.dumps(self._access_token, separators=(',', ':'))}"

    async def async_connect_signalr(self) -> None:
        """Подключение к SignalR Hub."""
        try:
            if not self._access_token:
                await self.async_authenticate()

            # Negotiate запрос с Bearer токеном
            negotiate_url = f"{CONTROL_NEGOTIATE}?negotiateVersion=1"
            headers = {
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "X-SignalR-User-Agent": "Microsoft SignalR/7.0 (7.0.0; Unknown OS; Browser; Unknown Runtime Version)",
                "Authorization": self._get_bearer_token(),
            }

            async with self._session.post(negotiate_url, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error("Ошибка negotiate: %s, ответ: %s", response.status, error_text)
                    raise PrizrakAPIError(
                        f"Ошибка negotiate: статус {response.status}"
                    )
                negotiate_data = await response.json()
                self._connection_id = negotiate_data.get("connectionId")
                connection_token = negotiate_data.get("connectionToken")
                _LOGGER.debug("Получен connectionId: %s", self._connection_id)

            # Подключение к WebSocket
            # Используем connectionToken если он есть
            token_param = connection_token or self._connection_id
            access_token_str = json.dumps(self._access_token, separators=(',', ':'))
            access_token_encoded = urllib.parse.quote(access_token_str)
            ws_url = f"{CONTROL_WS}?id={token_param}&access_token={access_token_encoded}"

            # Создаём SSL context в executor чтобы избежать blocking call
            import ssl
            loop = asyncio.get_event_loop()
            ssl_context = await loop.run_in_executor(None, ssl.create_default_context)

            # Подключение к WebSocket
            self._websocket = await websockets.connect(ws_url, ssl=ssl_context)
            
            # Отправка SignalR handshake
            handshake_message = json.dumps({"protocol": "json", "version": 1}) + "\u001e"
            await self._websocket.send(handshake_message)
            _LOGGER.debug("Отправлен SignalR handshake")
            
            # Ожидание подтверждения handshake
            handshake_response = await asyncio.wait_for(self._websocket.recv(), timeout=5.0)
            _LOGGER.debug("Получен ответ handshake: %s", handshake_response)

            # Запуск задачи для прослушивания сообщений
            self._websocket_task = asyncio.create_task(self._websocket_listener())

            _LOGGER.debug("Подключение к SignalR установлено")

        except Exception as err:
            _LOGGER.error("Ошибка при подключении к SignalR: %s", err)
            raise PrizrakAPIError(f"Ошибка подключения SignalR: {err}") from err

    async def _websocket_listener(self) -> None:
        """Прослушивание сообщений от WebSocket."""
        try:
            if not self._websocket:
                return

            async for message in self._websocket:
                try:
                    # SignalR сообщения могут быть текстовыми или бинарными
                    if isinstance(message, bytes):
                        message = message.decode("utf-8")

                    # SignalR сообщения разделены символом \u001e
                    messages = message.split("\u001e")
                    for msg in messages:
                        if not msg.strip():
                            continue

                        data = json.loads(msg)
                        message_type = data.get("type")
                        
                        # Обработка ping сообщений (type 6)
                        if message_type == 6:
                            # Отвечаем на ping
                            await self._send_ping_response()
                            continue
                        
                        # Обработка ответов на invoke (type 3 - Completion)
                        if message_type == 3:
                            invocation_id = data.get("invocationId")
                            if invocation_id and invocation_id in self._pending_requests:
                                future = self._pending_requests[invocation_id]
                                if not future.done():
                                    result = data.get("result")
                                    error = data.get("error")
                                    if error:
                                        future.set_exception(PrizrakAPIError(error))
                                    else:
                                        future.set_result(result)
                            continue
                        
                        # Обработка уведомлений (type 1 - Invocation)
                        if message_type == 1:
                            target = data.get("target")
                            arguments = data.get("arguments", [])
                            _LOGGER.debug("SignalR уведомление: %s", target)
                            
                            # Обработка EventObject (телеметрия от WatchDevice)
                            if target == "EventObject":
                                for arg in arguments:
                                    device_id = arg.get("device_id")
                                    device_state = arg.get("device_state")
                                    if device_id and device_state:
                                        self.update_device_state(device_id, device_state)
                                        _LOGGER.debug("Обновлено состояние устройства %s", device_id)
                            
                            # Обработка обновлений состояния
                            elif target in ("DeviceStateUpdate", "StateUpdate", "DeviceUpdate"):
                                for arg in arguments:
                                    device_id = arg.get("device_id") or arg.get("id")
                                    if device_id:
                                        self.update_device_state(device_id, arg)

                        _LOGGER.debug("Получено сообщение от SignalR: %s", data)

                        # Вызов обработчиков сообщений
                        for handler in self._message_handlers:
                            try:
                                handler(data)
                            except Exception as handler_err:
                                _LOGGER.error(
                                    "Ошибка в обработчике сообщения: %s", handler_err
                                )

                except json.JSONDecodeError as err:
                    _LOGGER.warning("Не удалось распарсить сообщение: %s", err)
                except Exception as err:
                    _LOGGER.error("Ошибка при обработке сообщения: %s", err)

        except websockets.exceptions.ConnectionClosed:
            _LOGGER.debug("WebSocket соединение закрыто")
        except Exception as err:
            _LOGGER.error("Ошибка в websocket listener: %s", err)

    async def _send_ping_response(self) -> None:
        """Отправка ответа на ping."""
        if not self._websocket:
            return
        
        try:
            # Отправляем ping ответ (type 6)
            ping_message = json.dumps({"type": 6}) + "\u001e"
            await self._websocket.send(ping_message)
        except Exception as err:
            _LOGGER.debug("Ошибка при отправке ping ответа: %s", err)

    def add_message_handler(self, handler: Callable[[dict], None]) -> None:
        """Добавление обработчика сообщений от SignalR."""
        self._message_handlers.append(handler)

    async def async_send_signalr_command(
        self, method: str, arguments: list[Any]
    ) -> None:
        """Отправка команды через SignalR."""
        if not self._websocket:
            await self.async_connect_signalr()

        if not self._websocket:
            raise PrizrakAPIError("WebSocket не подключен")

        try:
            # Генерация уникального invocationId
            invocation_id = str(int(time.time() * 1000))

            # Формирование сообщения в формате SignalR
            message = {
                "arguments": arguments,
                "invocationId": invocation_id,
                "target": method,
                "type": 1,
            }

            # Отправка через WebSocket (формат с разделителем \u001e)
            message_str = json.dumps(message) + "\u001e"
            await self._websocket.send(message_str)
            _LOGGER.debug("Команда отправлена через SignalR: %s", method)

        except websockets.exceptions.ConnectionClosed:
            _LOGGER.error("WebSocket соединение закрыто при отправке команды")
            raise PrizrakAPIError("WebSocket соединение закрыто")
        except Exception as err:
            _LOGGER.error("Ошибка при отправке команды: %s", err)
            raise PrizrakAPIError(f"Ошибка отправки команды: {err}") from err

    async def async_disconnect(self) -> None:
        """Отключение от API."""
        if self._websocket_task:
            self._websocket_task.cancel()
            try:
                await self._websocket_task
            except asyncio.CancelledError:
                pass
            self._websocket_task = None

        if self._websocket:
            try:
                await self._websocket.close()
            except Exception as err:
                _LOGGER.debug("Ошибка при закрытии WebSocket: %s", err)
            self._websocket = None

        _LOGGER.debug("Отключение от API выполнено")

