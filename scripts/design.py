"""Single source of truth for the MIDI card: parts, footprints, nets, LCSC numbers.

Both the schematic generator (gen_schematic.py) and the PCB generator
(gen_pcb.py) import this file, so the schematic and the board cannot drift apart.
"""

# Touch keys, left to right on the card, with the MCU pin that senses each one.
# The firmware (firmware/keys.h) uses the same table.
KEYS = [
    # name,  MIDI offset, black?, MCU pin number, port pin
    ("C",   0, False,  5, "PA0"),
    ("C#",  1, True,   6, "PA1"),
    ("D",   2, False,  7, "PA2"),
    ("D#",  3, True,   8, "PA3"),
    ("E",   4, False,  9, "PA4"),
    ("F",   5, False, 10, "PA5"),
    ("F#",  6, True,  11, "PA6"),
    ("G",   7, False, 12, "PA7"),
    ("G#",  8, True,  13, "PB0"),
    ("A",   9, False, 14, "PB3"),
    ("A#", 10, True,  15, "PB4"),
    ("B",  11, False, 16, "PB1"),
    ("C2", 12, False, 17, "PB6"),
]


def key_net(name):
    return "KEY_" + name.replace("#", "s")


# CH32X035G8U6 (QFN-28, 4x4 mm). Pin number -> (name shown in the symbol, net)
MCU_PINS = {
    1: ("PC15", None),
    2: ("VDD", "VBUS"),
    3: ("PC0", None),
    4: ("PC3", "SEND"),
    18: ("PB7", None),
    19: ("PB8", None),
    20: ("PB9/T1CH1", "BUZ_A"),
    21: ("PB10/T1CH2", "BUZ_B"),
    22: ("PB11", None),
    23: ("PB12", "LED"),
    24: ("PC19/SWCLK", "SWCLK"),
    25: ("PC18/SWDIO", "SWDIO"),
    26: ("PC16/UDM", "USB_DM"),
    27: ("PC17/UDP/BOOT", "USB_DP"),
    28: ("PC14", None),
    29: ("GND", "GND"),
}
for _n, _off, _blk, _pin, _port in KEYS:
    MCU_PINS[_pin] = ("PB1/PB5" if _port == "PB1" else _port, key_net(_n))

# Parts. pins: pad number -> net.  lcsc None = not assembled by JLCPCB.
PARTS = []


def part(ref, value, lib_id, footprint, pins, lcsc=None, desc="", dnp=False):
    PARTS.append(dict(ref=ref, value=value, lib_id=lib_id, footprint=footprint,
                      pins=pins, lcsc=lcsc, desc=desc, dnp=dnp))


part("U1", "CH32X035G8U6", "midicard:CH32X035G8U6",
     "midicard:QFN-28-1EP_4x4mm_P0.4mm_EP2.6x2.6mm",
     {str(k): v[1] for k, v in MCU_PINS.items()}, "C7437027",
     "RISC-V MCU, USB full speed device, runs from 5 V, no crystal")
part("J1", "USB_A_PCB_Plug", "midicard:USB_A_Plug", "midicard:USB_A_PCB_Plug",
     {"1": "VBUS", "2": "USB_DM", "3": "USB_DP", "4": "GND"}, None,
     "USB-A plug formed by the PCB edge (gold contacts, no part)")
part("C1", "100nF", "Device:C", "Capacitor_SMD:C_0402_1005Metric",
     {"1": "VBUS", "2": "GND"}, "C1525", "16 V X7R")
part("C2", "4.7uF", "Device:C", "Capacitor_SMD:C_0603_1608Metric",
     {"1": "VBUS", "2": "GND"}, "C19666", "16 V X5R")
part("R14", "1k", "Device:R", "Resistor_SMD:R_0402_1005Metric",
     {"1": "LED", "2": "LED_A"}, "C11702", "LED current limit")
part("D1", "Red", "Device:LED", "LED_SMD:LED_0603_1608Metric",
     {"1": "GND", "2": "LED_A"}, "C2286", "status LED (pad 1 = cathode)")
part("BZ1", "PKLCS1212E4001", "Device:Buzzer", "Buzzer_Beeper:Buzzer_Murata_PKLCS1212E",
     {"1": "BUZ_A", "2": "BUZ_B"}, "C113159",
     "passive piezo, driven push-pull from two pins")
part("R15", "4.7k", "Device:R", "Resistor_SMD:R_0402_1005Metric",
     {"1": "BOOT", "2": "VBUS"}, "C25900", "boot pull-up for USB bootloader")
part("JP1", "BOOT", "Jumper:SolderJumper_2_Open",
     "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm",
     {"1": "USB_DP", "2": "BOOT"}, None,
     "bridge with tweezers while plugging in = USB bootloader")
for i, (n, off, blk, pin, port) in enumerate(KEYS):
    part("R%d" % (i + 1), "1M", "Device:R", "Resistor_SMD:R_0402_1005Metric",
         {"1": key_net(n), "2": "SEND"}, "C26083", "touch charge resistor")
for i, (n, off, blk, pin, port) in enumerate(KEYS):
    part("K%d" % (i + 1), "Key " + n, "Connector:TestPoint",
         "midicard:TouchKey_" + key_net(n), {"1": key_net(n)}, None,
         "copper touch key")
for ref, net in (("TP1", "VBUS"), ("TP2", "SWDIO"), ("TP3", "SWCLK"), ("TP4", "GND")):
    part(ref, net, "Connector:TestPoint", "TestPoint:TestPoint_Pad_D1.0mm",
         {"1": net}, None, "programming pad (back side)")


def nets():
    out = {}
    for p in PARTS:
        for pad, net in p["pins"].items():
            if net:
                out.setdefault(net, []).append((p["ref"], pad))
    return out


if __name__ == "__main__":
    for n, conns in sorted(nets().items()):
        print(n, conns)
