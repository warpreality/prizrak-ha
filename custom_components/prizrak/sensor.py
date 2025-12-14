"""Sensors для интеграции Призрак."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTemperature,
)

# UnitOfVoltage может отсутствовать в некоторых версиях HA
try:
    from homeassistant.const import UnitOfVoltage
except ImportError:
    class UnitOfVoltage:
        VOLT = "V"
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_AUTOLAUNCH_TIME,
    ATTR_BALANCE,
    ATTR_FUEL,
    ATTR_MILEAGE,
    ATTR_RPM,
    ATTR_SPEED,
    ATTR_TEMPERATURE_ENGINE,
    ATTR_TEMPERATURE_INTERIOR,
    ATTR_TEMPERATURE_OUTSIDE,
    ATTR_VOLTAGE,
    DOMAIN,
)
from .coordinator import PrizrakDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка sensors из конфигурации."""
    coordinator: PrizrakDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = [
        PrizrakStateSensor(coordinator),
        PrizrakBalanceSensor(coordinator),
        PrizrakTemperatureOutsideSensor(coordinator),
        PrizrakTemperatureEngineSensor(coordinator),
        PrizrakTemperatureInteriorSensor(coordinator),
        PrizrakVoltageSensor(coordinator),
        PrizrakRPMSensor(coordinator),
        PrizrakFuelSensor(coordinator),
        PrizrakSpeedSensor(coordinator),
        PrizrakMileageSensor(coordinator),
        PrizrakAutolaunchTimeSensor(coordinator),
    ]

    async_add_entities(sensors)


class PrizrakSensor(CoordinatorEntity, SensorEntity):
    """Базовый класс для sensors Призрак."""

    def __init__(
        self,
        coordinator: PrizrakDataUpdateCoordinator,
        key: str,
        name: str,
        icon: str | None = None,
    ) -> None:
        """Инициализация sensor."""
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


class PrizrakStateSensor(PrizrakSensor):
    """Sensor состояния автомобиля."""

    def __init__(self, coordinator: PrizrakDataUpdateCoordinator) -> None:
        """Инициализация sensor состояния."""
        super().__init__(coordinator, "state", "Состояние", "mdi:car-lock")

    @property
    def native_value(self) -> str | None:
        """Текущее состояние."""
        return self.coordinator.data.get("state")


class PrizrakBalanceSensor(PrizrakSensor):
    """Sensor баланса счета."""

    def __init__(self, coordinator: PrizrakDataUpdateCoordinator) -> None:
        """Инициализация sensor баланса."""
        super().__init__(coordinator, ATTR_BALANCE, "Баланс", "mdi:currency-rub")
        self._attr_native_unit_of_measurement = "₽"

    @property
    def native_value(self) -> float | None:
        """Текущий баланс."""
        return self.coordinator.data.get(ATTR_BALANCE)


class PrizrakTemperatureOutsideSensor(PrizrakSensor):
    """Sensor температуры за бортом."""

    def __init__(self, coordinator: PrizrakDataUpdateCoordinator) -> None:
        """Инициализация sensor температуры."""
        super().__init__(
            coordinator,
            ATTR_TEMPERATURE_OUTSIDE,
            "Температура за бортом",
            "mdi:thermometer",
        )
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> float | None:
        """Текущая температура."""
        return self.coordinator.data.get(ATTR_TEMPERATURE_OUTSIDE)


class PrizrakTemperatureEngineSensor(PrizrakSensor):
    """Sensor температуры двигателя."""

    def __init__(self, coordinator: PrizrakDataUpdateCoordinator) -> None:
        """Инициализация sensor температуры двигателя."""
        super().__init__(
            coordinator,
            ATTR_TEMPERATURE_ENGINE,
            "Температура двигателя",
            "mdi:engine",
        )
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> float | None:
        """Текущая температура двигателя."""
        return self.coordinator.data.get(ATTR_TEMPERATURE_ENGINE)


class PrizrakTemperatureInteriorSensor(PrizrakSensor):
    """Sensor температуры в салоне."""

    def __init__(self, coordinator: PrizrakDataUpdateCoordinator) -> None:
        """Инициализация sensor температуры в салоне."""
        super().__init__(
            coordinator,
            ATTR_TEMPERATURE_INTERIOR,
            "Температура в салоне",
            "mdi:car-seat-heater",
        )
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> float | None:
        """Текущая температура в салоне."""
        return self.coordinator.data.get(ATTR_TEMPERATURE_INTERIOR)


class PrizrakVoltageSensor(PrizrakSensor):
    """Sensor напряжения аккумулятора."""

    def __init__(self, coordinator: PrizrakDataUpdateCoordinator) -> None:
        """Инициализация sensor напряжения."""
        super().__init__(
            coordinator, ATTR_VOLTAGE, "Напряжение", "mdi:battery"
        )
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_native_unit_of_measurement = UnitOfVoltage.VOLT

    @property
    def native_value(self) -> float | None:
        """Текущее напряжение."""
        return self.coordinator.data.get(ATTR_VOLTAGE)


class PrizrakRPMSensor(PrizrakSensor):
    """Sensor оборотов двигателя."""

    def __init__(self, coordinator: PrizrakDataUpdateCoordinator) -> None:
        """Инициализация sensor оборотов."""
        super().__init__(coordinator, ATTR_RPM, "Обороты", "mdi:gauge")
        self._attr_native_unit_of_measurement = "об/м"

    @property
    def native_value(self) -> int | None:
        """Текущие обороты."""
        return self.coordinator.data.get(ATTR_RPM)


class PrizrakFuelSensor(PrizrakSensor):
    """Sensor уровня топлива."""

    def __init__(self, coordinator: PrizrakDataUpdateCoordinator) -> None:
        """Инициализация sensor топлива."""
        super().__init__(coordinator, ATTR_FUEL, "Топливо", "mdi:fuel")
        self._attr_native_unit_of_measurement = "л"

    @property
    def native_value(self) -> float | None:
        """Текущий уровень топлива."""
        return self.coordinator.data.get(ATTR_FUEL)


class PrizrakSpeedSensor(PrizrakSensor):
    """Sensor скорости."""

    def __init__(self, coordinator: PrizrakDataUpdateCoordinator) -> None:
        """Инициализация sensor скорости."""
        super().__init__(coordinator, ATTR_SPEED, "Скорость", "mdi:speedometer")
        self._attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR

    @property
    def native_value(self) -> int | None:
        """Текущая скорость."""
        return self.coordinator.data.get(ATTR_SPEED)


class PrizrakMileageSensor(PrizrakSensor):
    """Sensor пробега."""

    def __init__(self, coordinator: PrizrakDataUpdateCoordinator) -> None:
        """Инициализация sensor пробега."""
        super().__init__(coordinator, ATTR_MILEAGE, "Пробег", "mdi:counter")
        self._attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    @property
    def native_value(self) -> int | None:
        """Текущий пробег."""
        return self.coordinator.data.get(ATTR_MILEAGE)


class PrizrakAutolaunchTimeSensor(PrizrakSensor):
    """Sensor времени автозапуска."""

    def __init__(self, coordinator: PrizrakDataUpdateCoordinator) -> None:
        """Инициализация sensor времени автозапуска."""
        super().__init__(
            coordinator, ATTR_AUTOLAUNCH_TIME, "Время автозапуска", "mdi:timer"
        )

    @property
    def native_value(self) -> str | None:
        """Текущее время автозапуска."""
        return self.coordinator.data.get(ATTR_AUTOLAUNCH_TIME)

