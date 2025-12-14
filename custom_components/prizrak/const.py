"""Константы для интеграции Призрак."""

DOMAIN = "prizrak"

# Конфигурация
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_PUK_CODE = "puk_code"
CONF_DEVICE_ID = "device_id"

# API endpoints
BASE_URL = "https://monitoring.tecel.ru"
API_BASE = f"{BASE_URL}/api"
PASSPORT_API = f"{BASE_URL}/passport/api"
CONTROL_NEGOTIATE = f"{API_BASE}/Control/negotiate"
CONTROL_WS = "wss://monitoring.tecel.ru/api/Control"

# SignalR методы - получение данных
SIGNALR_GET_DEVICES = "GetDevices"
SIGNALR_GET_DEVICE_INFO = "GetDeviceInfoTp"
SIGNALR_SET_CONNECTION_ACTIVITY = "SetConnectionActivity"
SIGNALR_WATCH_DEVICE = "WatchDevice"

# SignalR методы - управление
SIGNALR_GUARD_ON = "GuardOn"
SIGNALR_GUARD_OFF = "GuardOff"
SIGNALR_AUTOLAUNCH_ON = "AutolaunchOn"
SIGNALR_AUTOLAUNCH_OFF = "AutolaunchOff"
SIGNALR_VALET_ON = "ValetOn"
SIGNALR_VALET_OFF = "ValetOff"
SIGNALR_ALARM_ON = "AlarmOn"
SIGNALR_ALARM_OFF = "AlarmOff"
SIGNALR_GSM_BLOCK_ON = "GsmBlockOn"
SIGNALR_GSM_BLOCK_OFF = "GsmBlockOff"
SIGNALR_HEATER_ON = "HeaterOn"
SIGNALR_HEATER_OFF = "HeaterOff"
SIGNALR_PREHEAT_ON = "PreHeatOn"
SIGNALR_PREHEAT_OFF = "PreHeatOff"
SIGNALR_FAN_ON = "FanOn"
SIGNALR_FAN_OFF = "FanOff"
SIGNALR_SEASONAL_COMFORT_ON = "SeasonalComfortOn"
SIGNALR_SEASONAL_COMFORT_OFF = "SeasonalComfortOff"
SIGNALR_PARKING_SEARCH_ON = "ParkingSearchOn"
SIGNALR_PARKING_SEARCH_OFF = "ParkingSearchOff"
SIGNALR_VIDEO_RECORDER_ON = "VideoRecorderOn"
SIGNALR_VIDEO_RECORDER_OFF = "VideoRecorderOff"

# Состояния
STATE_ARMED = "В охране"
STATE_DISARMED = "Снято с охраны"
STATE_SERVICE_MODE = "Сервисный режим"
STATE_NO_MOVEMENT = "Без движения"
STATE_AUTOLAUNCH_ON = "Автозапуск вкл."

# Атрибуты
ATTR_BALANCE = "balance"
ATTR_TEMPERATURE_OUTSIDE = "temperature_outside"
ATTR_TEMPERATURE_ENGINE = "temperature_engine"
ATTR_TEMPERATURE_INTERIOR = "temperature_interior"
ATTR_VOLTAGE = "voltage"
ATTR_RPM = "rpm"
ATTR_FUEL = "fuel"
ATTR_SPEED = "speed"
ATTR_MILEAGE = "mileage"
ATTR_AUTOLAUNCH_TIME = "autolaunch_time"

# Интервалы обновления
UPDATE_INTERVAL = 30  # секунды
SIGNALR_PING_INTERVAL = 15  # секунды

