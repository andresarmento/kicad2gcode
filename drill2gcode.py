#!/usr/bin/env python3
# drill2gcode.py
# KiCad Action Plugin: reads through-hole pads and generates GRBL 1.1
# G-code for drilling, without exporting Excellon files.
#
# Hole positions are aligned with the cut G-code: uses the same
# board cutter diameter (TOOL_DIAMETER) to compute the
# same origin translation as edgecuts2gcode.

import os

import pcbnew
import wx

from gcode_common import (
    get_drill_holes,
    agrupar_por_diametro,
    ordenar_vizinho_mais_proximo,
    gerar_gcode_furacao,
)

PLUGIN_NAME = "Drill to G-code"

# ============================================================
# OPTIONS
# ============================================================
DEFAULTS = {
    "TOOL_DIAMETER":        3.175,
    "DRILL_DEPTH":           -2.2,
    "SAFE_Z":                 3.0,
    "FEED_Z":               300.0,
    "SPINDLE_RPM":           900,
    "END_Z":                 25.0,
    "TOOLCHANGE_Z":          30.0,
    "DWELL":                   3,
}

LABELS = {
    "TOOL_DIAMETER":         "Tool diameter (mm) — must match Edge Cuts to G-code",
    "DRILL_DEPTH":           "Drill depth (mm, negative)",
    "SAFE_Z":                "Safe Z height (mm)",
    "FEED_Z":                "Plunge feed rate (mm/min)",
    "SPINDLE_RPM":           "Spindle RPM",
    "END_Z":                 "End Z height (mm)",
    "TOOLCHANGE_Z":          "Tool change Z height (mm)",
    "DWELL":                 "Spindle dwell (s)",
}

INT_KEYS = {"SPINDLE_RPM", "DWELL"}


# ============================================================
# OPTIONS DIALOG
# ============================================================
class DrillOptionsDialog(wx.Dialog):
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
class Drill2GcodePlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = PLUGIN_NAME
        self.category = "Manufacturing"
        self.description = "Generate GRBL 1.1 G-code for drilling (no Excellon export needed)"
        self.show_toolbar_button = True
        icon_path = os.path.join(os.path.dirname(__file__), "icon_drill.png")
        self.icon_file_name = icon_path if os.path.isfile(icon_path) else ""

    def Run(self):
        board = pcbnew.GetBoard()

        dlg = DrillOptionsDialog(None)
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
            furos = get_drill_holes(board, opts["TOOL_DIAMETER"])
            grupos = agrupar_por_diametro(furos)

            # sort holes in each group by nearest neighbour;
            # each group starts from the last hole of the previous group
            pos_inicio = (0.0, 0.0)
            grupos_ordenados = []
            for diameter, lista in grupos:
                lista_ord = ordenar_vizinho_mais_proximo(lista, pos_inicio)
                grupos_ordenados.append((diameter, lista_ord))
                if lista_ord:
                    pos_inicio = lista_ord[-1]

            gcode = gerar_gcode_furacao(grupos_ordenados, opts)

            board_file = board.GetFileName()
            base = os.path.splitext(board_file)[0] if board_file else \
                   os.path.join(os.path.expanduser("~"), "board")
            output_file = base + "_drill.nc"

            with open(output_file, "w") as f:
                f.write(gcode)

            total = sum(len(lista) for _, lista in grupos_ordenados)
            resumo = ", ".join(
                f"{len(lista)}x{d:.3f}mm" for d, lista in grupos_ordenados
            )
            wx.MessageBox(
                f"{total} holes ({resumo})\n\nG-code saved to:\n{output_file}",
                f"{PLUGIN_NAME} — Done",
                wx.OK | wx.ICON_INFORMATION,
            )

        except Exception as e:
            wx.MessageBox(str(e), f"{PLUGIN_NAME} — Error", wx.OK | wx.ICON_ERROR)
