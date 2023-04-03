# Copyright 2023 Mark T. Tomczak
# License at https://github.com/fixermark/brilliant-monocle-driver-python/blob/main/LICENSE

import asyncio
import datetime
import itertools
import logging
from bleak import BleakScanner, BleakClient
from .batched import batched
from .line_reader import LineReader

__version__ = "0.1.3"

TOUCH_CALLBACK_COMMAND = """
import touch
touch.callback(touch.A, lambda x: print("[EVENT:touch-A]"))
touch.callback(touch.B, lambda x: print("[EVENT:touch-B]"))
"""


class MonocleException(Exception):
    pass

class Monocle:
    # MTU size. Set this to a different value if you find
    # difficulty connecting to the Monocle consistently.
    #
    # 23 is the default, but Monocle sould support 128
    MTU_SIZE = 128
    logger = logging.getLogger(__name__)

    def get_logger():
        """Access the logger for Monocles"""
        return Monocle.logger

    def __init__(self, notify_callback=None, address=None):
        """
        Prepares a Monocle for connection. Specify an optional callback and optional
        address to connect to.
        """

        self.client = None
        self.out_channel = None
        self.in_channel = None
        self.connected = False
        self.address = address
        self.notify_callback = notify_callback
        self.line_reader = LineReader('\r\n')
        self.line_listeners = {}
        self.next_line_listener_id = itertools.count(1,1)

        self.touch_events_installed = False
        self.a_callback = None
        self.b_callback = None

    def add_line_listener(self, line_listener):
        """
        Adds a callback to fire when a full line is received from the device.

        Returns a token that can be passed to remove_line_listener to remove this callback.
        """
        listener_id = next(self.next_line_listener_id)
        Monocle.logger.info("Installing line listener id {}".format(listener_id))

        self.line_listeners[listener_id] = line_listener
        return listener_id

    def remove_line_listener(self, token):
        """
        Remove the line listener corresponding to the token
        """
        Monocle.logger.info("Removing line listener id {}".format(token))
        del self.line_listeners[token]

    async def connect(self):
        """
        Connect to the only monocle available, or the monocle at address if
        one was provided.

        Raises MonocleException if no monocle is found at the address, no
        monocles (or too many monocles) are found when no address is provided,
        or a connection error occurs.
        """
        address_to_connect = self.address
        if address_to_connect is None:
            address_to_connect = await self._find_address_of_monocle()

        client, rx_characteristic, tx_characteristic = await self._get_uart(address_to_connect)

        await client.start_notify(tx_characteristic, self._on_notify)

        self.client = client
        self.out_channel = rx_characteristic
        self.in_channel = tx_characteristic
        self.address = address_to_connect
        Monocle.logger.info("Connected {}".format(self.address))
        self.connected = True

    async def disconnect(self):
        """
        Disconnect from monocle, if connected.
        """
        if not self.connected:
            return

        await self.client.disconnect()
        Monocle.logger.info("Disconnected {}".format(self.address))
        self.client = None
        self.out_channel = None
        self.in_channel = None
        self.connected = False

    async def __aenter__(self):
        await self.connect()

    async def __aexit__(self, exc_type, exc, tb):
        await self.disconnect()

    async def _get_uart(self, address):
        """
        Get UART endpoints for the monocle at address

        Raises MonocleException if no UART endpoints can be found.

        Returns the BLE client, rx, and tx endpoints
        """
        client = BleakClient(address)
        await client.connect()
        Monocle.logger.info("Finding UART channel for {}...".format(address))

        uart_service = None
        tx_characteristic = None
        rx_characteristic = None
        for service in client.services:
            if service.description == "Nordic UART Service":
                uart_service = service

        if uart_service is None:
            raise MonocleException("No UART service found at {}".format(address))

        Monocle.logger.info("Found UART service.")

        for characteristic in uart_service.characteristics:
            if characteristic.description == "Nordic UART TX":
                tx_characteristic = characteristic
            if characteristic.description == "Nordic UART RX":
                rx_characteristic = characteristic

        if tx_characteristic is None:
            raise MonocleException("Unable to find TX characteristic at {}".format(
                address))
        if rx_characteristic is None:
            raise MonocleExcpetion("Unable to find RX characteristic at {}".format(
                    address))

        return client, rx_characteristic, tx_characteristic

    async def _find_address_of_monocle(self):
        """
        Finds the address of one monocle. Raises an exception if zero or more than one are found.
        """
        Monocle.logger.info("Scanning for devices...")
        devices = await BleakScanner.discover()
        monocles = [device for device in devices if device.name == "monocle"]
        if len(monocles) != 1:
            raise MonocleException("Expected 1 device, found {}".format(len(monocles)))
        return monocles[0].address


    async def send(self, input):
        """
        Send a string to the client.

        Raises exception if Monocle not connected.
        """
        if not self.connected:
            raise MonocleException("Monocle is not connected.")

        input = input.replace("\n", "\r\n")

        mtu_size = Monocle.MTU_SIZE
        Monocle.logger.info("MTU size is {}".format(mtu_size))

        # Ctrl-C to terminate any previously-running code, then
        # need to wrap input in CTRL-A / CTRL-D to get into raw repl mode and
        # execute the content.
        input = '\x03\x01' + input + '\x04'

        buffer = input.encode()

        batch_count = 1
        for chunk in batched(buffer, mtu_size - 3):
            Monocle.logger.info("Sending batch {}".format(batch_count))
            batch_count += 1
            await self.client.write_gatt_char(self.out_channel, chunk)

    async def install_touch_events(self):
        """
        Installs touch detectors. This enables touch callbacks (and replaces
        any `touch.callback` values set on the Monocle).

        note that setting any new `touch.callback` configurations will
        break the touch detectors; call `install_touch_events` again to
        restore them.
        """

        if not self.touch_events_installed:
            self.touch_events_installed = True
            self.add_line_listener(self._touch_line_listener)

        await self.send(TOUCH_CALLBACK_COMMAND)

    def set_a_touch_callback(self, a_callback):
        """
        Sets the touch callback for A taps
        """
        self.a_callback = a_callback

    def set_b_touch_callback(self, b_callback):
        """
        Sets the touch callback for B taps
        """
        self.b_callback = b_callback

    def _on_notify(self, channel, bytes_in):
        """Internal handler for dispatching notifications to the notify_callback."""
        text_in = bytes_in.decode("utf-8")
        Monocle.logger.info("Notify: <<{}>>".format(text_in))
        if self.notify_callback is not None:
            self.notify_callback(channel, text_in)

        self.line_reader.input(text_in)

        for line in self.line_reader.get_lines():
            for listener in self.line_listeners.values():
                listener(line)

    def _touch_line_listener(self, line):
        """Internal line listener to watch for A and B touch events."""
        if "[EVENT:touch-A]" in line and self.a_callback is not None:
            self.a_callback()
        if "[EVENT:touch-B]" in line and self.b_callback is not None:
            self.b_callback()

