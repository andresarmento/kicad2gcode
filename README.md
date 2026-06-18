# Kicad2Gcode

A KiCad Action Plugin that generates GRBL 1.1 G-code for board cutting and drilling directly from the PCB editor — no Gerber or Excellon export required.

## Features

- **Board cutting** — reads the Edge Cuts layer and generates a milling toolpath for the board outline and internal cutouts
- **Drilling** — reads all PTH/NPTH pads and generates a drill toolpath grouped by bit diameter
- Multiple Z passes (configurable depth per pass)
- Retention tabs to keep the board attached to the stock during the last pass
- Internal cutouts are milled before the outer contour
- Nearest-neighbour drill path optimisation to minimise XY travel
- No external Python dependencies — uses KiCad's built-in polygon engine (`SHAPE_POLY_SET`)
- Compatible with KiCad 6, 7, and 8+

## Installation

1. Copy the entire plugin folder into KiCad's scripting plugins directory:

   **Windows**
   ```
   %APPDATA%\kicad\<version>\scripting\plugins\kicad2gcode\
   ```

   **Linux**
   ```
   ~/.local/share/kicad/<version>/scripting/plugins/kicad2gcode/
   ```

   **macOS**
   ```
   ~/Library/Application Support/kicad/<version>/scripting/plugins/kicad2gcode/
   ```

2. Restart KiCad, or open the PCB editor Scripting Console and run:
   ```python
   import pcbnew; pcbnew.LoadPlugins()
   ```

3. The two toolbar buttons — **Edge Cuts to G-code** and **Drill to G-code** — will appear in the PCB editor toolbar.

## Usage

### Board Cutting

1. Click the **Edge Cuts to G-code** toolbar button.
2. Fill in the options dialog and click **OK**.
3. The G-code file `<board_name>_cut.nc` is saved next to the `.kicad_pcb` file.

| Parameter | Default | Description |
|---|---|---|
| Tool diameter (mm) | 3.175 | Diameter of the end mill |
| Cut depth (mm) | -1.8 | Final Z depth (negative = below surface) |
| Depth per pass (mm) | 0.6 | Material removed per pass |
| Safe Z height (mm) | 5.0 | Z height for rapid moves |
| XY feed rate (mm/min) | 700 | Cutting feed rate |
| Plunge feed rate (mm/min) | 500 | Vertical plunge feed rate |
| Spindle RPM | 1000 | Spindle speed |
| End Z height (mm) | 25.0 | Z height at program end |
| Spindle dwell (s) | 3 | Seconds to wait after spindle start |
| Tab size (mm) | 1.0 | Width of each retention tab |
| Number of tabs | 4 | Number of tabs on the outer contour |

### Drilling

1. Click the **Drill to G-code** toolbar button.
2. Set **Tool diameter** to the same value used for board cutting (used to align hole positions with the cut origin).
3. Fill in the remaining options and click **OK**.
4. The G-code file `<board_name>_drill.nc` is saved next to the `.kicad_pcb` file.
5. The machine will pause (`M0`) between each drill diameter group so you can change the bit.

| Parameter | Default | Description |
|---|---|---|
| Tool diameter (mm) | 3.175 | Board cutter diameter — must match Edge Cuts to G-code |
| Drill depth (mm) | -2.2 | Final Z depth for drilling |
| Safe Z height (mm) | 3.0 | Z height for rapid moves |
| Plunge feed rate (mm/min) | 300 | Vertical plunge feed rate |
| Spindle RPM | 900 | Spindle speed |
| End Z height (mm) | 25.0 | Z height at program end |
| Tool change Z height (mm) | 30.0 | Z height when pausing for bit change |
| Spindle dwell (s) | 3 | Seconds to wait after spindle start |

## Output

Both actions generate plain G-code files (`.nc`) compatible with **GRBL 1.1**:

- Coordinates are in millimetres (`G21`) with absolute positioning (`G90`)
- The board origin (0, 0) is the lower-left corner of the milled outline
- The cut file mills internal cutouts first, then the outer contour with tabs
- The drill file groups holes by diameter from smallest to largest, sorted by nearest-neighbour within each group

## License

MIT — see [LICENSE](LICENSE) for details.

## Author

André Sarmento — [diybrasil@gmail.com](mailto:diybrasil@gmail.com)
