# NM-CYD-C5

ESP32-C5-WROOM-1, 240 MHz single-core RISC-V, 16 MB flash, 8 MB PSRAM,
ST7789 display, XPT2046 resistive touch, and shared SPI microSD.

Use **ESP-IDF 5.5.3**. See the complete
[macOS setup, build, flash and GPIO26 speaker guide](../../../../../docs/NM-CYD-C5.md).

Audio uses 8-bit LEDC PWM at 150 kHz, paced by GPTimer from an internal-RAM
sample buffer. GPIO26 is the **SPEAK_IN** analog input of the board's SC8002B
amplifier. Connect a speaker to the board's speaker connector. The default sink
is **Speaker** (`pwm`), with software volume and mute. Audio uses LEDC channel 1
and timer 1, with the same XTAL clock source as the backlight on channel/timer 0.
The Options menu includes **Test sound** for a short 440 Hz tone.
The user confirmed working display/touch and an audible PWM test tone on the
connected C5 revision 1.0 board. Individual games still need normal play testing.

The touch panel maps screen regions to gamepad buttons. It is single-touch;
direction plus A/B cannot generally be held together. No Bluetooth gamepad
driver is included. GPIO27's WS2812 status LED is not driven by this port.

The default image includes launcher, retro-core, prboom-go, gwenesis and fmsx,
with 1.5 MB per app. Single-core performance varies with the emulator and ROM.

Board bring-up is adapted from RockBase-iot's
[Retro-Go PR #335](https://github.com/ducalex/retro-go/pull/335), commit
`cf23dffcf1455c663cd17907bd19c2bba36c2d64`. GPIO26 PWM audio, expanded app
partitions, host-tool compatibility, tests and this guide extend that port.
