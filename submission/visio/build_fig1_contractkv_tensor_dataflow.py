"""Build ContractKV Figure 1 as a tensor-centric architecture and state pipeline."""

from __future__ import annotations

import json
from pathlib import Path


OUT = Path(__file__).with_name("fig1_contractkv_visual.scene.json")

INK = "#1F2937"
GRAY = "#667085"
GRAY_LINE = "#7B8794"
GRAY_FILL = "#F6F8FA"
BLUE = "#2468B4"
BLUE_DARK = "#174E91"
BLUE_FILL = "#EAF3FC"
ORANGE = "#D97724"
ORANGE_FILL = "#FFF1E2"
TEAL = "#187D78"
TEAL_FILL = "#E7F6F3"
GREEN = "#2F7D43"
GREEN_FILL = "#E9F6ED"
RED = "#B93835"
RED_FILL = "#FFF0EF"

SEG = {
    "SYS": "#D7E6F6",
    "CODE": "#BFD8EE",
    "DOC": "#A9CBE5",
    "OBS": "#F2C590",
    "QUERY": "#E1E5EA",
    "OUT": "#B9E0D8",
}

nodes: list[dict] = []
edges: list[dict] = []


def node(node_id, kind, x, y, w, h, label="", container=None, **extra):
    item = {"id": node_id, "type": kind, "x": x, "y": y,
            "w": w, "h": h, "text": label}
    if container:
        item["container_id"] = container
    item.update(extra)
    nodes.append(item)
    return node_id


def text(node_id, x, y, w, h, label, container=None, size=14.0,
         bold=False, color=INK, align=1):
    size = max(size, 14.5)
    return node(node_id, "text_block", x, y, w, h, label, container,
                style={"font_size_pt": size,
                       "font_weight": "bold" if bold else "normal",
                       "text_color": color, "text_align": align,
                       "text_fit": "shrink_to_fit"})


def box(node_id, x, y, w, h, label="", line=BLUE, fill="#FFFFFF",
        container=None, size=14.0, bold=True, rounding=0.035):
    size = max(size, 14.0)
    return node(node_id, "process_box", x, y, w, h, label, container,
                style={"fill": fill, "line": line, "line_weight_pt": 1.0,
                       "rounding_in": rounding, "font_size_pt": size,
                       "font_weight": "bold" if bold else "normal",
                       "text_color": INK, "text_fit": "shrink_to_fit"})


def region(node_id, x, y, w, h, label, line, fill, container=None,
           dashed=True, size=16.0):
    return node(node_id, "dashed_region" if dashed else "group_container",
                x, y, w, h, label, container,
                style={"fill": fill, "line": line, "line_weight_pt": 1.05,
                       "rounding_in": 0.045, "font_size_pt": size,
                       "font_weight": "bold", "text_color": INK,
                       "text_fit": "shrink_to_fit"})


def connect(edge_id, source, target, color=GRAY_LINE, dashed=False,
            points=None, weight=1.2, end_arrow=4):
    item = {"id": edge_id, "type": "arrow_connector", "from": source,
            "to": target, "route": "orthogonal",
            "style": {"line": color, "line_weight_pt": weight,
                      "line_pattern": "dash" if dashed else 1,
                      "end_arrow": end_arrow}}
    if points:
        item["points"] = points
    edges.append(item)


def cell(node_id, x, y, w, h, fill, line, container=None, label="",
         size=14.0, color=INK, bold=False):
    return box(node_id, x, y, w, h, label, line, fill, container, size, bold,
               rounding=0.0)


def matrix(node_id, x, y, w, h, rows, cols, row_colors, container=None,
           line=GRAY_LINE, shades=None):
    return node(node_id, "feature_map_grid", x, y, w, h, "", container,
                rows=rows, cols=cols, row_colors=row_colors,
                column_shades=shades or [0.00, 0.06, 0.12, 0.02] *
                ((cols + 3) // 4),
                style={"line": line, "grid_line": line,
                       "line_weight_pt": 0.75,
                       "grid_line_weight_pt": 0.55},
                allow_overlap=True)


def tensor_stack(prefix, x, y, w, h, rows, cols, colors, container=None,
                 layers=3, dx=0.055, dy=-0.045, line=GRAY_LINE):
    ids = []
    for layer in reversed(range(layers)):
        nid = f"{prefix}_{layer}"
        matrix(nid, x + layer * dx, y + layer * dy, w, h, rows, cols,
               colors, container, line)
        ids.append(nid)
    return ids


def token_vector(prefix, x, y, h, spec, container=None, cell_w=0.075,
                 gap=0.018, labels=False):
    ids = []
    current = x
    for idx, (kind, count) in enumerate(spec):
        width = max(0.20, count * cell_w)
        nid = f"{prefix}_{idx}_{kind}"
        matrix(nid, current, y, width, h, 1, count, [SEG[kind]], container)
        if labels:
            text(f"{nid}_label", current, y - 0.16, width, 0.13, kind,
                 container, 13.5, True, INK)
        ids.append(nid)
        current += width + gap
    return ids, current - x


def block_vector(prefix, x, y, count, active, container=None, cell_w=0.12,
                 cell_h=0.19, fill=TEAL_FILL, line=TEAL):
    ids = []
    for i in range(count):
        ids.append(cell(f"{prefix}_{i}", x + i * cell_w, y, cell_w,
                        cell_h, fill if i < active else "#FFFFFF",
                        line if i < active else GRAY_LINE, container))
    return ids


def decision(node_id, x, y, w, h, label, color, container=None):
    node(node_id, "decision_diamond", x, y, w, h, "", container,
         style={"fill": "#FFFFFF", "line": color,
                "line_weight_pt": 1.3})
    text(f"{node_id}_label", x + 0.07, y + 0.12, w - 0.14, h - 0.24,
         label, container, 13.5, True, INK)
    return node_id


def short_stage_arrow(prefix, x, y0, y1, color, container):
    node(f"{prefix}_a", "junction_point", x, y0, 0.035, 0.035, "",
         container, role="boundary_anchor", style={"fill": color,
                                                    "line": color})
    node(f"{prefix}_b", "junction_point", x, y1, 0.035, 0.035, "",
         container, role="boundary_anchor", style={"fill": color,
                                                    "line": color})
    connect(prefix, f"{prefix}_a", f"{prefix}_b", color, weight=2.0)


# Header and consolidated legend.
text("title", 4.72, 0.00, 4.30, 0.29, "ContractKV", size=25.0, bold=True)
text("subtitle", 4.05, 0.31, 5.70, 0.18,
     "Semantic-physical co-design for safe prefix reuse",
     size=14.5, color=GRAY)
region("legend", 9.50, 0.03, 4.50, 0.57, "", GRAY_LINE, "#FFFFFF",
       dashed=False, size=14.0)
for i, (label, line, fill) in enumerate([
    ("Private", GRAY_LINE, GRAY_FILL), ("Compile", BLUE, BLUE_FILL),
    ("Verify", ORANGE, ORANGE_FILL), ("Shared KV", TEAL, TEAL_FILL),
]):
    x = 9.66 + i * 0.84
    box(f"legend_swatch_{i}", x, 0.13, 0.21, 0.12, "", line, fill,
        "legend", 14.0)
    text(f"legend_label_{i}", x + 0.24, 0.09, 0.58, 0.20, label,
         "legend", 13.5, False, INK, 0)
node("legend_data_a", "junction_point", 12.92, 0.39, 0.03, 0.03, "",
     "legend", style={"fill": INK, "line": INK})
node("legend_data_b", "junction_point", 13.18, 0.39, 0.03, 0.03, "",
     "legend", style={"fill": INK, "line": INK})
connect("legend_data", "legend_data_a", "legend_data_b", INK, weight=1.8)
text("legend_data_text", 13.23, 0.31, 0.54, 0.16, "data", "legend",
     13.5, False, INK, 0)
node("legend_meta_a", "junction_point", 12.92, 0.52, 0.03, 0.03, "",
     "legend", style={"fill": GRAY_LINE, "line": GRAY_LINE})
node("legend_meta_b", "junction_point", 13.18, 0.52, 0.03, 0.03, "",
     "legend", style={"fill": GRAY_LINE, "line": GRAY_LINE})
connect("legend_meta", "legend_meta_a", "legend_meta_b", GRAY_LINE,
        dashed=True, weight=1.2)
text("legend_meta_text", 13.23, 0.44, 0.60, 0.16, "metadata", "legend",
     13.5, False, INK, 0)

text("panel_a_title", 0.62, 0.68, 7.85, 0.22,
     "(a) ContractKV Control Plane", size=18.0, bold=True)
text("panel_b_title", 9.28, 0.68, 4.55, 0.22,
     "(b) Execution-State Dataflow", size=18.0, bold=True)
region("arch", 0.12, 0.92, 8.58, 6.37, "", GRAY_LINE, "#FCFDFE",
       dashed=True, size=14.0)
region("flow", 8.90, 0.92, 5.15, 6.37, "", GRAY_LINE, "#FCFDFE",
       dashed=True, size=14.0)

# Ingress: a structured prompt and its deployment contract are separate inputs.
region("ingress", 0.34, 1.10, 8.15, 0.60, "Structured request ingress",
       GRAY_LINE, "#FFFFFF", "arch", dashed=False, size=16.0)
text("ingress_prompt_label", 0.55, 1.31, 0.88, 0.15, "Segmented prompt",
     "ingress", 14.0, True, INK, 0)
token_vector("ingress_tokens", 1.48, 1.30, 0.21,
             [("SYS", 3), ("OBS", 2), ("CODE", 5),
              ("DOC", 3), ("QUERY", 2)], "ingress", 0.060, 0.014)
text("ingress_names", 1.48, 1.51, 2.03, 0.17,
     "SYS     OBS       CODE        DOC      QUERY", "ingress",
     15.0, True, INK, 0)
text("ingress_contract_label", 5.72, 1.20, 1.30, 0.14,
     "Contract envelope", "ingress", 14.0, True, INK)
for i, label in enumerate(["scope", "budget", "epoch"]):
    cell(f"ingress_contract_{i}", 5.74 + i * 0.69, 1.40, 0.63, 0.18,
         BLUE_FILL, BLUE, "ingress", label, 13.5, INK, True)

# CALC: the core compiler is rendered as four explicit data transformations.
region("calc", 0.34, 1.82, 5.85, 1.86,
       "CALC: contract-aware layout compiler", BLUE, BLUE_FILL,
       "arch", dashed=True, size=16.5)
text("calc_contract_title", 0.49, 2.12, 1.18, 0.16,
     "Segment-contract tensor", "calc", 14.0, True, INK)
matrix("calc_contract_tensor", 0.98, 2.41, 0.66, 0.80, 5, 4,
       [SEG["SYS"], SEG["CODE"], SEG["DOC"], SEG["OBS"], SEG["QUERY"]],
       "calc", BLUE)
for i, label in enumerate(["SYS", "CODE", "DOC", "OBS", "QUERY"]):
    text(f"calc_contract_row_{i}", 0.45, 2.40 + i * 0.16, 0.49, 0.14,
         label, "calc", 13.5, True, INK, 2)
text("calc_contract_cols", 0.94, 3.24, 0.74, 0.18,
     "type   stable   pred   scope", "calc", 13.5, False, INK)

text("calc_posc_title", 1.78, 2.12, 1.52, 0.16, "Segment dependency graph",
     "calc", 14.0, True, INK)
for nid, x, y, label, fill, line in [
    ("posc_sys", 1.80, 2.48, "SYS", SEG["SYS"], BLUE),
    ("posc_code", 2.31, 2.32, "CODE", SEG["CODE"], BLUE),
    ("posc_doc", 2.31, 2.62, "DOC", SEG["DOC"], BLUE),
    ("posc_obs", 2.31, 2.92, "OBS", SEG["OBS"], ORANGE),
    ("posc_query", 2.86, 2.92, "QUERY", SEG["QUERY"], GRAY_LINE),
]:
    width = {"SYS": 0.44, "CODE": 0.56, "DOC": 0.56,
             "OBS": 0.56, "QUERY": 0.76}[label]
    box(nid, x, y, width, 0.23, label,
        line, fill, "calc", 13.5, True)
for eid, src, dst in [
    ("posc_sys_code", "posc_sys:right", "posc_code:left"),
    ("posc_sys_doc", "posc_sys:right", "posc_doc:left"),
    ("posc_sys_obs", "posc_sys:right", "posc_obs:left"),
    ("posc_obs_query", "posc_obs:right", "posc_query:left"),
]:
    connect(eid, src, dst, GRAY_LINE, weight=1.2)

text("calc_ledger_title", 3.64, 2.12, 0.94, 0.16, "Residency ledger",
     "calc", 14.0, True, INK)
tensor_stack("calc_ledger", 3.65, 2.48, 0.92, 0.34, 2, 8,
             [TEAL_FILL, BLUE_FILL], "calc", layers=3, dx=0.055, dy=-0.045,
             line=TEAL)
block_vector("calc_lcp", 3.66, 3.00, 7, 5, "calc", 0.13, 0.18,
             TEAL_FILL, TEAL)
text("calc_lcp_label", 3.64, 3.20, 0.98, 0.18,
     "resident LCP mask", "calc", 15.0, True, INK)

text("calc_layout_title", 4.77, 2.12, 1.19, 0.16,
     "Legal-layout stack", "calc", 14.0, True, INK)
layout_specs = [
    [("SYS", 2), ("OBS", 2), ("CODE", 2)],
    [("SYS", 2), ("CODE", 2), ("OBS", 2)],
    [("SYS", 2), ("CODE", 2), ("DOC", 2)],
    [("SYS", 2), ("CODE", 2), ("DOC", 2), ("OBS", 1)],
]
for i, spec in enumerate(layout_specs):
    text(f"calc_level_{i}", 4.74, 2.40 + i * 0.25, 0.24, 0.14,
         f"L{i}", "calc", 13.5, True, TEAL if i == 3 else INK)
    token_vector(f"calc_layout_{i}", 5.00, 2.42 + i * 0.25, 0.14,
                 spec, "calc", 0.034, 0.006)
    box(f"calc_utility_{i}", 5.70, 2.46 + i * 0.25,
        [0.12, 0.18, 0.24, 0.32][i], 0.055, "",
        TEAL if i == 3 else BLUE, TEAL if i == 3 else BLUE,
        "calc", 13.5)
text("calc_utility_label", 5.42, 3.39, 0.64, 0.18, "reuse utility",
     "calc", 15.0, True, INK)
connect("calc_contract_posc", "calc_contract_tensor:right", "posc_sys:left",
        BLUE, weight=1.7)
connect("calc_posc_ledger", "posc_query:right", "calc_ledger_0:left",
        BLUE, weight=1.7)
connect("calc_ledger_layout", "calc_lcp_6:right", "calc_layout_2_0_SYS:left",
        BLUE, weight=1.7)

# Frozen policy and reusable certificate objects, at the same abstraction level.
region("registry", 6.34, 1.82, 2.15, 1.86,
       "Policy + certificate objects", BLUE, "#F7FAFD", "arch",
       dashed=True, size=16.0)
text("registry_ladder_title", 6.52, 2.13, 0.78, 0.14,
     "Frozen ladder", "registry", 14.0, True, INK)
for i, width in enumerate([0.42, 0.55, 0.68, 0.82]):
    cell(f"registry_level_{i}", 6.52, 2.36 + i * 0.19, width, 0.14,
         BLUE_FILL if i < 3 else TEAL_FILL,
         BLUE if i < 3 else TEAL, "registry", f"L{i}", 13.5,
         INK, True)
text("registry_cert_title", 7.48, 2.13, 0.75, 0.14,
     "Scoped certificate", "registry", 14.0, True, INK)
region("certificate_store", 7.47, 2.35, 0.80, 0.72, "", TEAL,
       TEAL_FILL, "registry", dashed=False, size=14.0)
for i, label in enumerate(["layout", "scope", "epoch"]):
    cell(f"certificate_field_{i}", 7.57, 2.43 + i * 0.19, 0.60, 0.15,
         "#FFFFFF", TEAL, "certificate_store", label, 13.5, INK, True)
text("registry_rule", 6.80, 3.23, 1.32, 0.18,
     "immutable + epoch-scoped", "registry", 15.0, False, INK)
connect("registry_calc", "registry_level_2:left", "calc_utility_2:right",
        BLUE, dashed=True, points=[[6.25, 2.84], [6.05, 2.84]], weight=1.0)

# Verifier: actual tensor operations, not token-id decoration.
region("verifier", 0.34, 3.84, 5.85, 1.39,
       "In-engine teacher-forced verifier", ORANGE, ORANGE_FILL,
       "arch", dashed=True, size=16.5)
text("verify_mask_title", 0.50, 4.13, 0.92, 0.14,
     "Idle-window mask", "verifier", 14.0, True, INK)
for i, fill in enumerate([
    GRAY_FILL, GRAY_FILL, ORANGE_FILL, ORANGE_FILL, ORANGE_FILL,
    GRAY_FILL, GRAY_FILL, ORANGE_FILL, ORANGE_FILL, GRAY_FILL,
]):
    cell(f"verify_mask_{i}", 0.50 + i * 0.087, 4.40, 0.087, 0.19,
         fill, ORANGE if fill == ORANGE_FILL else GRAY_LINE, "verifier")

text("verify_chunk_title", 1.53, 4.13, 1.02, 0.14,
     "32-token micro-chunks", "verifier", 14.0, True, INK)
tensor_stack("verify_chunks", 1.66, 4.42, 0.76, 0.31, 2, 8,
             [ORANGE_FILL, "#F9D5AC"], "verifier", layers=3,
             dx=0.055, dy=-0.045, line=ORANGE)

text("verify_lanes_title", 2.63, 4.13, 0.92, 0.14,
     "Idle-only lanes", "verifier", 14.0, True, INK)
matrix("verify_lanes", 2.66, 4.39, 0.88, 0.42, 2, 6,
       [GRAY_FILL, ORANGE_FILL], "verifier", ORANGE)

text("verify_path_title", 3.72, 4.13, 0.98, 0.14,
     "Teacher-forced paths", "verifier", 14.0, True, INK)
matrix("verify_candidate_path", 3.75, 4.37, 0.95, 0.19, 1, 5,
       ["#F7C58E"], "verifier", ORANGE)
matrix("verify_reference_path", 3.75, 4.65, 0.95, 0.19, 1, 5,
       ["#DCE2E8"], "verifier", GRAY_LINE)
matrix("verify_match_mask", 4.87, 4.46, 0.52, 0.29, 1, 5,
       [GREEN_FILL], "verifier", GREEN)
text("verify_match_label", 4.82, 4.76, 0.62, 0.18,
     "top-1 + stop", "verifier", 15.0, True, INK)
box("verify_pass", 5.48, 4.42, 0.56, 0.34, "PASS", GREEN,
    GREEN_FILL, "verifier", 14.0)
connect("verify_mask_chunks", "verify_mask_9:right", "verify_chunks_0:left",
        ORANGE, weight=1.8)
connect("verify_chunks_lanes", "verify_chunks_2:right", "verify_lanes:left",
        ORANGE, weight=1.8)
connect("verify_lanes_candidate", "verify_lanes:right",
        "verify_candidate_path:left", ORANGE, weight=1.8)
connect("verify_candidate_mask", "verify_candidate_path:right",
        "verify_match_mask:top", GREEN,
        points=[[4.78, 4.31], [5.13, 4.31]], weight=1.3)
connect("verify_paths_mask", "verify_reference_path:right",
        "verify_match_mask:left", GREEN, weight=1.8)
connect("verify_mask_pass", "verify_match_mask:right", "verify_pass:left",
        GREEN, weight=1.8)

# PSTP: only a verified, scope-valid private tensor becomes shared state.
region("pstp", 6.34, 3.84, 2.15, 1.39,
       "PSTP atomic promotion", TEAL, TEAL_FILL, "arch",
       dashed=True, size=16.0)
text("pstp_private_title", 6.49, 4.13, 0.72, 0.14,
     "Private KV", "pstp", 14.0, True, INK)
tensor_stack("pstp_private", 6.48, 4.44, 0.60, 0.28, 2, 6,
             [TEAL_FILL, "#D7EEEA"], "pstp", layers=3,
             dx=0.045, dy=-0.040, line=TEAL)
decision("pstp_gate", 7.18, 4.28, 0.56, 0.56,
         "path +\nscope?", TEAL, "pstp")
box("pstp_commit", 7.64, 4.27, 0.76, 0.26, "", TEAL,
    TEAL_FILL, "pstp", 13.5)
text("pstp_commit_label", 7.66, 4.31, 0.72, 0.16, "COMMIT", "pstp",
     13.5, True, INK)
tensor_stack("pstp_shared", 7.80, 4.72, 0.48, 0.24, 2, 6,
             [TEAL_FILL, "#CDEAE5"], "pstp", layers=2,
             dx=0.040, dy=-0.035, line=TEAL)
text("pstp_shared_title", 7.72, 4.98, 0.70, 0.18,
     "shared prefix", "pstp", 15.0, True, INK)
box("pstp_abort", 7.17, 4.95, 0.60, 0.22, "ABORT", RED,
    RED_FILL, "pstp", 13.5)
connect("pstp_private_gate", "pstp_private_2:right", "pstp_gate:left",
        TEAL, weight=1.9)
connect("pstp_gate_commit", "pstp_gate:right", "pstp_commit:left",
        TEAL, weight=1.9)
connect("pstp_commit_shared", "pstp_commit:bottom", "pstp_shared_1:top",
        TEAL, weight=1.8)
connect("pstp_gate_abort", "pstp_gate:bottom", "pstp_abort:top", RED,
        dashed=True, weight=1.0)
connect("verify_to_pstp", "verify_pass:right", "pstp_private_0:left", TEAL,
        weight=2.0)
connect("pstp_cert", "pstp_commit:right", "certificate_store:right", TEAL,
        dashed=True, points=[[8.39, 4.40], [8.39, 2.71]], weight=1.0)

# Existing serving system is deliberately subdued; only the cache interface remains.
region("runtime", 0.34, 5.41, 8.15, 1.60,
       "Existing serving engine (vLLM V1)", GRAY_LINE, "#F7F8FA",
       "arch", dashed=True, size=16.0)
text("runtime_request_title", 0.55, 5.71, 1.08, 0.14,
     "Certified request", "runtime", 14.0, True, INK)
token_vector("runtime_request", 0.56, 5.99, 0.21,
             [("SYS", 2), ("CODE", 4), ("OBS", 2), ("QUERY", 1)],
             "runtime", 0.052, 0.010)
box("runtime_lookup", 1.93, 5.88, 0.89, 0.42, "Certificate\nlookup",
    GRAY_LINE, "#FFFFFF", "runtime", 14.0)
box("runtime_api", 3.13, 5.88, 1.10, 0.42, "Prefix-cache\ninterface",
    GRAY_LINE, "#FFFFFF", "runtime", 14.0)
tensor_stack("runtime_cache", 4.55, 5.88, 1.08, 0.38, 2, 10,
             [TEAL_FILL, "#D6EDE9"], "runtime", layers=3,
             dx=0.055, dy=-0.045, line=TEAL)
text("runtime_cache_label", 4.52, 6.34, 1.22, 0.18,
     "shared physical prefix", "runtime", 15.0, True, INK)
box("runtime_decode", 6.08, 5.88, 0.82, 0.42, "Decode", GRAY_LINE,
    "#FFFFFF", "runtime", 14.0)
token_vector("runtime_output", 7.27, 5.99, 0.21,
             [("OUT", 7)], "runtime", 0.065, 0.010)
text("runtime_output_label", 7.25, 6.34, 0.92, 0.18,
     "output tokens", "runtime", 15.0, True, INK)
connect("runtime_request_lookup", "runtime_request_3_QUERY:right",
        "runtime_lookup:left", GRAY_LINE, weight=1.8)
connect("runtime_lookup_api", "runtime_lookup:right", "runtime_api:left",
        BLUE, weight=1.8)
connect("runtime_api_cache", "runtime_api:right", "runtime_cache_0:left",
        TEAL, weight=1.9)
connect("runtime_cache_decode", "runtime_cache_2:right", "runtime_decode:left",
        TEAL, weight=1.9)
connect("runtime_decode_output", "runtime_decode:right",
        "runtime_output_0_OUT:left", GRAY_LINE, weight=1.8)

# Explicit local ports replace long cross-module fence lines.
cell("cert_port_a", 6.48, 3.32, 0.26, 0.22, BLUE, BLUE, "registry",
     "A", 14.0, "#FFFFFF", True)
cell("runtime_port_a", 2.22, 5.52, 0.26, 0.22, BLUE, BLUE, "runtime",
     "A", 14.0, "#FFFFFF", True)
connect("runtime_cert_port", "runtime_port_a:bottom", "runtime_lookup:top",
        BLUE, dashed=True, weight=1.0)
node("commit_cache_out", "junction_point", 8.18, 5.20, 0.035, 0.035, "",
     "arch", role="boundary_anchor", style={"fill": TEAL, "line": TEAL})
node("commit_cache_in", "junction_point", 8.18, 5.40, 0.035, 0.035, "",
     "arch", role="boundary_anchor", style={"fill": TEAL, "line": TEAL})
connect("commit_cache_gap", "commit_cache_out", "commit_cache_in", TEAL,
        dashed=True, weight=1.1)
connect("pstp_cache_port", "pstp_shared_0:bottom", "commit_cache_out:top",
        TEAL, dashed=True, points=[[8.18, 5.08]], weight=1.0)
connect("cache_port_runtime", "commit_cache_in:bottom", "runtime_cache_2:top",
        TEAL, dashed=True, points=[[8.18, 5.61], [5.12, 5.61]], weight=1.0)
connect("ingress_calc", "ingress_tokens_0_SYS:bottom",
        "calc_contract_tensor:top", BLUE,
        points=[[1.52, 1.73], [1.19, 1.73]], weight=1.8)
connect("ingress_registry", "ingress_contract_2:bottom",
        "certificate_store:top", BLUE, dashed=True, weight=1.0)

# Panel (b): state evolution only. It does not redraw the control-plane modules.
stage_specs = [
    ("df1", 1.10, 0.86, "1  Private raw state", GRAY_LINE, GRAY_FILL),
    ("df2", 2.08, 0.98, "2  Private compiled layout", BLUE, BLUE_FILL),
    ("df3", 3.18, 1.10, "3  Shadow path verification", ORANGE, ORANGE_FILL),
    ("df4", 4.41, 1.24, "4  Atomic promotion", TEAL, TEAL_FILL),
    ("df5", 5.78, 1.20, "5  Later physical-prefix hit", TEAL, "#F3FAF7"),
]
for sid, y, h, label, color, fill in stage_specs:
    region(sid, 9.12, y, 4.70, h, label, color, fill, "flow",
           dashed=True, size=16.0)

# 1. Raw tokens are private, accompanied by a compact contract envelope.
token_vector("df_raw", 9.40, 1.48, 0.22,
             [("SYS", 3), ("OBS", 2), ("CODE", 5),
              ("DOC", 3), ("QUERY", 2)], "df1", 0.052, 0.012)
text("df_raw_labels", 9.40, 1.72, 1.72, 0.16,
     "SYS   OBS     CODE      DOC     QUERY", "df1",
     15.0, True, INK, 0)
tensor_stack("df_raw_kv", 11.44, 1.43, 0.84, 0.34, 2, 8,
             [GRAY_FILL, "#E7EBEF"], "df1", layers=3,
             dx=0.050, dy=-0.043, line=GRAY_LINE)
text("df_raw_kv_label", 11.46, 1.78, 0.89, 0.16,
     "private KV", "df1", 15.0, True, INK)
box("df_contract", 12.72, 1.40, 0.78, 0.38,
    "scope | budget\nepoch", BLUE, "#FFFFFF", "df1", 13.5)
connect("df_raw_to_kv", "df_raw_4_QUERY:right", "df_raw_kv_0:left",
        GRAY_LINE, weight=1.8)

# 2. A legal permutation matrix rewrites only the private layout.
token_vector("df_compile_in", 9.38, 2.50, 0.18,
             [("SYS", 2), ("OBS", 2), ("CODE", 3),
              ("DOC", 2), ("QUERY", 1)], "df2", 0.040, 0.008)
matrix("df_permutation", 10.58, 2.32, 0.62, 0.50, 5, 5,
       [BLUE_FILL] * 5, "df2", BLUE,
       shades=[0.00, 0.12, 0.00, 0.12, 0.00])
text("df_permutation_label", 10.52, 2.84, 0.74, 0.17,
     "legal reorder", "df2", 15.0, True, INK)
token_vector("df_compile_out", 11.47, 2.50, 0.20,
             [("SYS", 2), ("CODE", 3), ("DOC", 2),
              ("OBS", 2), ("QUERY", 1)], "df2", 0.043, 0.008)
block_vector("df_stable_mask", 12.67, 2.50, 6, 4, "df2", 0.12, 0.20,
             TEAL_FILL, TEAL)
text("df_stable_label", 12.61, 2.74, 0.86, 0.17,
     "stable-prefix mask", "df2", 15.0, True, INK)
connect("df_compile_perm", "df_compile_in_4_QUERY:right",
        "df_permutation:left", BLUE, weight=1.8)
connect("df_perm_out", "df_permutation:right", "df_compile_out_0_SYS:left",
        BLUE, weight=1.8)
connect("df_out_mask", "df_compile_out_4_QUERY:right",
        "df_stable_mask_0:left", TEAL, weight=1.8)

# 3. Candidate and raw paths produce an explicit equality mask.
text("df_candidate_label", 9.38, 3.55, 0.82, 0.13,
     "candidate path", "df3", 13.5, True, INK)
matrix("df_candidate_path", 9.39, 3.82, 1.12, 0.20, 1, 6,
       ["#F7C58E"], "df3", ORANGE)
text("df_reference_label", 10.74, 3.55, 0.82, 0.13,
     "raw reference", "df3", 13.5, True, INK)
matrix("df_reference_path", 10.74, 3.82, 1.12, 0.20, 1, 6,
       ["#DCE2E8"], "df3", GRAY_LINE)
matrix("df_equality_mask", 12.09, 3.69, 0.62, 0.34, 2, 6,
       [GREEN_FILL, GREEN_FILL], "df3", GREEN)
text("df_equality_label", 12.04, 4.04, 0.74, 0.17,
     "path + stop mask", "df3", 15.0, True, INK)
box("df_pass", 12.99, 3.77, 0.55, 0.33, "PASS", GREEN,
    GREEN_FILL, "df3", 14.0)
connect("df_candidate_mask", "df_candidate_path:right",
        "df_equality_mask:top", ORANGE,
        points=[[10.62, 3.68], [12.40, 3.68]], weight=1.3)
connect("df_reference_mask", "df_reference_path:right",
        "df_equality_mask:left", GREEN, weight=1.8)
connect("df_mask_pass", "df_equality_mask:right", "df_pass:left",
        GREEN, weight=1.8)

# 4. The success path reaches COMMIT; ABORT exits sideways and stops.
tensor_stack("df_private_kv", 9.38, 4.89, 0.76, 0.34, 2, 8,
             [TEAL_FILL, "#D7EEEA"], "df4", layers=3,
             dx=0.050, dy=-0.043, line=TEAL)
text("df_private_kv_label", 9.35, 5.27, 0.90, 0.16,
     "private KV tensor", "df4", 15.0, True, INK)
block_vector("df_boundary_mask", 10.47, 4.94, 6, 4, "df4",
             0.12, 0.20, TEAL_FILL, TEAL)
text("df_boundary_label", 10.41, 5.27, 0.86, 0.16,
     "stable boundary", "df4", 15.0, True, INK)
decision("df_gate", 11.46, 4.73, 0.60, 0.58,
         "path +\nscope?", TEAL, "df4")
box("df_commit", 12.08, 4.74, 0.86, 0.27, "", TEAL,
    TEAL_FILL, "df4", 13.5)
text("df_commit_label", 12.11, 4.79, 0.80, 0.16, "COMMIT", "df4",
     13.5, True, INK)
tensor_stack("df_shared_kv", 13.04, 4.83, 0.48, 0.29, 2, 6,
             [TEAL_FILL, "#CDEAE5"], "df4", layers=3,
             dx=0.040, dy=-0.036, line=TEAL)
text("df_shared_kv_label", 12.86, 5.27, 0.76, 0.16,
     "published prefix", "df4", 15.0, True, INK)
box("df_abort", 11.45, 5.36, 0.62, 0.22, "ABORT", RED,
    RED_FILL, "df4", 13.5)
connect("df_private_boundary", "df_private_kv_2:right",
        "df_boundary_mask_0:left", TEAL, weight=1.9)
connect("df_boundary_gate", "df_boundary_mask_5:right", "df_gate:left",
        TEAL, weight=1.9)
connect("df_gate_commit", "df_gate:right", "df_commit:left", TEAL,
        weight=1.9)
connect("df_commit_shared", "df_commit:right", "df_shared_kv_0:left", TEAL,
        weight=1.9)
connect("df_gate_abort", "df_gate:bottom", "df_abort:top", RED,
        dashed=True, weight=1.0)

# 5. A later suffix joins the already-published physical prefix.
token_vector("df_future_suffix", 9.39, 6.31, 0.22,
             [("OBS", 2), ("QUERY", 2)], "df5", 0.060, 0.010)
text("df_future_suffix_label", 9.35, 6.57, 0.76, 0.16,
     "new suffix", "df5", 15.0, True, INK)
tensor_stack("df_hit_prefix", 10.38, 6.25, 0.91, 0.34, 2, 9,
             [TEAL_FILL, "#D6EDE9"], "df5", layers=3,
             dx=0.048, dy=-0.041, line=TEAL)
text("df_hit_prefix_label", 10.34, 6.62, 1.02, 0.16,
     "physical prefix hit", "df5", 15.0, True, INK)
matrix("df_hit_mask", 11.64, 6.28, 0.55, 0.27, 1, 6,
       [GREEN_FILL], "df5", GREEN)
box("df_decode", 12.46, 6.22, 0.66, 0.38, "Decode", GRAY_LINE,
    "#FFFFFF", "df5", 14.0)
token_vector("df_output", 13.34, 6.31, 0.22,
             [("OUT", 6)], "df5", 0.060, 0.010)
connect("df_suffix_prefix", "df_future_suffix_1_QUERY:right",
        "df_hit_prefix_0:left", TEAL, weight=1.9)
connect("df_prefix_mask", "df_hit_prefix_2:right", "df_hit_mask:left",
        TEAL, weight=1.9)
connect("df_mask_decode", "df_hit_mask:right", "df_decode:left", TEAL,
        weight=1.9)
connect("df_decode_output", "df_decode:right", "df_output_0_OUT:left",
        GRAY_LINE, weight=1.8)

# Compact colored handoffs convey state progression without a visual spine.
short_stage_arrow("df_handoff_1", 13.62, 1.98, 2.07, BLUE, "flow")
short_stage_arrow("df_handoff_2", 13.62, 3.07, 3.16, ORANGE, "flow")
short_stage_arrow("df_handoff_3", 13.62, 4.30, 4.39, TEAL, "flow")
connect("df_published_to_hit", "df_shared_kv_2:bottom",
        "df_hit_prefix_2:top", TEAL,
        points=[[13.30, 5.69], [10.83, 5.69]], weight=1.9)

scene = {
    "version": "0.1",
    "metadata": {
        "title": "ContractKV tensor-centric architecture and execution-state dataflow",
        "created_by": "Codex with visiomaster",
        "style_profile": "paper_white",
        "fidelity": "semantic_redraw",
        "region_strategy": "region_first",
        "notes": [
            "Panel a uses a uniform data-structure abstraction for ContractKV components.",
            "Panel b shows state transformations and does not repeat component architecture.",
            "COMMIT is the only path to shared state; ABORT is a terminal side branch.",
            "All readable text labels use at least 14.5 pt in the 14.15-inch scene, approximately 7.3 pt at double-column scale.",
        ],
    },
    "page": {"width": 14.15, "height": 7.45,
             "origin": "top-left", "units": "in"},
    "canvas": {"width_in": 14.15, "height_in": 7.45,
               "background": "#FFFFFF"},
    "nodes": nodes,
    "edges": edges,
    "assets": [],
}

OUT.write_text(json.dumps(scene, indent=2), encoding="utf-8")
print(f"wrote {OUT} with {len(nodes)} nodes and {len(edges)} edges")
