#ifndef _USB_CONFIG_H
#define _USB_CONFIG_H

// USB MIDI 1.0 class-compliant device: one MIDI IN and one MIDI OUT cable.
// EP1 IN (bulk) = card -> computer, EP2 OUT (bulk) = computer -> card (piezo).

#include "funconfig.h"
#include "ch32fun.h"

#define FUSB_BUFFERS_NUMBER   3   // EP0 + EP1 IN + EP2 OUT
#define FUSB_EP1_MODE         USBFS_EP_MODE_TX
#define FUSB_EP2_MODE         USBFS_EP_MODE_RX
#define MIDI_EP_IN            1
#define MIDI_EP_OUT           2
#define FUSB_SUPPORTS_SLEEP   0
#define FUSB_HID_INTERFACES   0
#define FUSB_HID_USER_REPORTS 0
#define FUSB_IO_PROFILE       0
#define FUSB_USE_HPE          FUNCONF_ENABLE_HPE
#define FUSB_EP_SIZE          64
#define FUSB_USER_HANDLERS    1
#define FUSB_OUT_FLOW_CONTROL 0
#define FUSB_VDD_5V           FUNCONF_USE_5V_VDD
#define FUSB_FROM_RAM         0

#include "usb_defines.h"

// pid.codes test VID/PID. Request your own free PID at https://pid.codes before
// handing out lots of cards.
#define FUSB_USB_VID          0x1209
#define FUSB_USB_PID          0x0001
#define FUSB_USB_REV          0x0100
#define FUSB_STR_MANUFACTURER u"YOUR NAME"
#define FUSB_STR_PRODUCT      u"MIDI Card"
#define FUSB_STR_SERIAL       u"0001"

static const tusb_desc_device_t device_descriptor = {
	.bLength            = sizeof(tusb_desc_device_t),
	.bDescriptorType    = TUSB_DESC_DEVICE,
	.bcdUSB             = 0x0200,
	.bDeviceClass       = 0,      // class given per interface
	.bDeviceSubClass    = 0,
	.bDeviceProtocol    = 0,
	.bMaxPacketSize0    = 64,
	.idVendor           = FUSB_USB_VID,
	.idProduct          = FUSB_USB_PID,
	.bcdDevice          = FUSB_USB_REV,
	.iManufacturer      = 1,
	.iProduct           = 2,
	.iSerialNumber      = 3,
	.bNumConfigurations = 1,
};

#define MIDI_CFG_TOTAL 101
static const uint8_t config_descriptor[MIDI_CFG_TOTAL] = {
	// Configuration
	0x09, 0x02, MIDI_CFG_TOTAL, 0x00, 0x02, 0x01, 0x00, 0x80, 50,   // 2 interfaces, bus powered, 100 mA

	// Standard AudioControl interface (required by the spec, no endpoints)
	0x09, 0x04, 0x00, 0x00, 0x00, 0x01, 0x01, 0x00, 0x00,
	// Class-specific AC header: ADC 1.0, total 9, one streaming interface (#1)
	0x09, 0x24, 0x01, 0x00, 0x01, 0x09, 0x00, 0x01, 0x01,

	// Standard MIDIStreaming interface, 2 endpoints
	0x09, 0x04, 0x01, 0x00, 0x02, 0x01, 0x03, 0x00, 0x00,
	// Class-specific MS header: MIDI 1.0, total length of CS descriptors = 65
	0x07, 0x24, 0x01, 0x00, 0x01, 0x41, 0x00,
	// MIDI IN jack, embedded, id 1 (host -> card)
	0x06, 0x24, 0x02, 0x01, 0x01, 0x00,
	// MIDI IN jack, external, id 2 (the touch keys)
	0x06, 0x24, 0x02, 0x02, 0x02, 0x00,
	// MIDI OUT jack, embedded, id 3, source = jack 2 (card -> host)
	0x09, 0x24, 0x03, 0x01, 0x03, 0x01, 0x02, 0x01, 0x00,
	// MIDI OUT jack, external, id 4, source = jack 1 (the piezo)
	0x09, 0x24, 0x03, 0x02, 0x04, 0x01, 0x01, 0x01, 0x00,

	// Bulk OUT endpoint 2 (audio class style 9-byte endpoint descriptor)
	0x09, 0x05, 0x02, 0x02, 0x40, 0x00, 0x00, 0x00, 0x00,
	// CS MS bulk OUT: one embedded jack, id 1
	0x05, 0x25, 0x01, 0x01, 0x01,
	// Bulk IN endpoint 1
	0x09, 0x05, 0x81, 0x02, 0x40, 0x00, 0x00, 0x00, 0x00,
	// CS MS bulk IN: one embedded jack, id 3
	0x05, 0x25, 0x01, 0x01, 0x03,
};

struct usb_string_descriptor_struct {
	uint8_t bLength;
	uint8_t bDescriptorType;
	uint16_t wString[];
};
static const struct usb_string_descriptor_struct string0 __attribute__((section(".rodata"))) = { 4, 3, {0x0409} };
static const struct usb_string_descriptor_struct string1 __attribute__((section(".rodata"))) = {
	sizeof(FUSB_STR_MANUFACTURER), 3, FUSB_STR_MANUFACTURER };
static const struct usb_string_descriptor_struct string2 __attribute__((section(".rodata"))) = {
	sizeof(FUSB_STR_PRODUCT), 3, FUSB_STR_PRODUCT };
static const struct usb_string_descriptor_struct string3 __attribute__((section(".rodata"))) = {
	sizeof(FUSB_STR_SERIAL), 3, FUSB_STR_SERIAL };

static const struct descriptor_list_struct {
	uint32_t lIndexValue;
	const uint8_t *addr;
	uint8_t length;
} descriptor_list[] = {
	{0x00000100, (const uint8_t *)&device_descriptor, sizeof(device_descriptor)},
	{0x00000200, config_descriptor, sizeof(config_descriptor)},
	{0x00000300, (const uint8_t *)&string0, 4},
	{0x04090301, (const uint8_t *)&string1, sizeof(FUSB_STR_MANUFACTURER)},
	{0x04090302, (const uint8_t *)&string2, sizeof(FUSB_STR_PRODUCT)},
	{0x04090303, (const uint8_t *)&string3, sizeof(FUSB_STR_SERIAL)},
};
#define DESCRIPTOR_LIST_ENTRIES ((sizeof(descriptor_list)) / (sizeof(struct descriptor_list_struct)))

#endif
