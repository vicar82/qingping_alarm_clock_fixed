import asyncio
import logging
import time
from datetime import time as dtime

from bleak import BleakClient, BleakError
from bleak_retry_connector import (
    establish_connection,
    BleakClientWithServiceCache,
    BleakNotFoundError,
    BleakOutOfConnectionSlotsError,
    BleakAbortedError,
    BleakConnectionError,
)

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.components.bluetooth import (
    async_ble_device_from_address
)

from .configuration import Configuration, Language
from .util import updates_configuration
from .alarm import Alarm, AlarmDay
from .eventbus import EventBus
from .exceptions import NotConnectedError
from ..const import (
    ALARM_SLOTS_COUNT,
    DISCONNECT_DELAY,
    CONNECTION_TIMEOUT,
    RETRY_INTERVAL
)
from .events import (
    DEVICE_CONNECT,
    DEVICE_DISCONNECT,
    DEVICE_CONFIG_UPDATE,
    ALARMS_UPDATE
)

_LOGGER = logging.getLogger(__name__)

MAIN_CHAR       = "00000001-0000-1000-8000-00805f9b34fb"
CFG_WRITE_CHAR  = "0000000B-0000-1000-8000-00805f9b34fb"
CFG_READ_CHAR   = "0000000C-0000-1000-8000-00805f9b34fb"

AUTH_STEP_1 = bytes.fromhex("1101ea600e964287ea7d17894900da6174bd")
AUTH_STEP_2 = bytes.fromhex("1102ea600e964287ea7d17894900da6174bd")


class Qingping:
    def __init__(self, hass: HomeAssistant, mac: str, name: str):
        """Initialize the Qingping CGD1 Alarm Clock."""
        self.hass = hass
        self.mac = mac
        self.name = name

        self.client = None
        self.configuration = None
        self.alarms: list[Alarm] = []
        self.eventbus = EventBus()

        self._connect_lock = asyncio.Lock()
        self._configuration_event = asyncio.Event()
        self._alarms_event = asyncio.Event()
        self._highest_alarm_index_seen = -1
        self._disconnect_task = None

    async def connect(self) -> bool:
        async with self._connect_lock:
            if self.client and self.client.is_connected:
                return True

            device = async_ble_device_from_address(self.hass, self.mac, connectable=True)
            if device is None:
                _LOGGER.error("No adapters can reach the device with address %s", self.mac)
                return False

            _LOGGER.debug("Connecting to %s...", self.mac)
            try:
                self.client = await establish_connection(
                    BleakClientWithServiceCache,
                    device,
                    self.name or self.mac,
                    disconnected_callback=self._on_disconnect,
                    max_attempts=3,
                )
            except (BleakNotFoundError, BleakOutOfConnectionSlotsError,
                    BleakAbortedError, BleakConnectionError, asyncio.TimeoutError) as exc:
                _LOGGER.debug("Failed to connect to %s: %s", self.mac, exc)
                return False
            except Exception as exc:
                _LOGGER.exception("Unexpected error connecting to %s: %s", self.mac, exc)
                return False

            _LOGGER.debug("Connected to %s, authenticating...", self.mac)

            try:
                # Step 1 auth
                await self._write_main_char(AUTH_STEP_1)
                await asyncio.sleep(0.2)

                # Step 2 auth
                await self._write_main_char(AUTH_STEP_2)
                await asyncio.sleep(0.5)

                self.eventbus.send(DEVICE_CONNECT, self)

                # Read configuration
                _LOGGER.debug("Reading configuration...")
                await self.client.start_notify(CFG_READ_CHAR, self._notification_handler)
                await self.get_configuration()

                # Read alarms (non-fatal if the device does not return them)
                _LOGGER.debug("Reading alarms...")
                try:
                    await self.get_alarms()
                except NotConnectedError as exc:
                    _LOGGER.warning(
                        "Could not read alarms from %s: %s. "
                        "You can still use the device, but alarm management may be limited.",
                        self.mac, exc
                    )
                    self.alarms = []
            except Exception as exc:
                _LOGGER.exception("Failed to initialize %s after connection: %s", self.mac, exc)
                await self.disconnect()
                return False

            return True

    async def connect_if_needed(self) -> bool:
        if not self.client or not self.client.is_connected or \
                not self.configuration or self.configuration.is_expired:
            return await self.connect()

        return False

    async def disconnect(self) -> bool:
        if self._disconnect_task is not None:
            self._disconnect_task.cancel()
            self._disconnect_task = None

        if self.client and self.client.is_connected:
            _LOGGER.debug("Disconnecting from %s...", self.mac)
            try:
                await self.client.disconnect()
            except Exception as exc:
                _LOGGER.debug("Failed to disconnect from %s: %s", self.mac, exc)

        self.client = None
        return True

    async def delayed_disconnect(self):
        try:
            await asyncio.sleep(DISCONNECT_DELAY)
            await self.disconnect()
            _LOGGER.debug("Disconnected from %s", self.mac)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            _LOGGER.debug("Failed to disconnect. Error: %s", exc)

    async def get_configuration(self):
        if not self.client or not self.client.is_connected:
            raise NotConnectedError("Not connected")

        self._configuration_event.clear()
        await self._write_config(b"\x01\x02")
        try:
            await asyncio.wait_for(self._configuration_event.wait(), CONNECTION_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise NotConnectedError("Timeout waiting for configuration") from exc

    async def set_configuration(self, configuration: Configuration):
        await self._write_config(configuration.to_bytes())
        await self.get_configuration()

    async def set_time(self, timestamp: int, timezone_offset: int | None = None):
        start_time = time.time()

        await self._ensure_connected()
        await self._ensure_configuration()

        # Account for time passed while connecting
        timestamp = int(timestamp + (time.time() - start_time))

        timestamp_bytes = self._get_timestamp_bytes(timestamp)
        await self._write_main_char(timestamp_bytes)

        if timezone_offset is not None and \
            self.configuration.timezone_offset != timezone_offset:

            self.configuration.timezone_offset = timezone_offset
            await self.set_configuration(self.configuration)

    async def get_alarms(self):
        if not self.client or not self.client.is_connected:
            raise NotConnectedError("Not connected")

        self.alarms = []
        self._highest_alarm_index_seen = -1
        self._alarms_event.clear()
        await self._write_config(b"\x01\x06")
        try:
            await asyncio.wait_for(self._alarms_event.wait(), CONNECTION_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise NotConnectedError("Timeout waiting for alarms") from exc

    async def set_alarm(
        self,
        slot: int,
        is_enabled: bool | None,
        time: dtime | None,
        days: set[AlarmDay] | None,
        snooze: bool | None
    ) -> bool:
        await self._ensure_alarms()
        await self._ensure_connected()

        if 0 <= slot < ALARM_SLOTS_COUNT:
            alarm: Alarm = self.alarms[slot]
            if not alarm.is_configured:
                if time is None:
                    raise ServiceValidationError("Alarm time is required for a new alarm.")
                alarm.time = time
                alarm.days = days if days is not None else set()
                alarm.is_enabled = is_enabled if is_enabled is not None else True
                alarm.snooze = snooze if snooze is not None else True
            else:
                if is_enabled is not None:
                    alarm.is_enabled = is_enabled
                if time is not None:
                    alarm.time = time
                if days is not None:
                    alarm.days = days
                if snooze is not None:
                    alarm.snooze = snooze

            await self._write_config(alarm.to_bytes())
            try:
                await self.get_alarms()
            except NotConnectedError:
                _LOGGER.warning("Alarm written, but could not refresh alarm list from %s", self.mac)
            return True

        return False

    async def delete_alarm(self, slot: int) -> bool:
        await self._ensure_alarms()
        await self._ensure_connected()

        if 0 <= slot < ALARM_SLOTS_COUNT:
            alarm: Alarm = self.alarms[slot]
            alarm.deactivate()

            if self.client and self.client.is_connected:
                await self._write_config(alarm.to_bytes())
                try:
                    await self.get_alarms()
                except NotConnectedError:
                    _LOGGER.warning("Alarm deleted, but could not refresh alarm list from %s", self.mac)
                return True
            else:
                raise NotConnectedError("Not connected")

        return False

    @updates_configuration
    async def enable_alarms(self, is_enabled: bool):
        self.configuration.alarms_on = is_enabled
        await self._write_config(self.configuration.to_bytes())

    @updates_configuration
    async def set_sound_volume(self, volume: int):
        self.configuration.sound_volume = volume
        await self._write_config(self.configuration.to_bytes())
        await self._write_config(b"\x01\x04")

    @updates_configuration
    async def set_screen_light_time(self, _time: int):
        self.configuration.screen_light_time = _time
        await self._write_config(self.configuration.to_bytes())

    @updates_configuration
    async def set_daytime_brightness(self, brightness: int):
        self.configuration.daytime_brightness = brightness
        await self._write_config(self.configuration.to_bytes())
        await self._write_config(bytes([0x02, 0x03, brightness//10]))

    @updates_configuration
    async def set_nighttime_brightness(self, brightness: int):
        self.configuration.nighttime_brightness = brightness
        await self._write_config(self.configuration.to_bytes())
        await self._write_config(bytes([0x02, 0x03, brightness//10]))

    @updates_configuration
    async def set_nighttime_start_time(self, _time: dtime):
        self.configuration.night_time_start_time = _time
        await self._write_config(self.configuration.to_bytes())

    @updates_configuration
    async def set_nighttime_end_time(self, _time: dtime):
        self.configuration.night_time_end_time = _time
        await self._write_config(self.configuration.to_bytes())

    @updates_configuration
    async def set_night_mode(self, is_night_mode: bool):
        self.configuration.night_mode_enabled = is_night_mode
        await self._write_config(self.configuration.to_bytes())

    @updates_configuration
    async def set_language(self, language: Language):
        self.configuration.language = language
        await self._write_config(self.configuration.to_bytes())

    @updates_configuration
    async def set_24h_time_format(self, is_24h: bool):
        self.configuration.use_24h_format = is_24h
        await self._write_config(self.configuration.to_bytes())

    @updates_configuration
    async def set_uses_celsius(self, is_celsius: bool):
        self.configuration.use_celsius = is_celsius
        await self._write_config(self.configuration.to_bytes())

    async def _ensure_connected(self):
        if self.client and self.client.is_connected:
            return

        for attempt in range(3):
            if await self.connect():
                return
            _LOGGER.debug("Connection attempt %d failed, retrying...", attempt + 1)
            await asyncio.sleep(RETRY_INTERVAL)

        raise NotConnectedError("Connection timeout")

    async def _ensure_configuration(self):
        if not self.configuration or self.configuration.is_expired:
            await self._ensure_connected()
            await self.get_configuration()

    async def _ensure_alarms(self):
        if self.alarms:
            return

        await self._ensure_connected()
        try:
            await self.get_alarms()
        except NotConnectedError:
            _LOGGER.warning(
                "Failed to read alarms from %s; creating empty alarm placeholders.",
                self.mac
            )
            self.alarms = [
                Alarm(slot, bytes.fromhex("ffffffffff"))
                for slot in range(ALARM_SLOTS_COUNT)
            ]
            self.eventbus.send(ALARMS_UPDATE, self.alarms)

    async def _write_config(self, data: bytes):
        await self._write_with_retry(CFG_WRITE_CHAR, data)

    async def _write_main_char(self, data: bytes):
        await self._write_with_retry(MAIN_CHAR, data)

    async def _write_with_retry(self, uuid: str, data: bytes):
        if not self.client or not self.client.is_connected:
            raise NotConnectedError("Not connected")

        try:
            await self._write_gatt_char(uuid, data)
        except (BleakError, asyncio.TimeoutError) as exc:
            _LOGGER.warning("Write to %s failed (%s), reconnecting and retrying once...", uuid, exc)
            await self.disconnect()
            await self._ensure_connected()
            await self._write_gatt_char(uuid, data)

        if self._disconnect_task is not None:
            self._disconnect_task.cancel()
        self._disconnect_task = asyncio.get_running_loop().create_task(
            self.delayed_disconnect()
        )

    async def _write_gatt_char(self, uuid: str, data: bytes):
        if not self.client or not self.client.is_connected:
            raise NotConnectedError("Not connected")

        _LOGGER.debug(">> %s: %s", uuid, data.hex())
        try:
            await asyncio.wait_for(
                self.client.write_gatt_char(uuid, data),
                timeout=10.0
            )
        except asyncio.TimeoutError as exc:
            _LOGGER.warning("Timeout writing to %s", uuid)
            raise

    def _get_timestamp_bytes(self, timestamp: int):
        timestamp_bytes = [0] * 6
        timestamp_bytes[0] = 0x05
        timestamp_bytes[1] = 0x09
        timestamp_bytes[2] = (timestamp >> 0) & 0xFF
        timestamp_bytes[3] = (timestamp >> 8) & 0xFF
        timestamp_bytes[4] = (timestamp >> 16) & 0xFF
        timestamp_bytes[5] = (timestamp >> 24) & 0xFF

        return bytes(timestamp_bytes)

    async def _notification_handler(self, sender, data):
        if sender.uuid.lower() == CFG_READ_CHAR.lower():
            _LOGGER.debug("<< %s: %s", sender.uuid, data.hex())
            if data[0] == 0x13 and data[1] in (0x01, 0x02):
                _LOGGER.debug("Got configuration bytes: %s", data.hex())
                self.configuration = Configuration(data)

                self._configuration_event.set()
                self.eventbus.send(DEVICE_CONFIG_UPDATE, self.configuration)
            elif data.startswith(b"\x11\x06") and len(data) >= 8:
                _LOGGER.debug("Got alarms bytes: %s", data.hex())
                slot_offset = data[2]
                if slot_offset == 0:
                    self.alarms = []
                    self._highest_alarm_index_seen = -1

                offset = 3
                current_index = slot_offset
                while offset + 5 <= len(data):
                    self.alarms.append(Alarm(current_index, data[offset:offset + 5]))
                    self._highest_alarm_index_seen = current_index
                    offset += 5
                    current_index += 1

                if self._highest_alarm_index_seen >= ALARM_SLOTS_COUNT - 1:
                    self._alarms_event.set()
                    self.eventbus.send(ALARMS_UPDATE, self.alarms)

    def _on_disconnect(self, client: BleakClient):
        if self._disconnect_task is not None:
            self._disconnect_task.cancel()
            self._disconnect_task = None

        self.client = None
        self.eventbus.send(DEVICE_DISCONNECT, self)
