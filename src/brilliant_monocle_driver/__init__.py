import asyncio
import datetime
import logging
from bleak import BleakScanner, BleakClient
from .batched import batched

__version__ = "0.1.1"

class MonocleException(Exception):
    pass

class Monocle:
    logger = logging.getLogger(__name__)
    def get_logger():
        return logger

    def __init__(self, notify_callback, address=None):
        """
        Prepares a Monocle for connection. Specify a callback and optional
        address to connect to.

        Raises MonocleException if callback not provided.
        """

        if notify_callback is None:
            raise MonocleException("Must provide a notification callback")

        self.client = None
        self.out_channel = None
        self.in_channel = None
        self.mtu_size = None
        self.connected = False
        self.address = address
        self.notify_callback = notify_callback

    def _on_notify(self, channel, bytes_in):
        """Internal handler for dispatching notifications to the notify_callback."""
        self.notify_callback(channel, bytes_in.decode("utf-8"))


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
        self.mtu_size = client.mtu_size
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
        self.mtu_size = None
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

        # Ctrl-C to terminate any previously-running code, then
        # need to wrap input in CTRL-A / CTRL-D to get into raw repl mode and
        # execute the content.
        input = '\x03\x01' + input + '\x04'

        buffer = input.encode()

        batch_count = 1
        for chunk in batched(buffer, self.mtu_size - 4):
            Monocle.logger.info("Sending batch {}".format(batch_count))
            batch_count += 1
            await self.client.write_gatt_char(self.out_channel, chunk)



