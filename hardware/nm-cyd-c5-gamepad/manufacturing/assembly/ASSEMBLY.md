# JLCPCB assembly files — NM-CYD-C5 Gamepad Rev A, R4 corners

Prepared 30 October 2026 from the native EasyEDA placement export of the same rounded board as the Gerbers. The files request **32 fitted components on the top side**. The circuit, PCB layout, and firmware are unchanged.

## Files to upload

| JLCPCB upload field | File |
|---|---|
| PCB / Gerber | `JLCPCB-NM-CYD-C5-RevA-R4-PCBA-Gerbers.zip` in this assembly folder |
| BOM | `JLCPCB-NM-CYD-C5-RevA-R4-BOM.csv` |
| CPL / Pick & Place | `JLCPCB-NM-CYD-C5-RevA-R4-CPL.csv` |

Enable **PCB Assembly** and choose **Top** as the assembly side. Upload the BOM and CPL CSVs individually in their respective fields, then use **Process BOM & CPL**. JLCPCB's [CPL requirements](https://jlcpcb.com/help/article/pick-place-file-for-pcb-assembly) and [BOM requirements](https://jlcpcb.com/help/article/bill-of-materials-for-pcb-assembly) are the format references.

Use the **PCBA Gerber ZIP above** for this order, replacing the previous bare-board ZIP if already uploaded. It contains the same nine PCB/drill files plus the top solder-paste layer for factory assembly. The paste layer retains the native EasyEDA openings on all **56 fitted SMT pads** and omits the four R15/R16 pad openings. Through-hole switches/header and mounting holes have no paste openings. JLCPCB [recommends supplying the paste layer](https://jlcpcb.com/help/article/instructions-for-ordering) for stencil preparation. The copper, solder mask, drilling, and R4 outline remain identical to the bare-board ZIP.

The supplied CPL uses millimeter centroids and native EasyEDA counterclockwise angles. Its headers are `Designator, Mid X, Mid Y, Layer, Rotation`. Negative Y coordinates are intentional: the Gerbers and native placement export share an origin at the upper-left, with the board spanning Y = -70 to 0 mm. No independent axis flip or origin shift was applied. The older `assembly-positions.csv` uses distances from the top and is a human assembly reference; use the CPL provided here for this upload.

## Parts to match

| References | Quantity per board | JLCPCB / LCSC part | Part |
|---|---:|---|---|
| U1 | 1 | [C1542498](https://jlcpcb.com/partdetail/NXPSemicon-PCA9555D112/C1542498) | NXP PCA9555D,112, SO24 |
| SW1–SW14 | 14 | [C93157](https://jlcpcb.com/partdetail/OmronElectronics-B3F1000/C93157) | Omron B3F-1000, through-hole |
| R1–R14 | 14 | [C25804](https://jlcpcb.com/partdetail/0603WAF1002T5E/C25804) | 10 kΩ, 1%, 0603 |
| C1, C2 | 2 | [C14663](https://jlcpcb.com/partdetail/Yageo-CC0603KRX7R9BB104/C14663) | 100 nF, 50 V, X7R, 0603 |
| J1 | 1 | [C2691448](https://jlcpcb.com/partdetail/Xfcn-PZ254V_1104P/C2691448) | PZ254V-11-04P, 1 × 4 through-hole header |

**R15 and R16 are intentionally omitted from both files. Leave those pads empty.** They are optional I²C pull-ups; the NM-CYD-C5 already provides bus pull-ups. All fourteen button pull-ups R1–R14 remain fitted.

JLCPCB currently lists the B3F-1000 switches and PZ254V-11-04P header for its **Wave Soldering** assembly process. The [assembly FAQ](https://jlcpcb.com/help/article/pcb-assembly-faqs) describes how those through-hole parts are handled. Ensure these fifteen parts remain selected for assembly, as well as the seventeen SMT parts. The final quote may include through-hole labor, setup, sourcing, or fixture costs.

Part-library listings were checked, but stock has not been reserved and availability for your quantity is determined during matching. Confirm all **five part types** are matched to the exact codes above. The BOM quantities are per board; JLCPCB applies the order's assembly quantity. An unmatched part may be left unassembled, so resolve missing parts before confirming the order.

## Placement preview checks

The CSVs have been checked against the CAD, but JLCPCB's online placement preview has not yet been reviewed. Check it before confirming manufacturing:

- All **32 components** appear on the top side, and R15/R16 are empty.
- **U1:** notch faces the cable/header edge. In a top view, pin 1 is the **upper-left** lead. CPL center is (50.000, -36.000) mm, native rotation 270°. Pin 1 is approximately (44.920, -29.015) mm in the Gerber frame. Align the actual pin-1 marker with that pad; a library model can use a different visual zero-angle convention.
- **J1:** square pad/pin 1 is at the left end of the header and is the 3V3 connection. Pins run 3V3, SDA, SCL, GND from left to right in the top view.
- **SW1–SW14:** the four leads align with the rectangular 6.5 × 4.5 mm hole pattern. Their actuators face up, on the component side.
- **C1** is vertical; **C2** and R1–R14 are horizontal. These ceramic capacitors and resistors are nonpolar.

Compare the preview with the [CAD board view](../../preview/board.webp). If any part is shifted, mirrored, or its pin-1 marker is on the wrong pad, correct the placement in the service's viewer or have the placement file corrected before manufacturing.

## Checks performed

`prepare_jlcpcb_assembly.py` converts the native export to ASCII CSV, filters R15/R16, and verifies centroids, top-side assignment, and rotations against the actual PCB source. It also compares reference sets and quantities between the BOM and CPL and checks U1/J1 pin 1 against the saved pad coordinates. It verifies all native paste openings against the SMT pads, removes only the four DNP openings, and checks that the other nine Gerber/drill files remain byte-identical. The original placement and paste exports are retained in `source/`. See [`pcba-validation.json`](../../reports/pcba-validation.json).

This prepares the assembly data; it does not validate an assembled prototype or add the deferred controller firmware support. The [main controller guide](../../README.md) covers wiring and hardware testing.
