#ifndef _FUNCONFIG_H
#define _FUNCONFIG_H

// CH32X035 straight off USB VBUS (5 V), internal 48 MHz HSI, no crystal.
#define FUNCONF_USE_HSI             1
#define FUNCONF_SYSTEM_CORE_CLOCK   48000000
#define FUNCONF_USE_5V_VDD          1
#define FUNCONF_SYSTICK_USE_HCLK    1
#define FUNCONF_USE_DEBUGPRINTF     0
#define FUNCONF_USE_USBPRINTF       0
#define FUNCONF_ENABLE_HPE          0
#define FUNCONF_DEBUG_HARDFAULT     0

#endif
