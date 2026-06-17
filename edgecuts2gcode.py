#!/usr/bin/env python3
# edgecuts2gcode.py
# KiCad Action Plugin: reads Edge Cuts layer and generates GRBL 1.1
# G-code for board cutting, without exporting Gerber files.

import os

import pcbnew
import wx

from gcode_common import (
    get_board_contours,
    separar_e_offsetar,
    mover_para_origem,
    calcular_profundidades,
    calcular_segmentos,
    gerar_gcode_corte,
)

PLUGIN_NAME = "Edge Cuts to G-code"

# ============================================================
# OPTIONS
# ============================================================
DEFAULTS = {
    "TOOL_DIAMETER": 3.175,
    "CUT_DEPTH":     -1.8,
    "MULTI_DEPTH":    0.6,
    "SAFE_Z":         5.0,
    "FEED_XY":      700.0,
    "FEED_Z":       500.0,
    "SPINDLE_RPM":  1000,
    "END_Z":         25.0,
    "DWELL":            3,
    "GAP_SIZE":       1.0,
    "NUM_GAPS":         4,
}

LABELS = {
    "TOOL_DIAMETER": "Tool diameter (mm)",
    "CUT_DEPTH":     "Cut depth (mm, negative)",
    "MULTI_DEPTH":   "Depth per pass (mm, positive)",
    "SAFE_Z":        "Safe Z height (mm)",
    "FEED_XY":       "XY feed rate (mm/min)",
    "FEED_Z":        "Plunge feed rate (mm/min)",
    "SPINDLE_RPM":   "Spindle RPM",
    "END_Z":         "End Z height (mm)",
    "DWELL":         "Spindle dwell (s)",
    "GAP_SIZE":      "Tab size (mm)",
    "NUM_GAPS":      "Number of tabs",
}

INT_KEYS = {"SPINDLE_RPM", "DWELL", "NUM_GAPS"}


# ============================================================
# OPTIONS DIALOG
# ============================================================
class CutOptionsDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title=f"{PLUGIN_NAME} — Options",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=12)
        grid.AddGrowableCol(1)

        self._fields = {}
        for key, label in LABELS.items():
            grid.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            ctrl = wx.TextCtrl(self, value=str(DEFAULTS[key]), size=(110, -1))
            grid.Add(ctrl, 1, wx.EXPAND)
            self._fields[key] = ctrl

        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)

        main = wx.BoxSizer(wx.VERTICAL)
        main.Add(grid, 1, wx.ALL | wx.EXPAND, 12)
        main.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizerAndFit(main)

    def get_options(self):
        opts = {}
        for key, ctrl in self._fields.items():
            text = ctrl.GetValue().strip().replace(",", ".")
            try:
                opts[key] = int(text) if key in INT_KEYS else float(text)
            except ValueError:
                raise ValueError(f"Invalid value for '{LABELS[key]}': {text!r}")
        return opts


# ============================================================
# ACTION PLUGIN
# ============================================================
class EdgeCuts2GcodePlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = PLUGIN_NAME
        self.category = "Manufacturing"
        self.description = "Generate GRBL 1.1 G-code for board cutting (no Gerber export needed)"
        self.show_toolbar_button = True
        icon_path = os.path.join(os.path.dirname(__file__), "icon_cut.png")
        self.icon_file_name = icon_path if os.path.isfile(icon_path) else ""

    def Run(self):
        board = pcbnew.GetBoard()

        dlg = CutOptionsDialog(None)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return

        try:
            opts = dlg.get_options()
        except ValueError as e:
            wx.MessageBox(str(e), f"{PLUGIN_NAME} — Error", wx.OK | wx.ICON_ERROR)
            dlg.Destroy()
            return
        finally:
            dlg.Destroy()

        try:
            contornos = get_board_contours(board)
            raio = opts["TOOL_DIAMETER"] / 2.0
            externo, furos = separar_e_offsetar(contornos, raio)

            todos = mover_para_origem([externo] + furos)
            externo, furos = todos[0], todos[1:]

            profundidades = calcular_profundidades(opts["CUT_DEPTH"], opts["MULTI_DEPTH"])
            segs = calcular_segmentos(
                externo, opts["GAP_SIZE"], opts["TOOL_DIAMETER"], opts["NUM_GAPS"]
            )
            gcode = gerar_gcode_corte(segs, furos, profundidades, opts)

            board_file = board.GetFileName()
            base = os.path.splitext(board_file)[0] if board_file else \
                   os.path.join(os.path.expanduser("~"), "board")
            output_file = base + "_cut.nc"

            with open(output_file, "w") as f:
                f.write(gcode)

            wx.MessageBox(
                f"G-code saved to:\n{output_file}",
                f"{PLUGIN_NAME} — Done",
                wx.OK | wx.ICON_INFORMATION,
            )

        except Exception as e:
            wx.MessageBox(str(e), f"{PLUGIN_NAME} — Error", wx.OK | wx.ICON_ERROR)
