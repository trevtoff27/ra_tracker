import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# Optional PDF export (ReportLab is available in your environment)
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

import matplotlib.pyplot as plt


# ============================================================
# Database (self-contained, JSON payload)
# ============================================================
DB_PATH = "tracker.db"


def db_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with db_connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts TEXT NOT NULL,
              time_of_day TEXT,
              payload TEXT NOT NULL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_entries_ts ON entries(ts)")
        con.commit()


def add_entry(payload: Dict[str, Any]) -> int:
    ts = payload.get("timestamp")
    tod = payload.get("time_of_day")
    with db_connect() as con:
        cur = con.execute(
            "INSERT INTO entries (ts, time_of_day, payload) VALUES (?, ?, ?)",
            (ts, tod, json.dumps(payload, ensure_ascii=False)),
        )
        con.commit()
        return int(cur.lastrowid)


def update_entry(entry_id: int, payload: Dict[str, Any]) -> None:
    ts = payload.get("timestamp")
    tod = payload.get("time_of_day")
    with db_connect() as con:
        con.execute(
            "UPDATE entries SET ts=?, time_of_day=?, payload=? WHERE id=?",
            (ts, tod, json.dumps(payload, ensure_ascii=False), entry_id),
        )
        con.commit()


def list_entries(limit: int = 500) -> List[Dict[str, Any]]:
    with db_connect() as con:
        rows = con.execute(
            "SELECT id, ts, time_of_day, payload FROM entries ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        try:
            payload = json.loads(r["payload"])
        except Exception:
            payload = {}
        payload["_id"] = int(r["id"])
        payload["_ts"] = r["ts"]
        payload["_time_of_day"] = r["time_of_day"]
        out.append(payload)
    return out


# ============================================================
# Rheumatology: 28-joint set + standard indices
# ============================================================
JOINTS_28 = [
    # Shoulders
    ("L_shoulder", "Left shoulder"),
    ("R_shoulder", "Right shoulder"),
    # Elbows
    ("L_elbow", "Left elbow"),
    ("R_elbow", "Right elbow"),
    # Wrists
    ("L_wrist", "Left wrist"),
    ("R_wrist", "Right wrist"),
    # MCP 1-5 each side
    ("L_mcp1", "Left MCP1 (thumb knuckle)"),
    ("L_mcp2", "Left MCP2"),
    ("L_mcp3", "Left MCP3"),
    ("L_mcp4", "Left MCP4"),
    ("L_mcp5", "Left MCP5"),
    ("R_mcp1", "Right MCP1 (thumb knuckle)"),
    ("R_mcp2", "Right MCP2"),
    ("R_mcp3", "Right MCP3"),
    ("R_mcp4", "Right MCP4"),
    ("R_mcp5", "Right MCP5"),
    # PIP 1-5 each side
    ("L_pip1", "Left PIP1 (thumb IP)"),
    ("L_pip2", "Left PIP2"),
    ("L_pip3", "Left PIP3"),
    ("L_pip4", "Left PIP4"),
    ("L_pip5", "Left PIP5"),
    ("R_pip1", "Right PIP1 (thumb IP)"),
    ("R_pip2", "Right PIP2"),
    ("R_pip3", "Right PIP3"),
    ("R_pip4", "Right PIP4"),
    ("R_pip5", "Right PIP5"),
    # Knees
    ("L_knee", "Left knee"),
    ("R_knee", "Right knee"),
]

STIFFNESS_BUCKETS = {
    0: "0–15 min",
    1: "15–30 min",
    2: "30–60 min",
    3: "60–120 min",
    4: ">120 min",
}

TIME_OF_DAY_OPTIONS = ["Morning", "Midday", "Evening", "Night", "Custom"]

SCALE_0_3 = {
    0: "None",
    1: "Mild",
    2: "Moderate",
    3: "Severe",
}


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def parse_optional_float(raw: str, field: str, errors: List[str]) -> Optional[float]:
    value = (raw or "").strip()
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        errors.append(f"{field} must be a number or blank.")
        return None


def default_time_of_day() -> str:
    hour = datetime.now().hour
    if hour < 11:
        return "Morning"
    if hour < 16:
        return "Midday"
    if hour < 21:
        return "Evening"
    return "Night"


def tjc_sjc_28(joint_map: Dict[str, Dict[str, bool]]) -> Tuple[int, int]:
    tjc = 0
    sjc = 0
    for k, _label in JOINTS_28:
        v = joint_map.get(k, {}) or {}
        if v.get("tender"):
            tjc += 1
        if v.get("swollen"):
            sjc += 1
    return tjc, sjc


def das28_esr(tjc: int, sjc: int, esr: float, gh_0_100: float) -> Optional[float]:
    # DAS28(ESR)=0.56*sqrt(TJC28)+0.28*sqrt(SJC28)+0.70*ln(ESR)+0.014*GH
    if esr is None or esr <= 0:
        return None
    return (
        0.56 * math.sqrt(tjc)
        + 0.28 * math.sqrt(sjc)
        + 0.70 * math.log(esr)
        + 0.014 * gh_0_100
    )


def das28_crp(tjc: int, sjc: int, crp_mg_l: float, gh_0_100: float) -> Optional[float]:
    # DAS28(CRP)=0.56*sqrt(TJC28)+0.28*sqrt(SJC28)+0.36*ln(CRP+1)+0.014*GH+0.96
    if crp_mg_l is None or crp_mg_l < 0:
        return None
    return (
        0.56 * math.sqrt(tjc)
        + 0.28 * math.sqrt(sjc)
        + 0.36 * math.log(crp_mg_l + 1.0)
        + 0.014 * gh_0_100
        + 0.96
    )


def categorize_das28(x: Optional[float]) -> str:
    if x is None:
        return "-"
    if x < 2.6:
        return "Remission"
    if x < 3.2:
        return "Low"
    if x <= 5.1:
        return "Moderate"
    return "High"


def cdai(tjc: int, sjc: int, ptga_0_10: float, phga_0_10: Optional[float]) -> Optional[float]:
    # CDAI = TJC28 + SJC28 + PtGA + PhGA
    if phga_0_10 is None:
        return None
    return float(tjc + sjc) + float(ptga_0_10) + float(phga_0_10)


def sdai(
    tjc: int,
    sjc: int,
    ptga_0_10: float,
    phga_0_10: Optional[float],
    crp_mg_l: Optional[float],
) -> Optional[float]:
    # SDAI = TJC28 + SJC28 + PtGA + PhGA + CRP (mg/dL)
    if phga_0_10 is None or crp_mg_l is None:
        return None
    crp_mg_dl = crp_mg_l / 10.0  # convert mg/L to mg/dL
    return float(tjc + sjc) + float(ptga_0_10) + float(phga_0_10) + float(crp_mg_dl)


def categorize_cdai(x: Optional[float]) -> str:
    if x is None:
        return "-"
    if x <= 2.8:
        return "Remission"
    if x <= 10:
        return "Low"
    if x <= 22:
        return "Moderate"
    return "High"


def categorize_sdai(x: Optional[float]) -> str:
    if x is None:
        return "-"
    if x <= 3.3:
        return "Remission"
    if x <= 11:
        return "Low"
    if x <= 26:
        return "Moderate"
    return "High"


# RAPID3: function (0–10) + pain (0–10) + patient global (0–10) = 0–30
MDHAQ_FUNCTION_ITEMS = [
    "Dress yourself (including tying shoelaces / buttons)",
    "Get in and out of bed",
    "Lift a full cup or glass to your mouth",
    "Walk outdoors on flat ground",
    "Wash and dry your body",
    "Bend down to pick up clothing from the floor",
    "Turn faucets on and off",
    "Get in and out of a car",
    "Walk 2 km (about 1.25 miles)",
    "Participate in recreational activities you enjoy",
]


def rapid3_function_score_0_10(function_items_0_3: List[int]) -> float:
    # 10 items each 0-3 => total 0-30; convert to 0-10 by (sum/30)*10
    total = sum(int(clamp(x, 0, 3)) for x in function_items_0_3)
    return (total / 30.0) * 10.0


def rapid3_total(function_0_10: float, pain_0_10: float, ptga_0_10: float) -> float:
    return float(function_0_10) + float(pain_0_10) + float(ptga_0_10)


def categorize_rapid3(x: Optional[float]) -> str:
    if x is None:
        return "-"
    # Remission ≤3, Low 3.1–6, Moderate 6.1–12, High >12
    if x <= 3.0:
        return "Remission"
    if x <= 6.0:
        return "Low"
    if x <= 12.0:
        return "Moderate"
    return "High"


# ============================================================
# Thyroid module: clinician-friendly (labs + symptoms + adherence)
# ============================================================
THYROID_UNDER = [
    ("cold_intolerance", "Cold intolerance"),
    ("constipation", "Constipation"),
    ("brain_fog", "Brain fog / slow thinking"),
    ("dry_skin", "Dry skin"),
    ("weight_gain", "Unintentional weight gain"),
    ("hair_shedding", "Hair shedding"),
]

THYROID_OVER = [
    ("palpitations", "Palpitations / racing heart"),
    ("tremor", "Tremor / shaky hands"),
    ("heat_intolerance", "Heat intolerance"),
    ("sweating", "Sweating"),
    ("insomnia", "Insomnia / trouble sleeping"),
    ("diarrhea", "Diarrhea"),
    ("anxiety", "Anxiety / restlessness"),
]


def thyroid_flags(symptoms: Dict[str, Any], meds: Dict[str, Any], labs: Dict[str, Any]) -> Dict[str, Any]:
    # Under-replacement suspicion: >=2 moderate+ under symptoms OR high TSH OR low FT4 OR missed doses
    under_count = 0
    for k, _lbl in THYROID_UNDER:
        under_count += int(int(symptoms.get(f"{k}_0_3", 0)) >= 2)

    over_count = 0
    for k, _lbl in THYROID_OVER:
        over_count += int(int(symptoms.get(f"{k}_0_3", 0)) >= 2)

    tsh = labs.get("TSH")
    ft4 = labs.get("FreeT4")

    tsh_high = tsh is not None and tsh > 4
    tsh_low = tsh is not None and tsh < 0.4
    ft4_low = ft4 is not None and ft4 < 0.8
    ft4_high = ft4 is not None and ft4 > 1.8

    missed = not meds.get("levothyroxine_taken_yes", True)
    timing = meds.get("levothyroxine_taken_correctly_yes", True)

    return {
        "possible_under_replacement": bool(under_count >= 2 or tsh_high or ft4_low or missed),
        "possible_over_replacement": bool(over_count >= 2 or tsh_low or ft4_high),
        "under_count_modplus": under_count,
        "over_count_modplus": over_count,
        "tsh_high": bool(tsh_high),
        "tsh_low": bool(tsh_low),
        "ft4_low": bool(ft4_low),
        "ft4_high": bool(ft4_high),
        "missed_dose_flag": bool(missed),
        "timing_flag_ok": bool(timing),
    }


# ============================================================
# Analysis wrapper
# ============================================================
def analyze_entry(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    s = payload.get("symptoms", {}) or {}
    labs = payload.get("labs", {}) or {}
    meds = payload.get("meds", {}) or {}
    joint_map = s.get("joint_map_28", {}) or {}

    alerts: List[str] = []
    if int(s.get("palpitations_0_3", 0)) >= 3:
        alerts.append(
            "Severe palpitations: seek urgent assessment if chest pain, fainting, severe shortness of breath, or persistent rapid heartbeat."
        )

    tjc, sjc = tjc_sjc_28(joint_map)

    ptga_0_10 = float(clamp(float(s.get("ptga_0_10", 0)), 0, 10))
    gh_0_100 = ptga_0_10 * 10.0

    esr = labs.get("ESR")
    crp = labs.get("CRP")

    das_esr = das28_esr(tjc, sjc, esr, gh_0_100) if esr is not None else None
    das_crp = das28_crp(tjc, sjc, crp, gh_0_100) if crp is not None else None

    # CDAI/SDAI need physician global
    phga = s.get("phga_0_10")
    phga_0_10 = None if phga in (None, "", "null") else float(clamp(float(phga), 0, 10))

    cdai_val = cdai(tjc, sjc, ptga_0_10, phga_0_10)
    sdai_val = sdai(tjc, sjc, ptga_0_10, phga_0_10, crp)

    # RAPID3
    func_items = s.get("mdhaq_function_items_0_3", []) or []
    if isinstance(func_items, list) and len(func_items) == 10:
        func_0_10 = rapid3_function_score_0_10([int(x) for x in func_items])
        pain_0_10 = float(clamp(float(s.get("pain_0_10", 0)), 0, 10))
        rapid3_val = rapid3_total(func_0_10, pain_0_10, ptga_0_10)
    else:
        func_0_10 = None
        rapid3_val = None

    thyroid = thyroid_flags(s, meds, labs)

    return (
        {
            "tjc28": tjc,
            "sjc28": sjc,
            "ptga_0_10": ptga_0_10,
            "phga_0_10": phga_0_10,
            "das28_esr": None if das_esr is None else round(das_esr, 2),
            "das28_crp": None if das_crp is None else round(das_crp, 2),
            "das28_esr_category": categorize_das28(das_esr),
            "das28_crp_category": categorize_das28(das_crp),
            "cdai": None if cdai_val is None else round(cdai_val, 1),
            "cdai_category": categorize_cdai(cdai_val),
            "sdai": None if sdai_val is None else round(sdai_val, 1),
            "sdai_category": categorize_sdai(sdai_val),
            "rapid3_function_0_10": None if func_0_10 is None else round(func_0_10, 1),
            "rapid3": None if rapid3_val is None else round(rapid3_val, 1),
            "rapid3_category": categorize_rapid3(rapid3_val),
            "thyroid_flags": thyroid,
        },
        alerts,
    )


# ============================================================
# PDF Export
# ============================================================
def make_trend_plot(df: pd.DataFrame, ycol: str, title: str, out_png: str) -> bool:
    if df.empty or ycol not in df.columns:
        return False
    d = df.dropna(subset=["ts", ycol]).copy()
    if d.empty:
        return False
    d = d.sort_values("ts")
    plt.figure()
    plt.plot(d["ts"], d[ycol])
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel(ycol)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    plt.close()
    return True


def export_doctor_report_pdf(
    patient_name: str,
    date_from: date,
    date_to: date,
    df: pd.DataFrame,
    latest_payload: Dict[str, Any],
) -> bytes:
    """
    Creates a simple 1–3 page PDF:
    - Latest snapshot (indices, joint counts, stiffness, key labs)
    - Trends charts (DAS28, CDAI/SDAI if available, RAPID3)
    - Thyroid summary (TSH/FT4 + flags)
    """
    import tempfile
    from io import BytesIO

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    def draw_header(y: float) -> float:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(0.75 * inch, y, "Doctor Visit Report (RA + Thyroid)")
        y -= 0.25 * inch
        c.setFont("Helvetica", 10)
        c.drawString(0.75 * inch, y, f"Patient: {patient_name or '-'}")
        c.drawString(3.75 * inch, y, f"Range: {date_from.isoformat()} to {date_to.isoformat()}")
        y -= 0.25 * inch
        c.line(0.75 * inch, y, width - 0.75 * inch, y)
        return y - 0.25 * inch

    def draw_kv(y: float, label: str, value: str) -> float:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(0.75 * inch, y, label)
        c.setFont("Helvetica", 9)
        c.drawString(2.6 * inch, y, value)
        return y - 0.18 * inch

    # Page 1: Latest snapshot
    y = height - 0.85 * inch
    y = draw_header(y)

    analysis = (latest_payload.get("analysis") or {}).get("analysis", {}) or {}
    symptoms = latest_payload.get("symptoms", {}) or {}
    labs = latest_payload.get("labs", {}) or {}
    meds = latest_payload.get("meds", {}) or {}

    c.setFont("Helvetica-Bold", 11)
    c.drawString(0.75 * inch, y, "Latest Snapshot")
    y -= 0.25 * inch

    # Core indices
    y = draw_kv(y, "TJC28 / SJC28", f"{analysis.get('tjc28','-')} / {analysis.get('sjc28','-')}")
    y = draw_kv(y, "PtGA (0–10)", str(analysis.get("ptga_0_10", "-")))
    y = draw_kv(y, "PhGA (0–10)", str(analysis.get("phga_0_10", "-")))
    y = draw_kv(y, "DAS28-ESR", f"{analysis.get('das28_esr','-')} ({analysis.get('das28_esr_category','-')})")
    y = draw_kv(y, "DAS28-CRP", f"{analysis.get('das28_crp','-')} ({analysis.get('das28_crp_category','-')})")
    y = draw_kv(y, "CDAI", f"{analysis.get('cdai','-')} ({analysis.get('cdai_category','-')})")
    y = draw_kv(y, "SDAI", f"{analysis.get('sdai','-')} ({analysis.get('sdai_category','-')})")
    y = draw_kv(y, "RAPID3", f"{analysis.get('rapid3','-')} ({analysis.get('rapid3_category','-')})")

    y -= 0.1 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(0.75 * inch, y, "Key Patient-Reported Context")
    y -= 0.25 * inch
    y = draw_kv(y, "Morning stiffness", STIFFNESS_BUCKETS.get(int(symptoms.get("morning_stiffness_duration_cat", 0)), "-"))
    y = draw_kv(y, "Gelling after rest (0–3)", str(symptoms.get("rest_stiffness_gelling_0_3", "-")))
    y = draw_kv(y, "Pain (0–10)", str(symptoms.get("pain_0_10", "-")))

    y -= 0.1 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(0.75 * inch, y, "Key Labs (if provided)")
    y -= 0.25 * inch
    y = draw_kv(y, "CRP (mg/L)", str(labs.get("CRP", "-")))
    y = draw_kv(y, "ESR (mm/hr)", str(labs.get("ESR", "-")))
    y = draw_kv(y, "TSH", str(labs.get("TSH", "-")))
    y = draw_kv(y, "Free T4", str(labs.get("FreeT4", "-")))

    y -= 0.1 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(0.75 * inch, y, "Thyroid / Levothyroxine Summary")
    y -= 0.25 * inch
    tf = analysis.get("thyroid_flags", {}) or {}
    y = draw_kv(y, "Possible under-replacement", str(tf.get("possible_under_replacement", "-")))
    y = draw_kv(y, "Possible over-replacement", str(tf.get("possible_over_replacement", "-")))
    y = draw_kv(y, "Levothyroxine taken", "Yes" if meds.get("levothyroxine_taken_yes", True) else "No")
    y = draw_kv(y, "Taken correctly", "Yes" if meds.get("levothyroxine_taken_correctly_yes", True) else "No")

    notes = latest_payload.get("notes")
    if notes:
        y -= 0.05 * inch
        c.setFont("Helvetica-Bold", 9)
        c.drawString(0.75 * inch, y, "Notes:")
        y -= 0.18 * inch
        c.setFont("Helvetica", 9)
        # basic wrap
        line = ""
        for word in str(notes).split():
            if len(line) + len(word) + 1 > 95:
                c.drawString(0.75 * inch, y, line)
                y -= 0.16 * inch
                line = word
            else:
                line = (line + " " + word).strip()
        if line:
            c.drawString(0.75 * inch, y, line)

    c.showPage()

    # Page 2+: trends (embed charts)
    with tempfile.TemporaryDirectory() as td:
        y = height - 0.85 * inch
        y = draw_header(y)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(0.75 * inch, y, "Trends")
        y -= 0.25 * inch

        # Create up to 4 plots
        plot_specs = [
            ("das28_esr", "DAS28-ESR Trend"),
            ("das28_crp", "DAS28-CRP Trend"),
            ("rapid3", "RAPID3 Trend"),
            ("tsh", "TSH Trend"),
        ]

        # Ensure columns exist
        for col in ["das28_esr", "das28_crp", "rapid3", "tsh", "ts"]:
            if col not in df.columns:
                df[col] = None

        pngs: List[str] = []
        for col, title in plot_specs:
            path = f"{td}/{col}.png"
            if make_trend_plot(df, col, title, path):
                pngs.append(path)

        # Layout images
        x0 = 0.75 * inch
        max_w = width - 1.5 * inch
        img_h = 2.25 * inch
        for p in pngs:
            if y - img_h < 1.0 * inch:
                c.showPage()
                y = height - 0.85 * inch
                y = draw_header(y)
                c.setFont("Helvetica-Bold", 11)
                c.drawString(0.75 * inch, y, "Trends (cont.)")
                y -= 0.25 * inch
            c.drawImage(p, x0, y - img_h, width=max_w, height=img_h, preserveAspectRatio=True, anchor='sw')
            y -= (img_h + 0.3 * inch)

    c.save()
    buffer.seek(0)
    return buffer.read()


# ============================================================
# Streamlit App
# ============================================================
st.set_page_config(page_title="RA Clinic Tracker", page_icon="🩺", layout="wide")
init_db()

st.title("🩺 RA Clinic Tracker (DAS28 / CDAI / SDAI / RAPID3)")
st.caption("Tracking tool only. Not medical advice. Patient-reported joint counts are helpful, but clinician exam remains the reference standard.")

mode = st.sidebar.selectbox("Mode", ["Patient Entry", "Clinician Summary"])

# ----------------------------
# PATIENT ENTRY
# ----------------------------
if mode == "Patient Entry":
    with st.form("patient_entry_form", clear_on_submit=False):
        st.subheader("Entry Timing")
        ts = st.datetime_input("Date & time", value=datetime.now())
        tod = st.selectbox(
            "Time of day",
            TIME_OF_DAY_OPTIONS,
            index=TIME_OF_DAY_OPTIONS.index(default_time_of_day()),
        )
        custom_tod = st.text_input(
            "Custom time-of-day label",
            placeholder="e.g., after lunch, post-work",
            disabled=(tod != "Custom"),
        )

        st.divider()
        st.subheader("Patient Global + Core Symptoms")
        ptga_0_10 = st.slider("Patient global assessment (PtGA) (0–10)", 0.0, 10.0, 4.0, 0.1)
        pain_0_10 = st.slider("Pain (0–10)", 0.0, 10.0, 4.0, 0.1)

        morning_stiffness_duration_cat = st.select_slider(
            "Morning stiffness duration",
            options=list(STIFFNESS_BUCKETS.keys()),
            value=2,
            format_func=lambda x: STIFFNESS_BUCKETS[x],
        )
        rest_stiffness_gelling_0_3 = st.slider("Stiff after sitting/resting (gelling) (0–3)", 0, 3, 0)

        st.divider()
        st.subheader("28-Joint Count (patient-reported)")
        st.caption("Mark each joint as tender and/or swollen today. This enables TJC28/SJC28 for DAS28/CDAI/SDAI.")
        joint_map_28: Dict[str, Dict[str, bool]] = {}

        left_col, right_col = st.columns(2)
        for i, (key, label) in enumerate(JOINTS_28):
            col = left_col if i % 2 == 0 else right_col
            with col:
                st.markdown(f"**{label}**")
                t = st.toggle("Tender", key=f"{key}_t", value=False)
                s = st.toggle("Swollen", key=f"{key}_s", value=False)
                joint_map_28[key] = {"tender": bool(t), "swollen": bool(s)}
                st.caption(" ")

        st.divider()
        st.subheader("RAPID3 Function (MDHAQ-style)")
        st.caption("For each item: 0=no difficulty, 1=some, 2=much, 3=unable to do.")
        function_items: List[int] = []
        for idx, item in enumerate(MDHAQ_FUNCTION_ITEMS):
            val = st.slider(item, 0, 3, 0, key=f"fn_{idx}")
            function_items.append(int(val))

        st.divider()
        st.subheader("Thyroid / Levothyroxine (clinician-friendly)")
        st.caption("Tracks thyroid-relevant symptoms + adherence + labs for interpretation.")
        lt1, lt2 = st.columns(2)
        with lt1:
            levothyroxine_taken_yes = st.toggle("Took levothyroxine (today/last scheduled dose)", value=True)
        with lt2:
            levothyroxine_taken_correctly_yes = st.toggle("Taken correctly (empty stomach, away from iron/calcium)", value=True)

        st.markdown("**Possible under-replacement symptoms (0–3):**")
        render_cols = st.columns(3)
        for idx, (k, lbl) in enumerate(THYROID_UNDER):
            with render_cols[idx % 3]:
                v = st.slider(lbl, 0, 3, 0, key=f"thy_under_{k}")
                # store in symptoms dict later via key mapping

        st.markdown("**Possible over-replacement symptoms (0–3):**")
        render_cols2 = st.columns(3)
        for idx, (k, lbl) in enumerate(THYROID_OVER):
            with render_cols2[idx % 3]:
                v = st.slider(lbl, 0, 3, 0, key=f"thy_over_{k}")

        st.divider()
        st.subheader("Labs (optional, but needed for DAS28 and SDAI)")
        include_labs = st.toggle("Add lab results", value=False)
        labs_raw: Dict[str, str] = {}
        if include_labs:
            c1, c2, c3 = st.columns(3)
            with c1:
                labs_raw["CRP"] = st.text_input("CRP (mg/L)")
                labs_raw["ESR"] = st.text_input("ESR (mm/hr)")
            with c2:
                labs_raw["TSH"] = st.text_input("TSH")
                labs_raw["FreeT4"] = st.text_input("Free T4")
            with c3:
                labs_raw["RF"] = st.text_input("Rheumatoid Factor (optional)")
                labs_raw["AntiCCP"] = st.text_input("Anti-CCP (optional)")

        st.divider()
        notes = st.text_area("Notes (optional)", placeholder="Triggers, infection exposure, unusual stress, etc.")
        submitted = st.form_submit_button("Review Entry")

    if submitted:
        errors: List[str] = []
        labs: Dict[str, Optional[float]] = {}
        if include_labs:
            for field, raw in labs_raw.items():
                labs[field] = parse_optional_float(raw, field, errors)

        if errors:
            for e in errors:
                st.error(e)
        else:
            resolved_tod = tod
            if tod == "Custom":
                custom_clean = (custom_tod or "").strip()
                resolved_tod = custom_clean if custom_clean else "Custom"

            # Build thyroid symptoms from widget state
            symptoms_thy: Dict[str, int] = {}
            for k, _lbl in THYROID_UNDER:
                symptoms_thy[f"{k}_0_3"] = int(st.session_state.get(f"thy_under_{k}", 0))
            for k, _lbl in THYROID_OVER:
                symptoms_thy[f"{k}_0_3"] = int(st.session_state.get(f"thy_over_{k}", 0))

            payload: Dict[str, Any] = {
                "timestamp": ts.isoformat(timespec="seconds"),
                "time_of_day": resolved_tod,
                "symptoms": {
                    "ptga_0_10": float(ptga_0_10),
                    "pain_0_10": float(pain_0_10),
                    "morning_stiffness_duration_cat": int(morning_stiffness_duration_cat),
                    "rest_stiffness_gelling_0_3": int(rest_stiffness_gelling_0_3),
                    "joint_map_28": joint_map_28,
                    "mdhaq_function_items_0_3": function_items,
                    # physician global is clinician-entered later
                    "phga_0_10": None,
                    **symptoms_thy,
                },
                "meds": {
                    "levothyroxine_taken_yes": bool(levothyroxine_taken_yes),
                    "levothyroxine_taken_correctly_yes": bool(levothyroxine_taken_correctly_yes),
                },
                "labs": labs if include_labs else {},
                "notes": (notes or "").strip() or None,
                "analysis": {},
            }

            analysis, alerts = analyze_entry(payload)
            payload["analysis"] = {"analysis": analysis, "alerts": alerts}

            st.session_state["pending_payload"] = payload
            st.info("Review below, then Confirm & Save.")

    pending = st.session_state.get("pending_payload")
    if pending:
        st.divider()
        st.subheader("Review Entry")
        a = pending["analysis"]["analysis"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("TJC28", a.get("tjc28", "-"))
        c2.metric("SJC28", a.get("sjc28", "-"))
        c3.metric("DAS28-ESR", f"{a.get('das28_esr','-')} ({a.get('das28_esr_category','-')})")
        c4.metric("RAPID3", f"{a.get('rapid3','-')} ({a.get('rapid3_category','-')})")

        st.write(
            {
                "DAS28-CRP": f"{a.get('das28_crp','-')} ({a.get('das28_crp_category','-')})",
                "CDAI (needs PhGA)": f"{a.get('cdai','-')} ({a.get('cdai_category','-')})",
                "SDAI (needs PhGA + CRP)": f"{a.get('sdai','-')} ({a.get('sdai_category','-')})",
            }
        )

        alerts = pending["analysis"].get("alerts", []) or []
        if alerts:
            st.warning("Safety alerts")
            for al in alerts:
                st.write(f"- {al}")

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("Confirm & Save", type="primary"):
                entry_id = add_entry(pending)
                st.session_state["last_saved_id"] = entry_id
                st.session_state.pop("pending_payload", None)
                st.success(f"Saved entry (id={entry_id}).")
        with b2:
            if st.button("Edit"):
                st.session_state.pop("pending_payload", None)
                st.info("Draft cleared. Edit and Review again.")
        with b3:
            if st.button("Discard"):
                st.session_state.pop("pending_payload", None)
                st.warning("Draft discarded.")


# ----------------------------
# CLINICIAN SUMMARY
# ----------------------------
else:
    entries = list_entries()
    if not entries:
        st.info("No entries yet.")
        st.stop()

    st.subheader("Clinician Summary Mode")
    st.caption("Industry-aligned outputs: DAS28, CDAI, SDAI, RAPID3. Add PhGA here to complete CDAI/SDAI.")

    # Build dataframe for trends
    rows: List[Dict[str, Any]] = []
    for p in entries:
        a = (p.get("analysis") or {}).get("analysis", {}) or {}
        labs = p.get("labs", {}) or {}
        rows.append(
            {
                "id": p.get("_id"),
                "ts": pd.to_datetime(p.get("_ts") or p.get("timestamp"), errors="coerce"),
                "time_of_day": p.get("_time_of_day") or p.get("time_of_day"),
                "tjc28": a.get("tjc28"),
                "sjc28": a.get("sjc28"),
                "ptga": a.get("ptga_0_10"),
                "phga": a.get("phga_0_10"),
                "das28_esr": a.get("das28_esr"),
                "das28_crp": a.get("das28_crp"),
                "cdai": a.get("cdai"),
                "sdai": a.get("sdai"),
                "rapid3": a.get("rapid3"),
                "rapid3_cat": a.get("rapid3_category"),
                "tsh": labs.get("TSH"),
                "freet4": labs.get("FreeT4"),
                "notes": p.get("notes") or "",
            }
        )

    df = pd.DataFrame(rows).dropna(subset=["ts"]).sort_values("ts")
    st.dataframe(df.sort_values("ts", ascending=False), width="stretch", hide_index=True)

    st.divider()
    st.subheader("Trend Visualization")
    metric = st.selectbox("Metric", ["das28_esr", "das28_crp", "cdai", "sdai", "rapid3", "tsh", "freet4"])
    series_df = df[["ts", metric]].dropna().set_index("ts")
    if series_df.empty:
        st.info("No data available for that metric yet.")
    else:
        st.line_chart(series_df)

    st.divider()
    st.subheader("Add / Update PhGA (Physician Global 0–10) for a Selected Entry")
    entry_options = [(f"{r['ts'].date()} (id={int(r['id'])})", int(r["id"])) for _, r in df.sort_values("ts", ascending=False).iterrows()]
    sel_label, sel_id = st.selectbox("Select entry", entry_options, format_func=lambda x: x[0])

    selected_payload = next((p for p in entries if int(p.get("_id")) == int(sel_id)), None)
    if not selected_payload:
        st.error("Entry not found.")
        st.stop()

    current_phga = selected_payload.get("symptoms", {}).get("phga_0_10", None)
    phga_new = st.slider("PhGA (0–10)", 0.0, 10.0, float(current_phga or 0.0), 0.1)

    if st.button("Save PhGA to Entry"):
        selected_payload["symptoms"]["phga_0_10"] = float(phga_new)
        analysis, alerts = analyze_entry(selected_payload)
        selected_payload["analysis"] = {"analysis": analysis, "alerts": alerts}
        update_entry(int(sel_id), selected_payload)
        st.success("Updated entry with PhGA and recalculated indices. Refresh page if needed.")

    st.divider()
    st.subheader("Printable Doctor Visit Report (PDF)")
    patient_name = st.text_input("Patient name (optional)", value="")
    colA, colB = st.columns(2)
    with colA:
        d_from = st.date_input("From", value=df["ts"].min().date() if not df.empty else date.today())
    with colB:
        d_to = st.date_input("To", value=df["ts"].max().date() if not df.empty else date.today())

    # Filter df for report
    mask = (df["ts"].dt.date >= d_from) & (df["ts"].dt.date <= d_to)
    df_r = df.loc[mask].copy()
    if df_r.empty:
        st.info("No entries in that date range.")
    else:
        latest_id = int(df_r.sort_values("ts").iloc[-1]["id"])
        latest_payload = next((p for p in entries if int(p.get("_id")) == latest_id), entries[0])

        if st.button("Generate PDF Report"):
            pdf_bytes = export_doctor_report_pdf(
                patient_name=patient_name,
                date_from=d_from,
                date_to=d_to,
                df=df_r.assign(ts=df_r["ts"].dt.date.astype(str)),
                latest_payload=latest_payload,
            )
            st.download_button(
                "Download Doctor Visit Report (PDF)",
                data=pdf_bytes,
                file_name=f"doctor_visit_report_{d_from.isoformat()}_{d_to.isoformat()}.pdf",
                mime="application/pdf",
            )

    st.divider()
    st.caption(
        "Note: CDAI/SDAI require PhGA. In real clinics, TJC/SJC come from clinician exam; patient-reported counts can still be useful between visits."
    )