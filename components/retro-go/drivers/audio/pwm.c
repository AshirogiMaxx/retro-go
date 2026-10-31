#include "rg_system.h"
#include "rg_audio.h"

#if RG_AUDIO_USE_PWM

#include <stdatomic.h>
#include <driver/gpio.h>
#include <driver/gptimer.h>
#include <driver/ledc.h>
#include <hal/ledc_ll.h>

// Channel/timer 0 belong to the LCD backlight. Audio owns channel/timer 1.
// All low-speed LEDC timers on C5 share a clock source. Use the same XTAL
// source as the backlight, with a 150 kHz carrier. The SC8002B takes the recovered
// analog waveform through SPEAK_IN; it does not accept an I2S data stream.
#define PWM_CHANNEL LEDC_CHANNEL_1
#define PWM_TIMER LEDC_TIMER_1
#define PWM_MODE LEDC_LOW_SPEED_MODE
#define PWM_CENTER 128
#define BUFFER_SIZE 2048 // Power of two; 64 ms at 32 kHz.
#define TIMER_RESOLUTION 40000000

static DRAM_ATTR struct
{
    gptimer_handle_t timer;
    bool enabled;
    bool started;
    bool channel_ready;
    atomic_bool muted;
    atomic_uint head;
    atomic_uint tail;
    uint8_t samples[BUFFER_SIZE];
    int volume;
    const char *error;
} state;

static bool IRAM_ATTR sample_interrupt(gptimer_handle_t timer, const gptimer_alarm_event_data_t *event, void *arg)
{
    unsigned tail = atomic_load_explicit(&state.tail, memory_order_relaxed);
    unsigned head = atomic_load_explicit(&state.head, memory_order_acquire);
    unsigned duty = PWM_CENTER;
    if (tail != head)
    {
        duty = state.samples[tail & (BUFFER_SIZE - 1)];
        atomic_store_explicit(&state.tail, tail + 1, memory_order_release);
    }
    if (atomic_load_explicit(&state.muted, memory_order_relaxed))
        duty = PWM_CENTER;

    // Register-only writes: no blocking fade locks or flash-resident functions
    // in the ISR. Only this ISR modifies audio channel 1 while it is running.
    ledc_ll_set_duty_int_part(LEDC_LL_GET_HW(), PWM_MODE, PWM_CHANNEL, duty);
    ledc_ll_set_duty_start(LEDC_LL_GET_HW(), PWM_MODE, PWM_CHANNEL);
    ledc_ll_ls_channel_update(LEDC_LL_GET_HW(), PWM_MODE, PWM_CHANNEL);
    return false;
}

static bool driver_deinit(void)
{
    if (state.timer)
    {
        if (state.started)
            gptimer_stop(state.timer);
        if (state.enabled)
            gptimer_disable(state.timer);
        gptimer_del_timer(state.timer);
        state.timer = NULL;
        state.started = state.enabled = false;
    }
    if (state.channel_ready)
    {
        ledc_stop(PWM_MODE, PWM_CHANNEL, 0);
        state.channel_ready = false;
    }
    gpio_reset_pin(RG_GPIO_SND_PWM);
    return true;
}

static bool driver_init(int device, int sample_rate)
{
    state.error = NULL;
    state.volume = 50;
    atomic_store(&state.muted, false);
    atomic_store(&state.head, 0);
    atomic_store(&state.tail, 0);
    if (sample_rate < 8000 || sample_rate > 48000)
    {
        state.error = "PWM supports sample rates from 8000 to 48000 Hz";
        return false;
    }
    esp_err_t ret = ledc_timer_config(&(ledc_timer_config_t){
        .speed_mode = PWM_MODE,
        .duty_resolution = LEDC_TIMER_8_BIT,
        .timer_num = PWM_TIMER,
        .freq_hz = 150000,
        .clk_cfg = LEDC_USE_XTAL_CLK,
    });
    if (ret == ESP_OK)
    {
        ret = ledc_channel_config(&(ledc_channel_config_t){
            .gpio_num = RG_GPIO_SND_PWM,
            .speed_mode = PWM_MODE,
            .channel = PWM_CHANNEL,
            .timer_sel = PWM_TIMER,
            .duty = PWM_CENTER,
        });
        state.channel_ready = ret == ESP_OK;
    }
    if (ret == ESP_OK)
        ret = gptimer_new_timer(&(gptimer_config_t){
            .clk_src = GPTIMER_CLK_SRC_DEFAULT,
            .direction = GPTIMER_COUNT_UP,
            .resolution_hz = TIMER_RESOLUTION,
        }, &state.timer);
    if (ret == ESP_OK)
        ret = gptimer_register_event_callbacks(state.timer, &(gptimer_event_callbacks_t){
            .on_alarm = sample_interrupt,
        }, NULL);
    if (ret == ESP_OK)
        ret = gptimer_set_alarm_action(state.timer, &(gptimer_alarm_config_t){
            .alarm_count = (TIMER_RESOLUTION + sample_rate / 2) / sample_rate,
            .reload_count = 0,
            .flags.auto_reload_on_alarm = true,
        });
    if (ret == ESP_OK)
    {
        ret = gptimer_enable(state.timer);
        state.enabled = ret == ESP_OK;
    }
    if (ret == ESP_OK)
    {
        ret = gptimer_start(state.timer);
        state.started = ret == ESP_OK;
    }
    if (ret != ESP_OK)
    {
        state.error = esp_err_to_name(ret);
        driver_deinit();
        return false;
    }
    RG_LOGI("PWM speaker ready on GPIO%d, %d Hz, carrier 150000 Hz\n", RG_GPIO_SND_PWM, sample_rate);
    return true;
}

static bool driver_submit(const rg_audio_frame_t *frames, size_t count)
{
    const int64_t deadline = rg_system_timer() + 1000000;
    while (count)
    {
        unsigned head = atomic_load_explicit(&state.head, memory_order_relaxed);
        unsigned tail = atomic_load_explicit(&state.tail, memory_order_acquire);
        size_t chunk = RG_MIN(count, BUFFER_SIZE - (head - tail));
        if (!chunk)
        {
            if (rg_system_timer() >= deadline)
            {
                state.error = "PWM sample buffer timed out";
                return false;
            }
            rg_task_delay(1);
            continue;
        }
        for (size_t i = 0; i < chunk; ++i)
        {
            int32_t sample = ((int32_t)frames[i].left + frames[i].right) / 2;
            sample = sample * state.volume / 100;
            state.samples[(head + i) & (BUFFER_SIZE - 1)] = (sample + 32768) >> 8;
        }
        atomic_store_explicit(&state.head, head + chunk, memory_order_release);
        frames += chunk;
        count -= chunk;
    }
    return true;
}

static bool driver_set_mute(bool mute)
{
    atomic_store(&state.muted, mute);
    return true;
}

static bool driver_set_volume(int percent)
{
    state.volume = RG_MIN(100, RG_MAX(0, percent));
    return true;
}

static const char *driver_get_error(void)
{
    return state.error ? state.error : "No error";
}

const rg_audio_driver_t rg_audio_driver_pwm = {
    .name = "pwm",
    .init = driver_init,
    .deinit = driver_deinit,
    .submit = driver_submit,
    .set_mute = driver_set_mute,
    .set_volume = driver_set_volume,
    .set_sample_rate = NULL, // rg_audio reinitializes the timer for a new rate.
    .get_error = driver_get_error,
};

#endif
