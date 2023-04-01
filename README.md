# Brilliant Monocle Driver

`brilliant-monocle-driver` is a simple Python library that uses
[Bleak](https://github.com/hbldh/bleak) to connect to and control a [Brilliant Labs Monocle](https://www.brilliantmonocle.com/) display device.

# Install

`pip install brilliant-monocle-driver`


# Usage example

``` Python
import asyncio
from brilliant_monocle_driver import Monocle

def callback(channel, text_in):
  """
  Callback to handle incoming text from the Monocle.
  """
  print(text_in)

# Simple MicroPython command that prints battery level for five seconds
# and then blanks the screen
COMMAND = """
import display
import device
import time

def show_battery(count):
  batLvl = str(device.battery_level())
  display.fill(0x000066)
  display.text("bat: {} {}".format(batLvl, count), 5, 5, 0xffffff)
  display.show()

count = 0
while (count < 5):
  show_battery(count)
  time.sleep(1)
  count += 1

display.fill(0x000000)
display.show()

print("Done")

"""

async def execute():
    mono = Monocle(callback)
    async with mono:
        await mono.send(COMMAND)

asyncio.run(execute())

```

# Details

`brilliant-monocle-driver` attaches to a Monocle via the UART characteristics exposed over
BLE in Monocle's default firmware, as specified in the
[Monocle documentation](https://docs.brilliantmonocle.com/micropython/micropython/#under-the-hood). Once
connection is established, commands can be sent directly to the Monocle as
MicroPython. The driver avoids MTU overflow and does some convenience /
correction massaging (sending `Ctrl-C` to stop any running command and wrapping
the incoming command in `Ctrl-A | Ctrl-D` to avoid interference from the REPL's
echo and auto-formatting convenience behaviors).

