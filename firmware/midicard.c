/*
 * USB MIDI touch keyboard business card - firmware for CH32X035G8U6.
 *
 * - Class-compliant USB MIDI (no drivers): each of the 13 copper keys sends
 *   Note On / Note Off, C4..C5 by default.
 * - Notes coming from the computer play on the piezo (monophonic).
 * - Powered from a charger / power bank (USB not enumerated): keys beep.
 *
 * Touch sensing: every key is wired to SEND through a 1 MOhm resistor.
 * SEND goes high and we time, in a tight loop, how long each key pin takes
 * to read high. A finger adds capacitance, so the edge comes later.
 * All 13 keys are timed in parallel from two port reads per loop pass.
 *
 * Pin map (must match scripts/design.py):
 *   keys  PA0..PA7, PB0, PB3, PB4, PB1, PB6  (C .. C2)
 *   SEND  PC3     LED  PB12     piezo  PB9 (TIM1 CH1) + PB10 (TIM1 CH2, inverted)
 *   USB   PC16 (D-), PC17 (D+)   SWD  PC18 (DIO), PC19 (CLK)
 */
#include "ch32fun.h"
#include "fsusb.h"
#include <string.h>

#define NKEYS        13
#define BASE_NOTE    60          // middle C
#define VELOCITY     100
#define BEEP_OCTAVES 2           // play the piezo 2 octaves up: louder near its 4 kHz resonance

// key -> (port B?, bit)
static const uint8_t key_portb[NKEYS] = { 0,0,0,0,0,0,0,0, 1,1,1,1,1 };
static const uint8_t key_bit[NKEYS]   = { 0,1,2,3,4,5,6,7, 0,3,4,1,6 };
#define MASK_A 0x00FFu
#define MASK_B ((1u<<0)|(1u<<1)|(1u<<3)|(1u<<4)|(1u<<6))

#define SEND_BIT     3           // PC3
#define LED_PIN      PB12

// ------------------------------------------------------------------ touch
#define MAX_T        1024                    // loop passes before giving up (~200 us)
static uint32_t samples[MAX_T];
static uint16_t raw[NKEYS];

// CFGLR nibble value 0x1 = output push-pull 10 MHz, 0x4 = floating input
static uint32_t cfg_set(uint32_t reg, uint32_t mask, uint32_t nib)
{
	for (int b = 0; b < 8; b++)
		if (mask & (1u << b))
			reg = (reg & ~(0xFu << (4 * b))) | (nib << (4 * b));
	return reg;
}

static void keys_discharge(void)
{
	GPIOC->BCR = 1u << SEND_BIT;
	GPIOA->BCR = MASK_A;
	GPIOB->BCR = MASK_B;
	GPIOA->CFGLR = cfg_set(GPIOA->CFGLR, MASK_A, GPIO_CFGLR_OUT_10Mhz_PP);
	GPIOB->CFGLR = cfg_set(GPIOB->CFGLR, MASK_B, GPIO_CFGLR_OUT_10Mhz_PP);
}

static void touch_scan(void)
{
	keys_discharge();
	Delay_Us(20);
	GPIOA->CFGLR = cfg_set(GPIOA->CFGLR, MASK_A, GPIO_CFGLR_IN_FLOAT);
	GPIOB->CFGLR = cfg_set(GPIOB->CFGLR, MASK_B, GPIO_CFGLR_IN_FLOAT);

	const uint32_t all = MASK_A | (MASK_B << 16);
	int n = 0;
	__disable_irq();
	GPIOC->BSHR = 1u << SEND_BIT;
	for (; n < MAX_T; n++) {
		uint32_t v = (GPIOA->INDR & MASK_A) | ((GPIOB->INDR & MASK_B) << 16);
		samples[n] = v;
		if (v == all)
			break;
	}
	__enable_irq();
	keys_discharge();

	for (int k = 0; k < NKEYS; k++) {
		uint32_t bit = 1u << (key_bit[k] + (key_portb[k] ? 16 : 0));
		int t = 0;
		int last = n < MAX_T ? n : MAX_T - 1;
		while (t <= last && !(samples[t] & bit))
			t++;
		raw[k] = t;              // MAX_T if it never rose (finger on bare copper)
	}
}

// ------------------------------------------------------------------ key logic
static int32_t base_x16[NKEYS];      // baseline in 1/16 counts
static int32_t filt[NKEYS];
static uint8_t pressed[NKEYS], debounce[NKEYS];

static int on_threshold(int k)
{
	int b = base_x16[k] >> 4;
	int th = b / 3;                  // +33 % of the untouched charge time
	return th < 6 ? 6 : th;
}

static void touch_calibrate(void)
{
	int32_t acc[NKEYS] = {0};
	for (int i = 0; i < 64; i++) {
		touch_scan();
		for (int k = 0; k < NKEYS; k++)
			acc[k] += raw[k];
	}
	for (int k = 0; k < NKEYS; k++) {
		base_x16[k] = acc[k] / 4;    // (acc/64)*16
		filt[k] = acc[k] / 64;
	}
}

// ------------------------------------------------------------------ MIDI out
static uint32_t midi_q[32];
static volatile uint8_t q_head, q_tail;

static void midi_put(uint8_t cin, uint8_t b0, uint8_t b1, uint8_t b2)
{
	uint8_t next = (q_head + 1) & 31;
	if (next == q_tail)
		return;                      // full: drop
	midi_q[q_head] = cin | (b0 << 8) | (b1 << 16) | ((uint32_t)b2 << 24);
	q_head = next;
}

static void midi_flush(void)
{
	if (q_head == q_tail || USBFSCTX.endpoints[MIDI_EP_IN].busy)
		return;
	static uint32_t pkt[16];
	int n = 0;
	uint8_t t = q_tail;
	while (t != q_head && n < 16) {
		pkt[n++] = midi_q[t];
		t = (t + 1) & 31;
	}
	if (USBFS_SendEndpointNEW(MIDI_EP_IN, (uint8_t *)pkt, n * 4, 1) == 0)
		q_tail = t;
}

static int usb_ready(void)
{
	return USBFSCTX.USBFS_DevEnumStatus != 0;
}

// ------------------------------------------------------------------ piezo
static uint8_t tone_note;            // 0 = silent

static void piezo_init(void)
{
	RCC->APB2PCENR |= RCC_APB2Periph_TIM1;
	TIM1->PSC = 48 - 1;              // 1 MHz timer clock
	TIM1->CHCTLR1 = (6 << 4) | TIM_OC1PE | (6 << 12) | (TIM_OC1PE << 8);  // PWM1 on CH1 and CH2
	TIM1->CCER = TIM_CC1E | TIM_CC2E | TIM_CC2P;  // CH2 inverted -> push-pull across the piezo
	TIM1->BDTR = TIM_MOE;
	TIM1->CTLR1 = TIM_ARPE;
	funPinMode(PB9, GPIO_CFGLR_OUT_10Mhz_PP);
	funPinMode(PB10, GPIO_CFGLR_OUT_10Mhz_PP);
	funDigitalWrite(PB9, FUN_LOW);
	funDigitalWrite(PB10, FUN_LOW);
}

static void piezo_play(uint8_t note)
{
	if (note == tone_note)
		return;
	tone_note = note;
	if (!note) {
		TIM1->CTLR1 &= ~TIM_CEN;
		funPinMode(PB9, GPIO_CFGLR_OUT_10Mhz_PP);
		funPinMode(PB10, GPIO_CFGLR_OUT_10Mhz_PP);
		funDigitalWrite(PB9, FUN_LOW);
		funDigitalWrite(PB10, FUN_LOW);
		return;
	}
	// f = 440 * 2^((n-69)/12); computed with an integer table for one octave
	static const uint32_t a_oct_mhz[12] = {   // millihertz of C..B in octave 4
		261626, 277183, 293665, 311127, 329628, 349228, 369994, 391995, 415305, 440000, 466164, 493883 };
	int n = note - 60;
	int oct = n >= 0 ? n / 12 : -((11 - n) / 12);
	int semi = n - oct * 12;
	uint32_t mhz = a_oct_mhz[semi];
	if (oct > 0) mhz <<= oct; else mhz >>= -oct;
	uint32_t period = 1000000000u / mhz;      // in us
	if (period < 50) period = 50;
	if (period > 60000) period = 60000;
	TIM1->ATRLR = period - 1;
	TIM1->CH1CVR = period / 2;
	TIM1->CH2CVR = period / 2;
	TIM1->SWEVGR = TIM_UG;
	funPinMode(PB9, GPIO_CFGLR_OUT_10Mhz_AF_PP);
	funPinMode(PB10, GPIO_CFGLR_OUT_10Mhz_AF_PP);
	TIM1->CTLR1 |= TIM_CEN;
}

// ------------------------------------------------------------------ USB callbacks
static volatile uint8_t host_note;   // last note the host asked us to play

int HandleSetupCustom(struct _USBState *ctx, int setup_code)
{
	return -1;                       // MIDI needs no class requests
}

int HandleInRequest(struct _USBState *ctx, int endp, uint8_t *data, int len)
{
	return 0;
}

void HandleDataOut(struct _USBState *ctx, int endp, uint8_t *data, int len)
{
	if (endp == 0) {
		ctx->USBFS_SetupReqLen = 0;
		return;
	}
	if (endp == MIDI_EP_OUT) {
		for (int i = 0; i + 3 < len; i += 4) {
			uint8_t cin = data[i] & 0x0F, note = data[i + 2], vel = data[i + 3];
			if (cin == 0x9 && vel)
				host_note = note;
			else if ((cin == 0x8 || (cin == 0x9 && !vel)) && note == host_note)
				host_note = 0;
		}
		ctx->endpoints[MIDI_EP_OUT].busy = 0;
	}
}

// ------------------------------------------------------------------ main
int main(void)
{
	SystemInit();
	funGpioInitAll();
	funPinMode(LED_PIN, GPIO_CFGLR_OUT_10Mhz_PP);
	funDigitalWrite(LED_PIN, FUN_HIGH);
	funPinMode(PC3, GPIO_CFGLR_OUT_10Mhz_PP);     // SEND
	// PB5 is bonded to PB1 inside the QFN-28: keep it a floating input.
	funPinMode(PB5, GPIO_CFGLR_IN_FLOAT);

	piezo_init();
	USBFSSetup();
	touch_calibrate();               // keep fingers off the keys while plugging in
	funDigitalWrite(LED_PIN, FUN_LOW);

	uint32_t start = SysTick->CNTL;
	uint8_t last_local = 0;
	int blink = 0;

	while (1) {
		touch_scan();
		int standalone = !usb_ready() &&
			(uint32_t)(SysTick->CNTL - start) > 2000u * (FUNCONF_SYSTEM_CORE_CLOCK / 1000u);

		for (int k = 0; k < NKEYS; k++) {
			// light low-pass, then threshold with hysteresis and 2-scan debounce
			filt[k] += ((int32_t)raw[k] - filt[k]) / 2;
			int b = base_x16[k] >> 4;
			int d = filt[k] - b;
			int th = on_threshold(k);
			int want = pressed[k] ? (d > th / 2) : (d > th);
			if (want != pressed[k]) {
				if (++debounce[k] >= 2) {
					pressed[k] = want;
					debounce[k] = 0;
					uint8_t note = BASE_NOTE + k;
					if (want) {
						midi_put(0x09, 0x90, note, VELOCITY);
						last_local = note;
					} else {
						midi_put(0x08, 0x80, note, 0);
						if (last_local == note) last_local = 0;
					}
					blink = 30;
				}
			} else {
				debounce[k] = 0;
			}
			// track slow drift (temperature, humidity) only while untouched
			if (!pressed[k] && d < th / 2)
				base_x16[k] += (filt[k] * 16 - base_x16[k]) / 64;
		}

		if (usb_ready())
			midi_flush();
		else
			q_tail = q_head;         // not connected: drop queued MIDI

		// piezo: host notes when connected, own keys when standalone
		uint8_t want_tone = 0;
		if (standalone) {
			if (!last_local)         // fall back to any key still held
				for (int k = NKEYS - 1; k >= 0; k--)
					if (pressed[k]) { last_local = BASE_NOTE + k; break; }
			want_tone = last_local ? last_local + 12 * BEEP_OCTAVES : 0;
		} else if (host_note) {
			want_tone = host_note + 12 * BEEP_OCTAVES;
		}
		piezo_play(want_tone);

		// LED: on when connected, flickers off on key events; slow blink standalone
		if (blink) blink--;
		int led;
		if (usb_ready())
			led = blink ? 0 : 1;
		else
			led = (SysTick->CNTL >> 25) & 1;   // ~1.4 s period
		funDigitalWrite(LED_PIN, led ? FUN_HIGH : FUN_LOW);
	}
}
