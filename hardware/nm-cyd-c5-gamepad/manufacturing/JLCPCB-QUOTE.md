# Quote the NM-CYD-C5 controller at JLCPCB

Prepared 30 October 2026 for the **100 × 70 mm board with four R4 rounded corners**.

**For PCB assembly service:** use `assembly/JLCPCB-NM-CYD-C5-RevA-R4-PCBA-Gerbers.zip` and the matching BOM/CPL files. Follow the [assembly upload guide](assembly/ASSEMBLY.md). That ZIP adds the top paste layer; the settings below describe a bare-board quote. Enable Top-side PCB Assembly for your populated-board order.

Upload **`JLCPCB-NM-CYD-C5-Gamepad-RevA-R4.zip`**. Keep it zipped. It contains only the nine required manufacturing files at the ZIP root: top/bottom copper, top/bottom solder mask, top/bottom silkscreen, the closed rounded outline, and separate plated/non-plated drill files. This is the same verified manufacturing data as `NM-CYD-C5-Gamepad-RevA-Gerbers.zip`, with a clear upload filename.

## Get the quote

1. Open the [JLCPCB PCB quote page](https://cart.jlcpcb.com/quote).
2. Choose **Standard PCB/PCBA**, click **Add gerber file**, and select the ZIP above. JLCPCB analyzes the upload to detect layers and dimensions; see its [ordering guide](https://jlcpcb.com/help/article/how-do-i-place-an-order).
3. Confirm the detected size and layer count, then use these settings for a prototype quote:

| Setting | Value |
|---|---|
| Base material | FR-4 |
| Layers | 2 |
| Dimensions | 100 × 70 mm |
| Quantity | 5 suggested for prototypes, or your preferred quantity |
| Different designs | 1 |
| Delivery format | Single PCB |
| PCB thickness | 1.6 mm |
| PCB color | Green |
| Silkscreen | White |
| Surface finish | LeadFree HASL |
| Outer copper weight | 1 oz |
| Impedance control | No |
| Gold fingers / castellated holes / edge plating | No |
| PCB assembly | Off for a bare-board quote |

The color and finish above are suggested quote choices. The current [JLCPCB form](https://cart.jlcpcb.com/quote) offers those options; quote pricing depends on the quantity, selected options, and shipping destination.

4. Open **Gerber Viewer**. Check the rounded corners, four mounting holes, fourteen four-leg button footprints, four-pin header, IC pads, tracks, and readable button labels. Confirm **100 × 70 mm**, **2 layers**, and a single board outline. Use the [local CAD preview](../preview/board.webp) for comparison.
5. Read the manufacturing quote. Add your destination in the site's shipping estimate if you also need the delivered total. A local file check does not replace JLCPCB's manufacturing review.

## What this quote includes

The Gerber ZIP specifies the **bare PCB**. Factory assembly also uses the matching [BOM and CPL files](assembly/ASSEMBLY.md) now provided in `assembly/`; see JLCPCB's [assembly file requirements](https://jlcpcb.com/help/article/pcb-assembly-faqs). Those files include the switches, IC, fitted resistors, capacitors, and header. The host cable is separate. The project's `assembly-positions.csv` remains a human assembly reference; upload the supplied `-CPL.csv` in the placement field.

The controller is still an untested hardware prototype. Confirm the CN1 cable connector fit before ordering a batch. Physical controls require the separately deferred firmware integration; current firmware remains unchanged. Full wiring, parts, and prototype checks are in the [controller guide](../README.md).

## Local verification

- Strict EasyEDA DRC: passed, zero errors.
- Eighteen nets and 117 connected pins match the schematic.
- Rounded outline: four tangent, 4 mm radius quarter-arcs.
- Plated drilling: 60 switch/header holes at 1.1 mm and 18 vias at 0.305 mm.
- Non-plated drilling: four mounting holes at 3.2 mm.
- ZIP integrity, layer contents, and file checksum verified; see [`jlcpcb-upload.json`](../reports/jlcpcb-upload.json).

Only the Gerber ZIP is uploaded in step 2. The EasyEDA project, full design package, quote guide, and BOM belong outside that upload.
