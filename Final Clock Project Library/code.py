# Smart Alarm Clock Code

# Import Statements

import board
import time
import displayio
import terminalio
import digitalio
from adafruit_display_text.label import Label
from adafruit_bitmap_font import bitmap_font
from adafruit_matrixportal.matrix import Matrix

# Accelerometer Sensor
import adafruit_lis3dh

# Light Sensor
import adafruit_vcnl4040


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

# Get WiFi details and more from a secrets.py file
try:
    from secrets import secrets
except ImportError:
    print("WiFi secrets are kept in secrets.py, please add them there!")
    raise
print("    Metro Minimal Clock")


# Clock and Weather Options
BLINK = True #Changes is Colon Blinks of Doesn't
DEBUG = False
UNITS = "imperial" #Changes Units for the Weather
LOCATION = secrets['location'] #Changes City that code asks API for
WEATHER_TIME_DISPLAY = 15 # Changes How long Weather is displayed upon wakeup
font = bitmap_font.load_font("/spleen-12x24.bdf")
light_sensor_threshold = 6.5
shaker_threshold = 10.5




# Light Sensor Setup
stemma_i2c = board.STEMMA_I2C()
light_sensor = adafruit_vcnl4040.VCNL4040(stemma_i2c)

#Accelerometer Set Up
i2c = board.I2C()  # uses board.SCL and board.SDA
lis3dh = adafruit_lis3dh.LIS3DH_I2C(i2c, address=0x19)
int1 = digitalio.DigitalInOut(board.ACCELEROMETER_INTERRUPT)
lis3dh.range = adafruit_lis3dh.RANGE_2_G


# Configure accelerometer to detect shakes
# lis3dh.set_tap(1, 80)  # 1 tap, sensitivity 80 (adjust as needed)



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

# Initialize Weather Graphics
gfx = openweather_graphics.OpenWeather_Graphics(matrix.display, am_pm=True, units=UNITS)

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

# OpenWeather API Setup
DATA_SOURCE = (
        "http://api.openweathermap.org/data/2.5/weather?q=" + LOCATION + "&units=" + UNITS
)
DATA_SOURCE += "&appid=" + secrets["openweather_token"]

# Beggining of Clock Code
if DEBUG:
    font = terminalio.FONT


clock_label = Label(font)


def update_time(*, hours=None, minutes=None, show_colon=False):
    now = time.localtime()  # Get the time values we need
    if hours is None:
        hours = now[3]
    if hours >= 18 or hours < 6:  # evening hours to morning
        clock_label.color = color[1]
    else:
        clock_label.color = color[3]  # daylight hours
    if hours > 12:  # Handle times later than 12:59
        hours -= 12
    elif not hours:  # Handle times between 0:00 and 0:59
        hours = 12

    if minutes is None:
        minutes = now[4]

    if BLINK:
        colon = ":" if show_colon or now[5] % 2 else " "
    else:
        colon = ":"

    clock_label.text = "{hours}{colon}{minutes:02d}".format(
        hours=hours, minutes=minutes, colon=colon
    )
    bbx, bby, bbwidth, bbh = clock_label.bounding_box
    # Center the label
    clock_label.x = round(display.width / 2 - bbwidth / 2)
    clock_label.y = display.height // 2 -2
    if DEBUG:
        print("Label bounding box: {},{},{},{}".format(bbx, bby, bbwidth, bbh))
        print("Label x: {} y: {}".format(clock_label.x, clock_label.y))


update_time(show_colon=True)  # Display whatever time is on the board
group.append(clock_label)  # add the clock label to the group

# Variables for while True Statement
localtime_refresh = None
weather_refresh = None
last_check = None
just_off = False
value = []

while True:
    if light_sensor.lux > light_sensor_threshold:
        if just_off == True:
            rtc.RTC().datetime = ntp.datetime  # Synchronize Board's clock to Internet
            last_check = time.monotonic()
            while time.monotonic() < last_check + WEATHER_TIME_DISPLAY:

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
                else:
                    gfx.display_weather(value)

                gfx.scroll_next_label()
                time.sleep(2)  # Adjust scroll hold time

            just_off = False
            last_check = None


        if last_check is None or time.monotonic() > last_check + 3600:
            display.root_group = group
            try:
                update_time(
                    show_colon=True
                )  # Make sure a colon is displayed while updating

                # NOTE: This changes the system time so make sure you aren't assuming that time
                # doesn't jump.
                rtc.RTC().datetime = ntp.datetime  # Synchronize Board's clock to Internet
                last_check = time.monotonic()

            except RuntimeError as e:
                print("Some error occured, retrying! -", e)

        update_time()
        time.sleep(1)
        print(light_sensor.lux)

    if light_sensor.lux < light_sensor_threshold:
        clock_label.color = color[0]
        just_off = True
        if lis3dh.shake(shake_threshold=shaker_threshold):  # Sensitivity adjustable (10 is a good starting value)
            #display.root_group = group
            print("Shake detected! Showing time for 5 seconds.")
            update_time()
          # Show the clock
            time.sleep(5)  # Keep display on for 5 seconds
            clock_label.color = color[0]







