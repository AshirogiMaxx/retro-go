# Retro-Go on NM-CYD-C5: macOS setup, audio, building and flashing

Prepared 29 October 2026 for the Apple Silicon Mac belonging to
`rubenponcemartinez`. Repository: `~/Documents/retro-go`, branch
`codex/nm-cyd-c5`. The toolchain is installed in your home directory and can be
used with **any of your ESP-IDF projects**. It is not a repository-local Python
environment. Other macOS accounts have separate home directories and would
need their own setup.

## Quick start on this Mac

Open a new Terminal window:

```sh
get_idf55
cd ~/Documents/retro-go
python rg_tool.py --target nm-cyd-c5 build-img
python -m serial.tools.list_ports
```

`get_idf55` activates ESP-IDF 5.5.3 in that terminal. If the terminal was open
before setup, run `source ~/.zshrc` first. In Bash, or in a shell that does not
load `.zshrc`, use:

```sh
source ~/.config/espressif/esp-idf-5.5.3.sh
```

Use the flashing commands below when you are ready to replace the board's
current firmware. Building an image does not flash it.

## Installed tools and locations

| Item | Location / version |
| --- | --- |
| ESP-IDF | `~/esp/esp-idf-v5.5.3`, tag `v5.5.3` |
| SDK revision | `2c211b236707889e8400c4dc5644dd5c4ee071e0` |
| Python | Existing user-wide Python 3.11.16 at `~/.local/bin/python3.11` |
| SDK Python packages | `~/.espressif/python_env/idf5.5_py3.11_env` |
| C5 C/C++ compiler | `~/.espressif/tools/riscv32-esp-elf/esp-14.2.0_20251107` |
| CMake | Espressif's 3.30.2, selected during activation |
| Ninja | Espressif's 1.12.1, selected during activation |
| Serial flasher | `esptool.py` / `python -m esptool`, 4.12.0 |
| Monitor | `python -m esp_idf_monitor` |
| Activation script | `~/.config/espressif/esp-idf-5.5.3.sh` |
| Terminal shortcut | `get_idf55()` appended to `~/.zshrc` |
| Previous shell configuration | `~/.zshrc.before-retro-go-20261029` |

The installation also supplies the matching RISC-V debugger, OpenOCD and ROM
ELF files. Your existing ESP-IDF 6.x installations and Homebrew tools remain
available. Activate the SDK version required by each project in a fresh shell.
Do not use ESP-IDF 6.x for this port: it has removed legacy APIs still used by
this Retro-Go checkout. No optional SDK source patches are needed for this board.

Check the active tools with:

```sh
idf.py --version
python --version
cmake --version
ninja --version
python -m esptool version
```

## Reproducing the installation

On this machine, Python 3.11 and Git were already installed. For a new Mac,
install Apple's command line developer tools (`xcode-select --install`) and
Python 3.11 first. With a Python 3.11 executable available:

```sh
mkdir -p ~/esp
git clone --depth 1 --branch v5.5.3 --recursive --shallow-submodules \
  https://github.com/espressif/esp-idf.git ~/esp/esp-idf-v5.5.3
python3.11 ~/esp/esp-idf-v5.5.3/tools/idf_tools.py install --targets=esp32c5
python3.11 ~/esp/esp-idf-v5.5.3/tools/idf_tools.py install cmake ninja
python3.11 ~/esp/esp-idf-v5.5.3/tools/idf_tools.py install-python-env
```

The installed activation file contains the following. Adjust the Python path
if your Python 3.11 is elsewhere:

```sh
_esp_idf55_exports="$("$HOME/.local/bin/python3.11" "$HOME/esp/esp-idf-v5.5.3/tools/activate.py" --export)" || return
eval "$_esp_idf55_exports"
unset _esp_idf55_exports
```

Create `~/.config/espressif` with `mkdir -p ~/.config/espressif`, save that as
`~/.config/espressif/esp-idf-5.5.3.sh`, and add this function to
`~/.zshrc` once:

```sh
get_idf55() { . "$HOME/.config/espressif/esp-idf-5.5.3.sh"; }
```

For another ESP-IDF project, activate the same SDK, change into that project,
and run its normal commands, such as `idf.py set-target esp32c5` and
`idf.py build`. Retro-Go specifically needs `rg_tool.py` because it contains
multiple applications. To add tools for other chip families later:

```sh
python3.11 ~/esp/esp-idf-v5.5.3/tools/idf_tools.py install --targets=esp32,esp32s3,esp32c5
```

## Board configuration

| Function | GPIO / setting |
| --- | --- |
| Chip | `esp32c5`; 240 MHz, one application core |
| Flash / PSRAM | 16 MB DIO flash at 40 MHz / 8 MB quad PSRAM at 80 MHz |
| Shared SPI SCK / MISO / MOSI | 6 / 2 / 7 |
| Display | ST7789, 320 × 240 landscape |
| Display CS / DC / backlight | 23 / 24 / 25 |
| XPT2046 touch CS | 1 |
| microSD CS | 10 |
| Speaker amplifier input | **26, SPEAK_IN** |
| WS2812 RGB LED | 27; currently unused |

The target files live in `components/retro-go/targets/nm-cyd-c5/`.
`config.h` selects pins, display commands, touch regions and the audio sink.
`sdkconfig` supplies the ESP-IDF defaults, and `env.py` selects the C5 and
reserves 1.5 MB for each app. Task creation maps unavailable CPU affinities to
the single available core. The touch controller attaches after SPI display
initialization and stops reading before its device handle is removed.

Flash intentionally runs at **40 MHz**. On the tested C5 revision 1.0 board,
80 MHz repeatedly caused an `esp_mmu_map_init` assertion immediately after a
USB reset. A 40 MHz launcher booted normally with the same 80 MHz PSRAM setting.
Keep that conservative flash setting when rebuilding.

### Sound through GPIO26 / SPEAK_IN

The C5 has no classic ESP32 analog DAC. The new
`components/retro-go/drivers/audio/pwm.c` driver produces **8-bit PWM audio at
150 kHz** on GPIO26, the SC8002B amplifier's analog input. The board's analog
input path and speaker recover the audio waveform from the PWM carrier.
There are no I2S clock or word-select signals.

Audio uses LEDC **channel 1 / timer 1**. The backlight keeps channel 0 / timer 0.
All low-speed LEDC timers on the C5 share their source clock, so both use XTAL;
selecting a different source for audio produces a timer clock conflict.
GPTimer supplies the sample interrupt. An internal-RAM ring buffer holds 2048
samples (64 ms at 32 kHz), with atomic producer/consumer positions. The ISR
writes LEDC registers directly and does not call blocking fade functions.

Stereo emulator samples are averaged into mono and scaled by software volume.
Mute takes effect in the sample interrupt, including already-queued samples.
Silence and underruns hold the 50% duty-cycle midpoint. A sample-rate change
recreates the timer, supporting 32,000 Hz and approximately 22,050 Hz playback.
This approach uses a sample interrupt and 8-bit output; it trades CPU time and
fidelity for a simple GPIO connection to the amplifier.

The selectable sink is named **Speaker**, with driver name `pwm`. If old
SD-card settings select Dummy, choose Speaker under **Audio out** in Options.
Connect a suitable speaker to the board's **SPEAK** output connector.
GPIO26/SPEAK_IN is the amplifier input, not a speaker power output.

To test without a ROM, open Options using the top-right touch region, select
**Audio out: Speaker**, set Volume to 25–50%, and activate **Test sound**. It
plays a half-second 440 Hz triangle wave, temporarily unmutes, and restores the
previous mute state. No startup tone is played. If the tone is audible but a
game is silent, check the game and its audio settings. Analog noise/filtering
and listening quality must be checked on your exact board revision.

### Touch controls and SD card

The left side is the direction pad. The right middle contains B and A, the top
right opens Menu, and the lower right contains Select and Start. These are
invisible touch regions over the existing display. The panel is single-touch,
so it cannot generally provide direction plus A/B together. This is suitable
for navigation and basic testing; a physical multi-button controller requires
an additional input implementation. No Bluetooth gamepad support is included.

Touch calibration is configurable with `RG_TOUCH_XPT2046_X_MIN/X_MAX`,
`Y_MIN/Y_MAX`, `SWAP_XY` and `PRESSURE_MIN` in the target's `config.h`. Adjust
the raw limits if your panel's touches do not match the intended regions.

Use a FAT32 microSD card. Copy your own game files into folders such as
`/roms/nes`, `/roms/gb`, `/roms/gbc`, `/roms/sms`, `/roms/gg`, `/roms/md`,
`/roms/pce`, `/roms/lnx`, `/roms/doom` and `/roms/msx`. BIOS requirements are
listed in the main README. Flashing firmware does not add ROMs to the card.
Performance varies on the single-core C5; start with Game Boy, NES or SMS.

## Build the firmware

```sh
get_idf55
cd ~/Documents/retro-go
python rg_tool.py --target nm-cyd-c5 build-img
```

The default build includes `launcher`, `retro-core`, `prboom-go`, `gwenesis`
and `fmsx`. It creates a `retro-go_<version>_nm-cyd-c5.img` file in the repository
root, with a C5 bootloader at `0x2000`, partition table at `0x8000`, and first
application at `0x10000`. Flash this **complete image at address 0x0**. The
1.5 MB app partitions leave room for ESP-IDF 5.5 networking overhead.

For a smaller image:

```sh
python rg_tool.py --target nm-cyd-c5 build-img launcher retro-core
```

When changing `sdkconfig`, SDK versions, or target boards, clean first:

```sh
python rg_tool.py --target nm-cyd-c5 clean
python rg_tool.py --target nm-cyd-c5 build-img
```

Do not use the ODROID `.fw` format, `idf.py flash` inside an app folder, or an
image for the original ESP32 CYD. They do not install the required C5 multi-app
layout.

## Identify, back up and flash the board

Connect a data-capable USB cable. macOS normally supports the C5's native
USB-Serial/JTAG port without a separate driver. The CH340 USB-UART connector
is an alternative; inspect the detected ports before installing any driver.

```sh
python -m serial.tools.list_ports
```

During setup, the board appeared as `/dev/cu.usbmodem11301`, identified as an
ESP32-C5 revision 1.0 with 16 MB flash. Port names can change after reconnecting.
Set the port to the current value:

```sh
export RG_TOOL_PORT=/dev/cu.usbmodem11301
python -m esptool --chip esp32c5 --port "$RG_TOOL_PORT" flash_id
```

Before replacing firmware, save all 16 MB if you need a recovery image:

```sh
mkdir -p ~/esp/backups/nm-cyd-c5
python -m esptool --chip esp32c5 --port "$RG_TOOL_PORT" --baud 460800 \
  read_flash 0x0 0x1000000 ~/esp/backups/nm-cyd-c5/original-flash.bin
```

The setup session's backup is at
`~/esp/backups/nm-cyd-c5-20261029/original-flash.bin`.

Build and install the complete image:

```sh
python rg_tool.py --target nm-cyd-c5 --port "$RG_TOOL_PORT" --baud 460800 install
```

This replaces the bootloader, partition table, settings sectors and app areas
covered by the image. Back up any existing firmware first. An erase-all command
is not required. To flash an already-built image without rebuilding, replace
the filename below with the exact image you want:

```sh
python -m esptool --chip esp32c5 --port "$RG_TOOL_PORT" --baud 460800 \
  write_flash --flash_size detect 0x0 retro-go_VERSION_nm-cyd-c5.img
```

If connection fails, hold **BOOT**, tap **RST**, release BOOT, then retry.
Close other serial monitors before opening the port. To restore the original
firmware, use the same `write_flash` command at `0x0` with the backup `.bin`.

## Rebuild individual applications and read logs

After installing a complete Retro-Go image once:

```sh
python rg_tool.py --target nm-cyd-c5 build launcher
python rg_tool.py --target nm-cyd-c5 --port "$RG_TOOL_PORT" --baud 460800 flash launcher
python rg_tool.py --target nm-cyd-c5 --port "$RG_TOOL_PORT" monitor launcher
```

`flash` writes an already-built app. `run launcher` builds, flashes and opens
the monitor. Each flash refreshes the partition table from the connected board
so it does not reuse another image's cached offsets. Reinstall a complete image
when adding apps or changing the partition layout. Keep the generated `.elf`
files to decode crashes. Exit the monitor with **Ctrl+]**.

## Validation and remaining hardware checks

The [validation record](nm-cyd-c5-validation.txt) lists the final image hash,
application offsets and completed checks. The built image is
`retro-go_1.46-8-g4ced1-dirty_nm-cyd-c5.img` in the repository root.

On 29 October 2026, the connected ESP32-C5 revision 1.0 board booted the port
with 40 MHz flash. The [captured boot log](nm-cyd-c5-boot.log) confirms SD
mounting, display initialization, XPT2046 initialization, a PWM Speaker sink on
GPIO26 at 32,000 Hz, about 8 MB of external RAM, and `Retro-Go ready.`. The user
confirmed that the screen and touch work and that **Test sound is audible**
through the SC8002B with the PWM driver. Three successive USB resets verified
the 40 MHz flash fix; the captured log separately verifies PWM initialization.
Game-specific playback, 22,050 Hz listening quality and emulator performance
have not all been checked on hardware.

The `SPI bus already initialized` message in that log comes from the display
driver trying to initialize the shared bus after the SD driver has done so.
The display driver accepts that state and attaches its device successfully.

The host regression checks run with:

```sh
python3 tools/test_nm_cyd_c5.py
```

They verify the C5 bootloader/partition offsets and image CRC, plus the actual
PWM driver's mono conversion, full-scale values, ring-buffer wrap and backpressure,
volume, immediate mute, underrun midpoint, timeout handling, init-failure cleanup
and sample-rate reinitialization.
The C driver tests use mock peripheral calls; they do not replace device tests.
The host checks also verify that individual-app flashing refreshes the board's
partition table and stops if that read fails.

Before considering the port verified on hardware, check cold boot, detected
PSRAM, screen orientation/colors/backlight, SD-card access, touch calibration,
app switching, playback at 32,000 Hz and 22,050 Hz, mute/volume, and audible
noise. A successful build alone does not prove those functions work physically.

## Sources and attribution

- [RockBase-iot's board bring-up PR #335](https://github.com/ducalex/retro-go/pull/335),
  imported from commit `cf23dffcf1455c663cd17907bd19c2bba36c2d64` under the
  repository's GPLv2 license. This port adds PWM audio and the tooling changes
  described above.
- [Manufacturer board reference](https://github.com/RockBase-iot/NM-CYD-C5),
  for board configuration and shared SPI pins.
- [Espressif ESP-IDF v5.5.3 source](https://github.com/espressif/esp-idf/tree/v5.5.3),
  especially the LEDC and GPTimer APIs.
- [Espressif PWM audio design](https://docs.espressif.com/projects/esp-iot-solution/en/latest/audio/pwm_audio.html),
  for the PWM, sample-timer and buffer approach.
- [SC8002B manufacturer datasheet](https://www.chipsourcetek.com/DataSheet/SC8002B.pdf),
  for the amplifier's analog input and speaker output.
