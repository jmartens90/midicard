# USB MIDI business card firmware (CH32X035G8U6)
#   make            build midicard.bin / .hex / .elf
#   make flash      program with a WCH-LinkE on the back pads (ch32fun minichlink)
# Or flash over USB with the BOOT jumper bridged: wchisp flash midicard.bin
all : build

TARGET:=midicard
TARGET_MCU:=CH32X035
TARGET_MCU_PACKAGE:=CH32X035G8U6
ADDITIONAL_C_FILES:=ch32fun/extralibs/fsusb.c
CH32FUN:=$(CURDIR)/ch32fun/ch32fun
EXTRA_CFLAGS:=
NEWLIB?=$(firstword $(wildcard /usr/lib/picolibc/riscv64-unknown-elf/include /usr/include/newlib))

include ch32fun/ch32fun/ch32fun.mk

flash : cv_flash
clean : cv_clean
