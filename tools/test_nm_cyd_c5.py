#!/usr/bin/env python3
"""Host checks for the C5 image layout and the real PWM driver's interrupt/buffer contract.

Run: python3 tools/test_nm_cyd_c5.py (requires a host C compiler).
These checks do not exercise the physical display, touch panel or amplifier.
"""
import ast
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mkfw", ROOT / "tools/mkfw.py")
mkfw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mkfw)


class C5Tests(unittest.TestCase):
    def test_flash_refreshes_table_and_stops_on_read_failure(self):
        # Load only the real flash function, without executing the tool's CLI.
        tree = ast.parse((ROOT / "rg_tool.py").read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "flash_app")
        calls = []
        scope = dict(os=os, IDF_TARGET="esp32c5", ESPTOOL_PY="esptool.py",
                     GEN_ESP32PART_PY="gen_esp32part.py", PARTTOOL_PY="parttool.py",
                     run=lambda command, **kwargs: calls.append(command))
        exec(compile(ast.Module(body=[function], type_ignores=[]), "rg_tool.py", "exec"), scope)
        scope["flash_app"]("launcher", "test-port")
        scope["flash_app"]("launcher", "test-port")
        self.assertEqual(calls[0][1], "read_flash")
        self.assertEqual(calls[3][1], "read_flash")
        self.assertEqual(calls[2][-1], "launcher/build/launcher.bin")
        calls.clear()

        def failing_read(command, **kwargs):
            calls.append(command)
            raise RuntimeError("Cannot read board")

        scope["run"] = failing_read
        with self.assertRaises(RuntimeError):
            scope["flash_app"]("launcher", "test-port")
        self.assertEqual(len(calls), 1)

    def test_image_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            boot = Path(folder) / "boot.bin"
            boot.write_bytes(b"\xe9C5-boot")
            parts = [(0, 16, "launcher", 0x10000, 0x180000, b"launcher"),
                     (0, 17, "retro-core", 0x190000, 0x180000, b"emulators")]
            image = mkfw.create_image("esp32c5", parts, str(boot), "Retro-Go", "test", "nm-cyd-c5")
            self.assertEqual(image[0x2000:0x2008], boot.read_bytes())
            self.assertEqual(image[0x8000:0x8002], b"\xaa\x50")
            for index, part in enumerate(parts, 3):
                entry = struct.unpack_from("<2sBBLL16sL", image, 0x8000 + index * 32)
                self.assertEqual(entry[1:5], (part[0], part[1], part[3], part[4]))
                self.assertEqual(image[part[3]:part[3] + len(part[5])], part[5])
            footer = struct.unpack("<8s28s28s28sII156s", image[-256:])
            self.assertEqual(footer[0], b"RG_IMG_0")
            self.assertEqual(footer[3].rstrip(b"\0"), b"nm-cyd-c5")
            self.assertEqual(footer[5], zlib.crc32(image[:-256]))
            self.assertLess(len(image), 16 * 1024 * 1024)

    def test_pwm_driver(self):
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            (tmp / "driver").mkdir()
            (tmp / "hal").mkdir()
            (tmp / "rg_system.h").write_text(r"""
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define RG_AUDIO_USE_PWM 1
#define RG_GPIO_SND_PWM 26
#define DRAM_ATTR
#define IRAM_ATTR
#define RG_MIN(a,b) ((a)<(b)?(a):(b))
#define RG_MAX(a,b) ((a)>(b)?(a):(b))
#define RG_COUNT(a) (sizeof(a)/sizeof((a)[0]))
#define RG_LOGI(...) ((void)0)
#define RG_LOGW(...) ((void)0)
static int64_t fake_time;
static int64_t rg_system_timer(void) { fake_time += 100000; return fake_time; }
static void rg_task_delay(int ms);
""")
            (tmp / "driver/gpio.h").write_text(r"""
#pragma once
static inline void gpio_reset_pin(int pin) {}
""")
            (tmp / "driver/ledc.h").write_text(r"""
#pragma once
#include <assert.h>
#define ESP_OK 0
#define LEDC_CHANNEL_1 1
#define LEDC_TIMER_1 1
#define LEDC_LOW_SPEED_MODE 0
#define LEDC_TIMER_8_BIT 8
#define LEDC_USE_XTAL_CLK 1
static int active_channel, pending_duty, captured_count;
static unsigned captured[10000];
typedef int esp_err_t;
typedef struct {int speed_mode,duty_resolution,timer_num,freq_hz,clk_cfg;} ledc_timer_config_t;
typedef struct {int gpio_num,speed_mode,channel,timer_sel,duty;} ledc_channel_config_t;
static int ledc_timer_config(const ledc_timer_config_t *cfg) {
    assert(cfg->timer_num==1 && cfg->duty_resolution==8 && cfg->freq_hz==150000 && cfg->clk_cfg==LEDC_USE_XTAL_CLK); return 0;
}
static int ledc_channel_config(const ledc_channel_config_t *cfg) {
    assert(cfg->gpio_num==26 && cfg->channel==1 && cfg->timer_sel==1 && cfg->duty==128);
    active_channel++; return 0;
}
static int ledc_stop(int mode,int channel,int idle) { assert(channel==1); active_channel--; return 0; }
static const char *esp_err_to_name(int error) {return "mock error";}
""")
            (tmp / "hal/ledc_ll.h").write_text(r"""
#pragma once
#define LEDC_LL_GET_HW() ((void*)1)
static void ledc_ll_set_duty_int_part(void *hw,int mode,int channel,unsigned duty) {
    assert(channel==1); pending_duty=duty;
}
static void ledc_ll_set_duty_start(void *hw,int mode,int channel) {}
static void ledc_ll_ls_channel_update(void *hw,int mode,int channel) {
    captured[captured_count++]=pending_duty;
}
""")
            (tmp / "driver/gptimer.h").write_text(r"""
#pragma once
#include "ledc.h"
#define GPTIMER_CLK_SRC_DEFAULT 0
#define GPTIMER_COUNT_UP 0
typedef void *gptimer_handle_t;
typedef struct {int unused;} gptimer_alarm_event_data_t;
typedef struct {int clk_src,direction,resolution_hz;} gptimer_config_t;
typedef struct {uint64_t alarm_count,reload_count; struct {bool auto_reload_on_alarm;} flags;} gptimer_alarm_config_t;
typedef struct {bool (*on_alarm)(void *,const gptimer_alarm_event_data_t *,void *);} gptimer_event_callbacks_t;
static bool (*callback)(void *,const gptimer_alarm_event_data_t *,void *);
static int timers,enabled,started,fail_new,fail_start,drain=1;
static uint64_t period;
static int gptimer_new_timer(const gptimer_config_t *cfg,void **out) {
    assert(cfg->resolution_hz==40000000);
    if(fail_new)return 1;
    *out=(void*)1;timers++;return 0;
}
static int gptimer_register_event_callbacks(void *timer,const gptimer_event_callbacks_t *cfg,void *arg) {callback=cfg->on_alarm;return 0;}
static int gptimer_set_alarm_action(void *timer,const gptimer_alarm_config_t *cfg) {assert(cfg->flags.auto_reload_on_alarm);period=cfg->alarm_count;return 0;}
static int gptimer_enable(void *timer) {enabled++;return 0;}
static int gptimer_start(void *timer) {if(fail_start)return 1;started++;return 0;}
static int gptimer_stop(void *timer) {started--;return 0;}
static int gptimer_disable(void *timer) {enabled--;return 0;}
static int gptimer_del_timer(void *timer) {timers--;return 0;}
static void rg_task_delay(int ms) {if(drain) for(int i=0;i<128;i++)callback((void*)1,0,0);}
""")
            harness = tmp / "test.c"
            harness.write_text(r"""
#include <string.h>
#include "drivers/audio/pwm.c"
static void tick(void) {callback((void*)1,0,0);}
int main(void) {
    const rg_audio_driver_t *driver=&rg_audio_driver_pwm;
    assert(!driver->init(0,0) && timers==0);
    fail_new=1;
    assert(!driver->init(0,32000) && active_channel==0 && timers==0);
    fail_new=0;fail_start=1;
    assert(!driver->init(0,32000) && active_channel==0 && timers==0 && enabled==0);
    fail_start=0;
    assert(driver->init(0,32000) && period==1250);
    rg_audio_frame_t frames[2200];
    for(int i=0;i<2200;i++)frames[i]=(rg_audio_frame_t){32767,32767};
    frames[0]=(rg_audio_frame_t){-32768,-32768};
    frames[1]=(rg_audio_frame_t){-32768,32767};
    driver->set_volume(100);
    assert(driver->submit(frames,2200));
    while(captured_count<2200)tick();
    assert(captured[0]==0 && captured[1]==128 && captured[2199]==255);
    tick();assert(captured[2200]==128); // Underrun holds the analog midpoint.
    driver->set_volume(50);driver->submit(frames+2,1);tick();assert(captured[2201]==191);
    driver->submit(frames+2,1);driver->set_mute(true);tick();assert(captured[2202]==128);
    driver->set_mute(false);driver->set_volume(-10);driver->submit(frames+2,1);tick();assert(captured[2203]==128);
    driver->set_volume(150);driver->submit(frames+2,1);tick();assert(captured[2204]==255);
    drain=0;
    assert(!driver->submit(frames,2200));
    assert(strcmp(driver->get_error(),"PWM sample buffer timed out")==0);
    assert(driver->deinit() && timers==0 && started==0 && enabled==0 && active_channel==0);
    assert(driver->deinit() && timers==0);
    assert(driver->init(0,22050) && period==1814);
    driver->deinit();
    return 0;
}
""")
            compiler=shutil.which("cc")
            self.assertIsNotNone(compiler,"Install the Xcode command line tools")
            binary=tmp/"test"
            subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror","-Wno-unused-parameter",
                            "-I",str(tmp),"-I",str(ROOT/"components/retro-go"),str(harness),"-o",str(binary)],check=True)
            subprocess.run([str(binary)],check=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
