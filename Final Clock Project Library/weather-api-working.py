#Weather API Code

# SPDX-FileCopyrightText: 2020 John Park for Adafruit Industries
#
# SPDX-License-Identifier: MIT

# Metro Matrix Clock
# Runs on Airlift Metro M4 with 64x32 RGB Matrix display & shield

import time
import board
import displayio
import terminalio
from adafruit_display_text.label import Label
from adafruit_bitmap_font import bitmap_font
from adafruit_matrixportal.matrix import Matrix

# Wifi Imports
from os import getenv
import busio
from digitalio import DigitalInOut
import adafruit_connection_manager
import adafruit_requests
from adafruit_esp32spi import adafruit_esp32spi

# Time Imports
import adafruit_ntp
import rtc

# Picture Imports
import openweather_graphics

BLINK = True
DEBUG = False

# Get WiFi details and more from a secrets.py file
try:
    from secrets import secrets
except ImportError:
    print("WiFi secrets are kept in secrets.py, please add them there!")
    raise
print("    Metro Minimal Clock")

# WiFi Setup
ssid = secrets["ssid"]
password = secrets["password"]

esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)
spi = busio.SPI(board.SCK, board.MOSI, board.MISO)

esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

# Create a socket pool
pool = adafruit_connection_manager.get_radio_socketpool(esp)
requests = adafruit_requests.Session(pool)

# Ensure WiFi connection
while not esp.is_connected:
    try:
        esp.connect_AP(ssid, password)
        print("Connected to WiFi!")
    except OSError as e:
        print("Could not connect to AP, retrying: ", e)
        continue

# NTP Time Sync
ntp = adafruit_ntp.NTP(pool, tz_offset=-4, cache_seconds=3600)
print("Current time:", ntp.datetime)

# --- Display setup ---
matrix = Matrix()
display = matrix.display

# --- Drawing setup ---
group = displayio.Group()
bitmap = displayio.Bitmap(64, 32, 2)
color = displayio.Palette(4)
color[0] = 0x000000  # black background
color[1] = 0xFF0000  # red
color[2] = 0xCC4000  # amber
color[3] = 0x85FF00  # greenish

tile_grid = displayio.TileGrid(bitmap, pixel_shader=color)
group.append(tile_grid)
display.root_group = group

UNITS = "imperial"
LOCATION = "Boston, US"
print(f"Getting weather for {LOCATION}")

# OpenWeather API Setup
DATA_SOURCE = (
    "http://api.openweathermap.org/data/2.5/weather?q=" + LOCATION + "&units=" + UNITS
)
DATA_SOURCE += "&appid=" + secrets["openweather_token"]

gfx = openweather_graphics.OpenWeather_Graphics(matrix.display, am_pm=True, units=UNITS)
print("gfx loaded")

localtime_refresh = None
weather_refresh = None

while True:
    # Sync time every hour
    if (not localtime_refresh) or (time.monotonic() - localtime_refresh) > 3600:
        try:
            print("Getting time from internet!")
            rtc.RTC().datetime = ntp.datetime
            localtime_refresh = time.monotonic()
        except RuntimeError as e:
            print("Error getting time, retrying! -", e)
            continue

    # Fetch weather data every 10 minutes
    if (not weather_refresh) or (time.monotonic() - weather_refresh) > 600:
        try:
            print("Fetching weather data...")
            response = requests.get(DATA_SOURCE)
            if response.status_code == 200:
                value = response.json()
                print("Weather data received:", value)
                gfx.display_weather(value)
                weather_refresh = time.monotonic()
            else:
                print("Failed to fetch weather data, status code:", response.status_code)
            response.close()
        except Exception as e:
            print("Error fetching weather data, retrying! -", e)
            continue

    gfx.scroll_next_label()
    time.sleep(2)  # Adjust scroll hold time