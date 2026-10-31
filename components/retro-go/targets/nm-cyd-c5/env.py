# This file is injected late into rg_tool.py, you can run arbitrary python code here
# For example override python variables or set environment variables with os.putenv

# Espressif chip in the device
IDF_TARGET = "esp32c5"
# .fw file format, if supported by the device
FW_FORMAT = "none"
# ESP-IDF 5.5 networking increases app size. The board has 16 MB flash,
# so reserve 1.5 MB per app and keep the usual five-app default image.
for app in PROJECT_APPS.values():
    app[2] = 0x180000
