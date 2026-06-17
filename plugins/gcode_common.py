#!/usr/bin/env python3
# gcode_common.py
# Geometry, board reading, and G-code generation functions shared by
# all plugin actions. pcbnew is imported locally inside the functions
# that need it so this module is importable outside KiCad as well.

import math


# ============================================================
# GEOMETRY
# ============================================================
def _area_assinada(pontos):
    # Gauss (shoelace) formula: area > 0 = CCW, area < 0 = CW
    area = 0.0
    n = len(pontos)
    for k in range(n):
        x1, y1 = pontos[k]
        x2, y2 = pontos[(k + 1) % n]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _inflate_poly(poly, amount_nm):
    """Call SHAPE_POLY_SET Inflate/Deflate handling API differences across KiCad versions.
    Positive amount_nm = expand outward, negative = shrink inward.
    Uses ALLOW_ACUTE_CORNERS (value 0) = mitre-like sharp corners.
    """
    import pcbnew

    ALLOW_ACUTE = 0   # CORNER_STRATEGY::ALLOW_ACUTE_CORNERS — sharpest corners
    MAX_ERR     = 5000  # 5 µm, only matters for round/chamfer strategies

    abs_nm = abs(amount_nm)

    if amount_nm >= 0:
        candidates = [
            (poly.Inflate, (abs_nm, ALLOW_ACUTE, MAX_ERR)),  # KiCad 7+
            (poly.Inflate, (abs_nm, 16, ALLOW_ACUTE)),       # KiCad 6 (segments, strategy)
            (poly.Inflate, (abs_nm, 16)),                    # KiCad 6 fallback
        ]
    else:
        deflate = getattr(poly, "Deflate", None)
        candidates = []
        if deflate:
            candidates += [
                (deflate, (abs_nm, ALLOW_ACUTE, MAX_ERR)),
                (deflate, (abs_nm, 16, ALLOW_ACUTE)),
                (deflate, (abs_nm, 16)),
            ]
        # KiCad 6 fallback: negative value passed to Inflate
        candidates += [
            (poly.Inflate, (amount_nm, ALLOW_ACUTE, MAX_ERR)),
            (poly.Inflate, (amount_nm, 16, ALLOW_ACUTE)),
            (poly.Inflate, (amount_nm, 16)),
        ]

    for fn, args in candidates:
        try:
            fn(*args)
            return
        except TypeError:
            continue

    raise RuntimeError(
        "SHAPE_POLY_SET: no compatible Inflate/Deflate signature found in this KiCad version"
    )


def _offset_caminho(pontos, raio):
    """Offset polygon using KiCad's built-in SHAPE_POLY_SET (no external dependencies).
    Positive raio = expand outward, negative = shrink inward.

    Points are received in Y-up convention (Y flipped from KiCad native).
    We un-flip Y before calling Inflate so that winding direction is correct
    for SHAPE_POLY_SET/Clipper, then re-flip the result.
    """
    import pcbnew

    NM = 1_000_000  # 1 mm = 1,000,000 nm (KiCad internal units)

    poly = pcbnew.SHAPE_POLY_SET()
    poly.NewOutline()
    pts = pontos[:-1] if len(pontos) > 1 and pontos[0] == pontos[-1] else list(pontos)
    for x, y in pts:
        poly.Append(int(round(x * NM)), int(round(-y * NM)))  # un-flip Y → KiCad native

    if raio != 0:
        _inflate_poly(poly, int(round(raio * NM)))

    if poly.OutlineCount() == 0 or poly.Outline(0).PointCount() < 3:
        raise ValueError(
            "Offset produced empty geometry (hole smaller than cutter diameter?)"
        )

    outline = poly.Outline(0)
    result = [
        (pcbnew.ToMM(outline.CPoint(i).x), -pcbnew.ToMM(outline.CPoint(i).y))  # re-flip Y
        for i in range(outline.PointCount())
    ]
    result.append(result[0])  # close the polygon
    return result


def _garantir_sentido_oposto(ref, caminho):
    if (_area_assinada(ref) > 0) == (_area_assinada(caminho) > 0):
        return list(reversed(caminho))
    return caminho


def separar_e_offsetar(contornos, raio):
    # largest area = outer contour; the rest are holes
    ordenados = sorted(contornos, key=lambda c: abs(_area_assinada(c)), reverse=True)
    externo = _offset_caminho(ordenados[0], raio)
    furos = []
    for bruto in ordenados[1:]:
        furo = _offset_caminho(bruto, -raio)
        furo = _garantir_sentido_oposto(externo, furo)
        furos.append(furo)
    return externo, furos


def calcular_offset_origem(caminhos):
    """Returns (min_x, min_y) — the translation that mover_para_origem applies."""
    todos = [p for c in caminhos for p in c]
    return min(p[0] for p in todos), min(p[1] for p in todos)


def mover_para_origem(caminhos):
    min_x, min_y = calcular_offset_origem(caminhos)
    return [[(x - min_x, y - min_y) for x, y in c] for c in caminhos]


# ============================================================
# READ BOARD OUTLINE FROM PCBNEW
#
# KiCad uses Y-down coordinates internally. We negate Y so the
# output matches the Gerber convention (Y-up) used by the
# standalone scripts.
# ============================================================
def get_board_contours(board):
    """Read board outline via pcbnew. Returns list of (x, y) point lists in mm."""
    import pcbnew

    outlines = pcbnew.SHAPE_POLY_SET()
    try:
        board.GetBoardPolygonOutlines(outlines, True)   # KiCad 8+
    except TypeError:
        board.GetBoardPolygonOutlines(outlines)         # KiCad 6/7

    if outlines.OutlineCount() == 0:
        raise RuntimeError("No board outline found. Check the Edge Cuts layer.")

    contornos = []
    for i in range(outlines.OutlineCount()):
        chain = outlines.Outline(i)
        pts = [(pcbnew.ToMM(chain.CPoint(j).x), -pcbnew.ToMM(chain.CPoint(j).y))
               for j in range(chain.PointCount())]
        if len(pts) >= 3:
            contornos.append(pts)
        for h in range(outlines.HoleCount(i)):
            hole = outlines.Hole(i, h)
            pts = [(pcbnew.ToMM(hole.CPoint(j).x), -pcbnew.ToMM(hole.CPoint(j).y))
                   for j in range(hole.PointCount())]
            if len(pts) >= 3:
                contornos.append(pts)

    if not contornos:
        raise RuntimeError("Board outline has fewer than 3 points.")

    return contornos


# ============================================================
# READ DRILL HOLES FROM PCBNEW
#
# Reads all PTH and NPTH pads and applies the same origin
# translation as the cut G-code so hole positions align.
# board_cutter_diameter must match the value used in edgecuts2gcode.
# ============================================================
def get_drill_holes(board, board_cutter_diameter):
    """Returns list of (diameter_mm, x, y) for all through-hole pads."""
    import pcbnew

    contornos = get_board_contours(board)
    raio = board_cutter_diameter / 2.0
    externo, furos_contorno = separar_e_offsetar(contornos, raio)
    min_x, min_y = calcular_offset_origem([externo] + furos_contorno)

    furos = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            attr = pad.GetAttribute()
            if attr not in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                continue
            diameter = pcbnew.ToMM(pad.GetDrillSize().x)
            if diameter <= 0:
                continue
            pos = pad.GetPosition()
            x = pcbnew.ToMM(pos.x) - min_x
            y = -pcbnew.ToMM(pos.y) - min_y   # Y flip
            furos.append((diameter, x, y))

    if not furos:
        raise RuntimeError("No through-hole pads found on this board.")

    return furos


# ============================================================
# DRILL — GROUP AND SORT
# ============================================================
def agrupar_por_diametro(furos):
    """Group (diameter, x, y) list into [(diameter, [(x,y),...]), ...] sorted small to large."""
    grupos = {}
    for diameter, x, y in furos:
        grupos.setdefault(diameter, []).append((x, y))
    chaves = sorted(grupos.keys(), key=lambda d: (d is None, d))
    return [(d, grupos[d]) for d in chaves]


def ordenar_vizinho_mais_proximo(furos, inicio=(0.0, 0.0)):
    """Greedy nearest-neighbour sort to minimise XY travel. O(n²)."""
    restantes = list(furos)
    ordenados = []
    px, py = inicio
    while restantes:
        idx = min(range(len(restantes)),
                  key=lambda i: (restantes[i][0] - px) ** 2 + (restantes[i][1] - py) ** 2)
        px, py = restantes[idx]
        ordenados.append(restantes.pop(idx))
    return ordenados


# ============================================================
# DEPTH PASSES
# ============================================================
def calcular_profundidades(cut_depth, multi_depth):
    if multi_depth <= 0:
        raise ValueError("Depth per pass must be positive")
    eps = 1e-6
    depths = []
    z = 0.0
    while z > cut_depth + eps:
        z -= multi_depth
        if z < cut_depth + eps:
            z = cut_depth
        depths.append(z)
    return depths


# ============================================================
# TABS / SEGMENTS  (cut only)
# ============================================================
def _distancias_acumuladas(caminho):
    cum = [0.0]
    for i in range(len(caminho) - 1):
        x1, y1 = caminho[i]
        x2, y2 = caminho[i + 1]
        cum.append(cum[-1] + math.hypot(x2 - x1, y2 - y1))
    return cum


def _rotacionar_para_meio_do_primeiro_segmento(caminho):
    # rotate closed path so tab 0 falls on a straight segment, not a corner
    x0, y0 = caminho[0]
    x1, y1 = caminho[1]
    meio = ((x0 + x1) / 2, (y0 + y1) / 2)
    return [meio] + caminho[1:-1] + [caminho[0], meio]


def _ponto_na_distancia(caminho, cum, distancia):
    for i in range(len(cum) - 1):
        if cum[i] <= distancia <= cum[i + 1]:
            L = cum[i + 1] - cum[i]
            if L == 0:
                return caminho[i]
            t = (distancia - cum[i]) / L
            x1, y1 = caminho[i]
            x2, y2 = caminho[i + 1]
            return (x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
    return caminho[-1]


def calcular_segmentos(caminho, gap_size, tool_diameter, num_gaps):
    vao = gap_size + tool_diameter
    caminho = _rotacionar_para_meio_do_primeiro_segmento(caminho)
    cum = _distancias_acumuladas(caminho)
    perimetro = cum[-1]
    espacamento = perimetro / num_gaps
    if vao >= espacamento:
        raise ValueError("Tab size too large for the number of tabs / perimeter")
    segs = []
    for i in range(num_gaps):
        inicio = i * espacamento + vao
        fim = (i + 1) * espacamento
        pts = [_ponto_na_distancia(caminho, cum, inicio)]
        for j in range(1, len(cum) - 1):
            if inicio < cum[j] < fim:
                pts.append(caminho[j])
        pts.append(_ponto_na_distancia(caminho, cum, fim))
        segs.append(pts)
    return segs


# ============================================================
# G-CODE GENERATION — BOARD CUT
# ============================================================
def gerar_gcode_corte(segs_externo, furos, profundidades, o):
    lines = []
    add = lines.append

    add("(G-CODE generated BY Gerber2Gcode KiCad Plugin - Board Cut)")
    add("")
    add("G21")          # units in millimetres
    add("G90")          # absolute coordinates
    add("G94")          # feed rate in units per minute
    add("G17")          # XY plane
    add("M5")           # spindle off
    add(f"G0 Z{o['SAFE_Z']:.3f}")
    add("G0 X0.0000 Y0.0000")
    add(f"M3 S{o['SPINDLE_RPM']}")
    add(f"G04 P{o['DWELL']}")
    add("")

    # holes/cutouts first (closed loop, no tabs)
    for furo in furos:
        for z in profundidades:
            x0, y0 = furo[0]
            add(f"G0 X{x0:.3f} Y{y0:.3f}")
            add(f"G1 Z{z:.3f} F{o['FEED_Z']:.1f}")
            for x, y in furo[1:]:
                add(f"G1 X{x:.3f} Y{y:.3f} F{o['FEED_XY']:.1f}")
            add(f"G0 Z{o['SAFE_Z']:.3f}")

    # outer contour with tabs
    for z in profundidades:
        for seg in segs_externo:
            x0, y0 = seg[0]
            add(f"G0 X{x0:.3f} Y{y0:.3f}")
            add(f"G1 Z{z:.3f} F{o['FEED_Z']:.1f}")
            for x, y in seg[1:]:
                add(f"G1 X{x:.3f} Y{y:.3f} F{o['FEED_XY']:.1f}")
            add(f"G0 Z{o['SAFE_Z']:.3f}")

    add(f"G0 Z{o['END_Z']:.3f}")
    add("M5")
    add("M2")

    return "\n".join(lines)


# ============================================================
# G-CODE GENERATION — DRILL
# ============================================================
def gerar_gcode_furacao(grupos, o):
    lines = []
    add = lines.append

    add("(G-CODE generated BY Gerber2Gcode KiCad Plugin - Drill)")
    add("")
    add("G21")          # units in millimetres
    add("G90")          # absolute coordinates
    add("G94")          # feed rate in units per minute
    add("G17")          # XY plane
    add("M5")           # ensure spindle is off
    add(f"G0 Z{o['SAFE_Z']:.3f}")
    add("G0 X0.0000 Y0.0000")
    add("")

    for diameter, furos in grupos:
        if diameter is None:
            add("(Bit: unknown diameter)")
        else:
            add(f"(Bit: {diameter:.3f}mm — {len(furos)} holes)")
        add("M5")
        add(f"G0 Z{o['TOOLCHANGE_Z']:.3f}")
        add("M0")           # pause: change bit and resume
        add(f"M3 S{o['SPINDLE_RPM']}")
        add(f"G04 P{o['DWELL']}")
        add("")

        for x, y in furos:
            add(f"G0 X{x:.3f} Y{y:.3f}")
            add(f"G1 Z{o['DRILL_DEPTH']:.3f} F{o['FEED_Z']:.1f}")
            add(f"G0 Z{o['SAFE_Z']:.3f}")

        add("")

    add(f"G0 Z{o['END_Z']:.3f}")
    add("M5")
    add("M2")

    return "\n".join(lines)
