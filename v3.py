import json
import math
import sqlite3
from datetime import datetime, date
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

# ============================================================
# CONFIG
# ============================================================
DB_PATH = "tracker.db"
APP_TITLE = "RA Clinic Tracker"
POINTS_PER_COMPLETED_ENTRY = 10
BRONZE_THRESHOLD = 100
SILVER_THRESHOLD = 300
GOLD_THRESHOLD = 600

TIME_OF_DAY_OPTIONS = ["Morning", "Midday", "Evening", "Night", "Custom"]

STIFFNESS_BUCKETS = {
    0: "0–15 min",
    1: "15–30 min",
    2: "30–60 min",
    3: "60–120 min",
    4: ">120 min",
}

MDHAQ_FUNCTION_ITEMS = [
    "Dress yourself (including buttons / shoelaces)",
    "Get in and out of bed",
    "Lift a full cup or glass to your mouth",
    "Walk outdoors on flat ground",
    "Wash and dry your body",
    "Bend down to pick clothing up from the floor",
    "Turn faucets on and off",
    "Get in and out of a car",
    "Walk 2 km (about 1.25 miles)",
    "Take part in activities you enjoy",
]

JOINTS_28 = [
    ("L_shoulder", "Left shoulder"),
    ("R_shoulder", "Right shoulder"),
    ("L_elbow", "Left elbow"),
    ("R_elbow", "Right elbow"),
    ("L_wrist", "Left wrist"),
    ("R_wrist", "Right wrist"),
    ("L_mcp1", "Left MCP1"),
    ("L_mcp2", "Left MCP2"),
    ("L_mcp3", "Left MCP3"),
    ("L_mcp4", "Left MCP4"),
    ("L_mcp5", "Left MCP5"),
    ("R_mcp1", "Right MCP1"),
    ("R_mcp2", "Right MCP2"),
    ("R_mcp3", "Right MCP3"),
    ("R_mcp4", "Right MCP4"),
    ("R_mcp5", "Right MCP5"),
    ("L_pip1", "Left PIP1 / thumb IP"),
    ("L_pip2", "Left PIP2"),
    ("L_pip3", "Left PIP3"),
    ("L_pip4", "Left PIP4"),
    ("L_pip5", "Left PIP5"),
    ("R_pip1", "Right PIP1 / thumb IP"),
    ("R_pip2", "Right PIP2"),
    ("R_pip3", "Right PIP3"),
    ("R_pip4", "Right PIP4"),
    ("R_pip5", "Right PIP5"),
    ("L_knee", "Left knee"),
    ("R_knee", "Right knee"),
]

THYROID_UNDER_FIELDS = [
    ("cold_intolerance", "Cold intolerance"),
    ("constipation", "Constipation"),
    ("brain_fog", "Brain fog / slow thinking"),
    ("dry_skin", "Dry skin"),
    ("weight_gain", "Unintentional weight gain"),
    ("hair_shedding", "Hair shedding"),
]

THYROID_OVER_FIELDS = [
    ("palpitations", "Palpitations / racing heart"),
    ("tremor", "Tremor / shaky hands"),
    ("heat_intolerance", "Heat intolerance"),
    ("sweating", "Sweating"),
    ("insomnia", "Trouble sleeping"),
    ("diarrhea", "Diarrhea"),
    ("anxiety", "Anxiety / restlessness"),
]

HCQ_FIELDS = [
    ("nausea", "Nausea / upset stomach"),
    ("abdominal_pain", "Stomach pain / cramps"),
    ("diarrhea", "Diarrhea"),
    ("headache", "Headache"),
    ("dizziness", "Dizziness / vertigo"),
    ("rash", "Rash / itching"),
    ("tinnitus", "Ringing in the ears / hearing changes"),
    ("sleep_vivid_dreams", "Sleep disturbance / vivid dreams"),
    ("visual_blur", "Blurred vision / focusing problems"),
    ("visual_flashes", "Flashes / halos / unusual visual changes"),
    ("mood_change", "New mood / behavior change"),
    ("palpitations", "Palpitations / fast heartbeat"),
]


# ============================================================
# UI STYLING
# ============================================================
def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2rem;
            max-width: 980px;
        }
        .reward-card {
            border-radius: 18px;
            padding: 16px 18px;
            margin-bottom: 14px;
            background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: 0 8px 24px rgba(0,0,0,0.18);
        }
        .reward-chip {
            display: inline-block;
            padding: 6px 10px;
            border-radius: 999px;
            margin-right: 8px;
            font-size: 0.85rem;
            font-weight: 600;
            border: 1px solid rgba(255,255,255,0.16);
        }
        .bronze { background: #7c4a1d; color: #fff; }
        .silver { background: #5b6572; color: #fff; }
        .gold { background: #8a6a09; color: #fff; }
        .section-note {
            font-size: 0.92rem;
            opacity: 0.86;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# DB
# ============================================================
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
    with db_connect() as con:
        cur = con.execute(
            "INSERT INTO entries (ts, time_of_day, payload) VALUES (?, ?, ?)",
            (
                payload.get("timestamp"),
                payload.get("time_of_day"),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def update_entry(entry_id: int, payload: Dict[str, Any]) -> None:
    with db_connect() as con:
        con.execute(
            "UPDATE entries SET ts=?, time_of_day=?, payload=? WHERE id=?",
            (
                payload.get("timestamp"),
                payload.get("time_of_day"),
                json.dumps(payload, ensure_ascii=False),
                entry_id,
            ),
        )
        con.commit()


def list_entries(limit: int = 500) -> List[Dict[str, Any]]:
    with db_connect() as con:
        rows = con.execute(
            "SELECT id, ts, time_of_day, payload FROM entries ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except Exception:
            payload = {}
        payload["_id"] = int(row["id"])
        payload["_ts"] = row["ts"]
        payload["_time_of_day"] = row["time_of_day"]
        out.append(payload)
    return out


# ============================================================
# HELPERS
# ============================================================
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


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def render_scale_hint() -> None:
    st.caption("0 = none, 1 = mild, 2 = moderate, 3 = severe.")


def tjc_sjc_28(joint_map: Dict[str, Dict[str, bool]]) -> Tuple[int, int]:
    tjc = 0
    sjc = 0
    for key, _label in JOINTS_28:
        val = joint_map.get(key, {}) or {}
        if val.get("tender"):
            tjc += 1
        if val.get("swollen"):
            sjc += 1
    return tjc, sjc


# ============================================================
# VALIDATED RA MEASURES
# ============================================================
def das28_esr(tjc: int, sjc: int, esr: Optional[float], gh_0_100: float) -> Optional[float]:
    if esr is None or esr <= 0:
        return None
    return (
        0.56 * math.sqrt(tjc)
        + 0.28 * math.sqrt(sjc)
        + 0.70 * math.log(esr)
        + 0.014 * gh_0_100
    )


def das28_crp(tjc: int, sjc: int, crp_mg_l: Optional[float], gh_0_100: float) -> Optional[float]:
    if crp_mg_l is None or crp_mg_l < 0:
        return None
    return (
        0.56 * math.sqrt(tjc)
        + 0.28 * math.sqrt(sjc)
        + 0.36 * math.log(crp_mg_l + 1.0)
        + 0.014 * gh_0_100
        + 0.96
    )


def cdai(tjc: int, sjc: int, ptga_0_10: float, phga_0_10: Optional[float]) -> Optional[float]:
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
    if phga_0_10 is None or crp_mg_l is None:
        return None
    crp_mg_dl = crp_mg_l / 10.0
    return float(tjc + sjc) + float(ptga_0_10) + float(phga_0_10) + float(crp_mg_dl)


def rapid3_function_score_0_10(function_items_0_3: List[int]) -> float:
    total = sum(int(clamp(float(x), 0, 3)) for x in function_items_0_3)
    return (total / 30.0) * 10.0


def rapid3_total(function_0_10: float, pain_0_10: float, ptga_0_10: float) -> float:
    return float(function_0_10) + float(pain_0_10) + float(ptga_0_10)


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


def categorize_rapid3(x: Optional[float]) -> str:
    if x is None:
        return "-"
    if x <= 3.0:
        return "Remission"
    if x <= 6.0:
        return "Low"
    if x <= 12.0:
        return "Moderate"
    return "High"


# ============================================================
# THYROID / LEVOTHYROXINE
# ============================================================
def thyroid_flags(symptoms: Dict[str, Any], meds: Dict[str, Any], labs: Dict[str, Any]) -> Dict[str, Any]:
    under_count = 0
    for key, _label in THYROID_UNDER_FIELDS:
        under_count += int(int(symptoms.get(f"{key}_0_3", 0)) >= 2)

    over_count = 0
    for key, _label in THYROID_OVER_FIELDS:
        over_count += int(int(symptoms.get(f"{key}_0_3", 0)) >= 2)

    tsh = labs.get("TSH")
    ft4 = labs.get("FreeT4")

    tsh_high = tsh is not None and tsh > 4
    tsh_low = tsh is not None and tsh < 0.4
    ft4_low = ft4 is not None and ft4 < 0.8
    ft4_high = ft4 is not None and ft4 > 1.8

    missed = not meds.get("levothyroxine_taken_yes", True)
    timing_ok = meds.get("levothyroxine_taken_correctly_yes", True)

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
        "timing_ok": bool(timing_ok),
    }


# ============================================================
# HYDROXYCHLOROQUINE MODULE
# ============================================================
def hcq_flags(symptoms: Dict[str, Any], meds: Dict[str, Any]) -> Dict[str, Any]:
    visual_flag = (
        int(symptoms.get("hcq_visual_blur_0_3", 0)) >= 2
        or int(symptoms.get("hcq_visual_flashes_0_3", 0)) >= 1
    )
    cardiac_flag = int(symptoms.get("hcq_palpitations_0_3", 0)) >= 2
    rash_flag = int(symptoms.get("hcq_rash_0_3", 0)) >= 2
    mood_flag = int(symptoms.get("hcq_mood_change_0_3", 0)) >= 2
    tinnitus_flag = int(symptoms.get("hcq_tinnitus_0_3", 0)) >= 2

    gi_count = 0
    for key in ["hcq_nausea_0_3", "hcq_abdominal_pain_0_3", "hcq_diarrhea_0_3"]:
        gi_count += int(int(symptoms.get(key, 0)) >= 2)

    return {
        "taking_hcq": bool(meds.get("hydroxychloroquine_taken_yes", True)),
        "missed_doses_7d": meds.get("hydroxychloroquine_missed_doses_7d", "0"),
        "recent_start_6w": bool(meds.get("hydroxychloroquine_started_recently_yes", False)),
        "gi_side_effect_cluster": gi_count >= 2,
        "visual_flag": bool(visual_flag),
        "cardiac_flag": bool(cardiac_flag),
        "rash_flag": bool(rash_flag),
        "mood_flag": bool(mood_flag),
        "tinnitus_flag": bool(tinnitus_flag),
    }


# ============================================================
# REWARDS
# ============================================================
def total_points(entries: List[Dict[str, Any]]) -> int:
    return len(entries) * POINTS_PER_COMPLETED_ENTRY


def reward_tier(points: int) -> str:
    if points >= GOLD_THRESHOLD:
        return "Gold"
    if points >= SILVER_THRESHOLD:
        return "Silver"
    if points >= BRONZE_THRESHOLD:
        return "Bronze"
    return "Starter"


def next_tier_info(points: int) -> Tuple[str, int]:
    if points < BRONZE_THRESHOLD:
        return "Bronze", BRONZE_THRESHOLD - points
    if points < SILVER_THRESHOLD:
        return "Silver", SILVER_THRESHOLD - points
    if points < GOLD_THRESHOLD:
        return "Gold", GOLD_THRESHOLD - points
    return "Gold", 0


# ============================================================
# ANALYSIS
# ============================================================
def analyze_entry(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    symptoms = payload.get("symptoms", {}) or {}
    labs = payload.get("labs", {}) or {}
    meds = payload.get("meds", {}) or {}

    alerts: List[str] = []

    joint_map = symptoms.get("joint_map_28", {}) or {}
    tjc, sjc = tjc_sjc_28(joint_map)

    ptga_0_10 = float(clamp(float(symptoms.get("ptga_0_10", 0)), 0, 10))
    gh_0_100 = ptga_0_10 * 10.0
    phga_raw = symptoms.get("phga_0_10")
    phga_0_10 = None if phga_raw in (None, "", "null") else float(clamp(float(phga_raw), 0, 10))

    esr = labs.get("ESR")
    crp = labs.get("CRP")

    das_esr = das28_esr(tjc, sjc, esr, gh_0_100)
    das_crp = das28_crp(tjc, sjc, crp, gh_0_100)

    cdai_val = cdai(tjc, sjc, ptga_0_10, phga_0_10)
    sdai_val = sdai(tjc, sjc, ptga_0_10, phga_0_10, crp)

    function_items = symptoms.get("mdhaq_function_items_0_3", []) or []
    rapid3_func = None
    rapid3_val = None
    if isinstance(function_items, list) and len(function_items) == 10:
        rapid3_func = rapid3_function_score_0_10([int(x) for x in function_items])
        rapid3_val = rapid3_total(
            function_0_10=rapid3_func,
            pain_0_10=float(symptoms.get("pain_0_10", 0)),
            ptga_0_10=ptga_0_10,
        )

    thyroid = thyroid_flags(symptoms, meds, labs)
    hcq = hcq_flags(symptoms, meds)

    if thyroid["possible_over_replacement"] and int(symptoms.get("palpitations_0_3", 0)) >= 3:
        alerts.append("Severe palpitations with possible thyroid over-replacement pattern: urgent assessment is appropriate if persistent, with chest pain, fainting, or shortness of breath.")

    if hcq["visual_flag"]:
        alerts.append("Hydroxychloroquine visual symptoms flagged: prompt clinician / eye review is appropriate.")
    if hcq["cardiac_flag"]:
        alerts.append("Hydroxychloroquine cardiac symptom flag: palpitations or fast heartbeat should be reviewed promptly.")
    if hcq["mood_flag"]:
        alerts.append("Hydroxychloroquine mood / behavior change flagged: contact prescribing clinician promptly.")
    if hcq["rash_flag"]:
        alerts.append("Hydroxychloroquine rash / itching flagged: review severity and contact clinician if worsening.")

    return {
        "tjc28": tjc,
        "sjc28": sjc,
        "ptga_0_10": round(ptga_0_10, 1),
        "phga_0_10": None if phga_0_10 is None else round(phga_0_10, 1),
        "das28_esr": None if das_esr is None else round(das_esr, 2),
        "das28_crp": None if das_crp is None else round(das_crp, 2),
        "das28_esr_category": categorize_das28(das_esr),
        "das28_crp_category": categorize_das28(das_crp),
        "cdai": None if cdai_val is None else round(cdai_val, 1),
        "cdai_category": categorize_cdai(cdai_val),
        "sdai": None if sdai_val is None else round(sdai_val, 1),
        "sdai_category": categorize_sdai(sdai_val),
        "rapid3_function_0_10": None if rapid3_func is None else round(rapid3_func, 1),
        "rapid3": None if rapid3_val is None else round(rapid3_val, 1),
        "rapid3_category": categorize_rapid3(rapid3_val),
        "thyroid_flags": thyroid,
        "hcq_flags": hcq,
    }, alerts


# ============================================================
# PDF EXPORT
# ============================================================
def make_trend_plot(df: pd.DataFrame, ycol: str, title: str, out_png: str) -> bool:
    if df.empty or ycol not in df.columns:
        return False
    plot_df = df.dropna(subset=["ts", ycol]).copy()
    if plot_df.empty:
        return False

    plt.figure(figsize=(7, 3))
    plt.plot(plot_df["ts"], plot_df[ycol], marker="o")
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
    import tempfile

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    def header(y: float) -> float:
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(0.7 * inch, y, "Doctor Visit Report")
        y -= 0.2 * inch
        pdf.setFont("Helvetica", 10)
        pdf.drawString(0.7 * inch, y, f"Patient: {patient_name or '-'}")
        pdf.drawString(3.9 * inch, y, f"Range: {date_from.isoformat()} to {date_to.isoformat()}")
        y -= 0.18 * inch
        pdf.line(0.7 * inch, y, width - 0.7 * inch, y)
        return y - 0.2 * inch

    def kv(y: float, label: str, value: str) -> float:
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(0.7 * inch, y, label)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(2.6 * inch, y, value)
        return y - 0.16 * inch

    analysis = (latest_payload.get("analysis") or {}).get("analysis", {}) or {}
    symptoms = latest_payload.get("symptoms", {}) or {}
    labs = latest_payload.get("labs", {}) or {}
    meds = latest_payload.get("meds", {}) or {}

    y = height - 0.8 * inch
    y = header(y)

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(0.7 * inch, y, "Latest Rheumatology Snapshot")
    y -= 0.22 * inch

    y = kv(y, "TJC28 / SJC28", f"{analysis.get('tjc28','-')} / {analysis.get('sjc28','-')}")
    y = kv(y, "Patient Global (0–10)", str(analysis.get("ptga_0_10", "-")))
    y = kv(y, "Physician Global (0–10)", str(analysis.get("phga_0_10", "-")))
    y = kv(y, "DAS28-ESR", f"{analysis.get('das28_esr','-')} ({analysis.get('das28_esr_category','-')})")
    y = kv(y, "DAS28-CRP", f"{analysis.get('das28_crp','-')} ({analysis.get('das28_crp_category','-')})")
    y = kv(y, "CDAI", f"{analysis.get('cdai','-')} ({analysis.get('cdai_category','-')})")
    y = kv(y, "SDAI", f"{analysis.get('sdai','-')} ({analysis.get('sdai_category','-')})")
    y = kv(y, "RAPID3", f"{analysis.get('rapid3','-')} ({analysis.get('rapid3_category','-')})")
    y = kv(y, "Morning stiffness", STIFFNESS_BUCKETS.get(int(symptoms.get("morning_stiffness_duration_cat", 0)), "-"))

    y -= 0.08 * inch
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(0.7 * inch, y, "Labs")
    y -= 0.22 * inch

    y = kv(y, "CRP (mg/L)", str(labs.get("CRP", "-")))
    y = kv(y, "ESR (mm/hr)", str(labs.get("ESR", "-")))
    y = kv(y, "TSH", str(labs.get("TSH", "-")))
    y = kv(y, "Free T4", str(labs.get("FreeT4", "-")))

    y -= 0.08 * inch
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(0.7 * inch, y, "Medication Summary")
    y -= 0.22 * inch

    hcq = analysis.get("hcq_flags", {}) or {}
    thyroid = analysis.get("thyroid_flags", {}) or {}

    y = kv(y, "Hydroxychloroquine taking", "Yes" if meds.get("hydroxychloroquine_taken_yes", True) else "No")
    y = kv(y, "Hydroxychloroquine missed doses (7d)", str(meds.get("hydroxychloroquine_missed_doses_7d", "-")))
    y = kv(y, "Hydroxychloroquine recent start", "Yes" if meds.get("hydroxychloroquine_started_recently_yes", False) else "No")
    y = kv(y, "HCQ visual flag", str(hcq.get("visual_flag", "-")))
    y = kv(y, "HCQ cardiac flag", str(hcq.get("cardiac_flag", "-")))
    y = kv(y, "Possible thyroid under-replacement", str(thyroid.get("possible_under_replacement", "-")))
    y = kv(y, "Possible thyroid over-replacement", str(thyroid.get("possible_over_replacement", "-")))

    notes = latest_payload.get("notes")
    if notes:
        y -= 0.06 * inch
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(0.7 * inch, y, "Notes")
        y -= 0.18 * inch
        pdf.setFont("Helvetica", 9)
        line = ""
        for word in str(notes).split():
            if len(line) + len(word) + 1 > 100:
                pdf.drawString(0.7 * inch, y, line)
                y -= 0.15 * inch
                line = word
            else:
                line = (line + " " + word).strip()
        if line:
            pdf.drawString(0.7 * inch, y, line)

    pdf.showPage()

    with tempfile.TemporaryDirectory() as td:
        y = height - 0.8 * inch
        y = header(y)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(0.7 * inch, y, "Trend Charts")
        y -= 0.28 * inch

        plot_specs = [
            ("das28_esr", "DAS28-ESR Trend"),
            ("das28_crp", "DAS28-CRP Trend"),
            ("rapid3", "RAPID3 Trend"),
            ("tsh", "TSH Trend"),
        ]

        pngs: List[str] = []
        for col, title in plot_specs:
            png_path = f"{td}/{col}.png"
            if make_trend_plot(df, col, title, png_path):
                pngs.append(png_path)

        for png in pngs:
            if y < 3.0 * inch:
                pdf.showPage()
                y = height - 0.8 * inch
                y = header(y)
                pdf.setFont("Helvetica-Bold", 11)
                pdf.drawString(0.7 * inch, y, "Trend Charts (cont.)")
                y -= 0.28 * inch

            pdf.drawImage(png, 0.7 * inch, y - 2.4 * inch, width=7.0 * inch, height=2.2 * inch)
            y -= 2.5 * inch

    pdf.save()
    buffer.seek(0)
    return buffer.read()


# ============================================================
# APP
# ============================================================
st.set_page_config(page_title=APP_TITLE, page_icon="🩺", layout="centered")
inject_css()
init_db()

entries = list_entries()
points = total_points(entries)
tier = reward_tier(points)
next_tier, points_to_next = next_tier_info(points)

st.title(f"🩺 {APP_TITLE}")
st.caption("Validated clinician-facing RA indices + patient-friendly tracking + rewards.")

st.markdown(
    f"""
    <div class="reward-card">
        <div style="font-size:1.05rem;font-weight:700;margin-bottom:8px;">Daily streak rewards</div>
        <div style="margin-bottom:10px;" class="section-note">Earn points each time a daily assessment is completed.</div>
        <span class="reward-chip bronze">Bronze: {BRONZE_THRESHOLD}+ pts</span>
        <span class="reward-chip silver">Silver: {SILVER_THRESHOLD}+ pts</span>
        <span class="reward-chip gold">Gold: {GOLD_THRESHOLD}+ pts</span>
        <div style="margin-top:12px;font-size:1rem;">
            Current points: <strong>{points}</strong> · Tier: <strong>{tier}</strong>
        </div>
        <div class="section-note" style="margin-top:6px;">
            {"You have reached the top tier." if points_to_next == 0 else f"{points_to_next} points to {next_tier}."}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

mode = st.sidebar.selectbox("Mode", ["Patient Entry", "Clinician Summary"])

if mode == "Patient Entry":
    with st.form("daily_entry_form", clear_on_submit=False):
        st.subheader("Entry timing")
        ts = st.datetime_input("Date & time", value=datetime.now())
        tod = st.selectbox("Time of day", TIME_OF_DAY_OPTIONS, index=TIME_OF_DAY_OPTIONS.index(default_time_of_day()))
        custom_tod = st.text_input("Custom label", placeholder="e.g. after lunch", disabled=(tod != "Custom"))

        st.divider()
        st.subheader("RA disease activity")
        ptga_0_10 = st.slider("Patient global assessment (0–10)", 0.0, 10.0, 4.0, 0.1)
        pain_0_10 = st.slider("Pain (0–10)", 0.0, 10.0, 4.0, 0.1)
        morning_stiffness_duration_cat = st.select_slider(
            "Morning stiffness duration",
            options=list(STIFFNESS_BUCKETS.keys()),
            value=2,
            format_func=lambda x: STIFFNESS_BUCKETS[x],
        )
        rest_stiffness_gelling_0_3 = st.slider("Stiff after sitting/resting", 0, 3, 0)

        st.markdown("**28-joint count**")
        st.caption("Mark each joint as tender and/or swollen today.")
        joint_map_28: Dict[str, Dict[str, bool]] = {}
        col1, col2 = st.columns(2)
        for i, (key, label) in enumerate(JOINTS_28):
            col = col1 if i % 2 == 0 else col2
            with col:
                st.markdown(f"**{label}**")
                tender = st.toggle("Tender", value=False, key=f"{key}_t")
                swollen = st.toggle("Swollen", value=False, key=f"{key}_s")
                joint_map_28[key] = {"tender": bool(tender), "swollen": bool(swollen)}

        st.divider()
        st.subheader("RAPID3 function")
        st.caption("0=no difficulty, 1=some, 2=much, 3=unable")
        function_items: List[int] = []
        for idx, item in enumerate(MDHAQ_FUNCTION_ITEMS):
            function_items.append(st.slider(item, 0, 3, 0, key=f"fn_{idx}"))

        st.divider()
        st.subheader("Hydroxychloroquine")
        st.caption("Use this to separate disease activity from possible hydroxychloroquine tolerability issues.")
        hcq_col1, hcq_col2 = st.columns(2)
        with hcq_col1:
            hydroxychloroquine_taken_yes = st.toggle("Took hydroxychloroquine", value=True)
            hydroxychloroquine_started_recently_yes = st.toggle("Started in last 6 weeks", value=True)
        with hcq_col2:
            hydroxychloroquine_missed_doses_7d = st.selectbox("Missed doses in last 7 days", ["0", "1", "2+"])

        render_scale_hint()
        hcq_ui_cols = st.columns(3)
        hcq_values: Dict[str, int] = {}
        for idx, (key, label) in enumerate(HCQ_FIELDS):
            with hcq_ui_cols[idx % 3]:
                hcq_values[f"hcq_{key}_0_3"] = st.slider(label, 0, 3, 0, key=f"hcq_{key}")

        st.divider()
        st.subheader("Thyroid / levothyroxine")
        thyroid_col1, thyroid_col2 = st.columns(2)
        with thyroid_col1:
            levothyroxine_taken_yes = st.toggle("Took levothyroxine", value=True)
        with thyroid_col2:
            levothyroxine_taken_correctly_yes = st.toggle("Taken correctly", value=True)

        render_scale_hint()
        st.markdown("**Possible under-replacement symptoms**")
        under_cols = st.columns(3)
        thyroid_vals: Dict[str, int] = {}
        for idx, (key, label) in enumerate(THYROID_UNDER_FIELDS):
            with under_cols[idx % 3]:
                thyroid_vals[f"{key}_0_3"] = st.slider(label, 0, 3, 0, key=f"thy_under_{key}")

        st.markdown("**Possible over-replacement symptoms**")
        over_cols = st.columns(3)
        for idx, (key, label) in enumerate(THYROID_OVER_FIELDS):
            with over_cols[idx % 3]:
                thyroid_vals[f"{key}_0_3"] = st.slider(label, 0, 3, 0, key=f"thy_over_{key}")

        st.divider()
        st.subheader("Labs")
        include_labs = st.toggle("Add lab results", value=False)
        labs_raw: Dict[str, str] = {}
        if include_labs:
            l1, l2, l3 = st.columns(3)
            with l1:
                labs_raw["CRP"] = st.text_input("CRP (mg/L)")
                labs_raw["ESR"] = st.text_input("ESR (mm/hr)")
            with l2:
                labs_raw["TSH"] = st.text_input("TSH")
                labs_raw["FreeT4"] = st.text_input("Free T4")
            with l3:
                labs_raw["RF"] = st.text_input("Rheumatoid factor (optional)")
                labs_raw["AntiCCP"] = st.text_input("Anti-CCP (optional)")

        notes = st.text_area("Notes", placeholder="Triggers, stress, infection exposure, menstrual context, etc.")
        submitted = st.form_submit_button("Review entry")

    if submitted:
        errors: List[str] = []
        labs: Dict[str, Optional[float]] = {}
        if include_labs:
            for field, raw in labs_raw.items():
                labs[field] = parse_optional_float(raw, field, errors)

        if errors:
            for err in errors:
                st.error(err)
        else:
            resolved_tod = tod
            if tod == "Custom":
                resolved_tod = (custom_tod or "").strip() or "Custom"

            payload = {
                "timestamp": ts.isoformat(timespec="seconds"),
                "time_of_day": resolved_tod,
                "symptoms": {
                    "ptga_0_10": float(ptga_0_10),
                    "pain_0_10": float(pain_0_10),
                    "morning_stiffness_duration_cat": int(morning_stiffness_duration_cat),
                    "rest_stiffness_gelling_0_3": int(rest_stiffness_gelling_0_3),
                    "joint_map_28": joint_map_28,
                    "mdhaq_function_items_0_3": function_items,
                    "phga_0_10": None,
                    **hcq_values,
                    **thyroid_vals,
                },
                "meds": {
                    "hydroxychloroquine_taken_yes": bool(hydroxychloroquine_taken_yes),
                    "hydroxychloroquine_started_recently_yes": bool(hydroxychloroquine_started_recently_yes),
                    "hydroxychloroquine_missed_doses_7d": hydroxychloroquine_missed_doses_7d,
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
            st.success("Review ready below.")

    pending_payload = st.session_state.get("pending_payload")
    if pending_payload:
        st.divider()
        st.subheader("Review before save")

        analysis = pending_payload["analysis"]["analysis"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("TJC28", analysis.get("tjc28", "-"))
        metric_cols[1].metric("SJC28", analysis.get("sjc28", "-"))
        metric_cols[2].metric("DAS28-ESR", f"{analysis.get('das28_esr','-')}")
        metric_cols[3].metric("RAPID3", f"{analysis.get('rapid3','-')}")

        st.write(
            {
                "DAS28-ESR category": analysis.get("das28_esr_category", "-"),
                "DAS28-CRP": f"{analysis.get('das28_crp','-')} ({analysis.get('das28_crp_category','-')})",
                "CDAI": f"{analysis.get('cdai','-')} ({analysis.get('cdai_category','-')})",
                "SDAI": f"{analysis.get('sdai','-')} ({analysis.get('sdai_category','-')})",
            }
        )

        alerts = pending_payload["analysis"].get("alerts", []) or []
        if alerts:
            st.warning("Flags")
            for alert in alerts:
                st.write(f"- {alert}")

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("Confirm & save", type="primary"):
                entry_id = add_entry(pending_payload)
                st.session_state["last_saved_id"] = entry_id
                st.session_state.pop("pending_payload", None)
                st.success(f"Saved entry. You earned {POINTS_PER_COMPLETED_ENTRY} points.")
                st.rerun()
        with b2:
            if st.button("Edit answers"):
                st.session_state.pop("pending_payload", None)
                st.info("Draft cleared.")
        with b3:
            if st.button("Discard draft"):
                st.session_state.pop("pending_payload", None)
                st.warning("Draft discarded.")

else:
    if not entries:
        st.info("No entries yet.")
        st.stop()

    st.subheader("Clinician summary mode")
    st.caption("Clinician-facing view with validated RA indices, thyroid trends, hydroxychloroquine flags, and printable reporting.")

    rows: List[Dict[str, Any]] = []
    for payload in entries:
        analysis = (payload.get("analysis") or {}).get("analysis", {}) or {}
        labs = payload.get("labs", {}) or {}
        meds = payload.get("meds", {}) or {}
        rows.append(
            {
                "id": payload.get("_id"),
                "ts": pd.to_datetime(payload.get("_ts") or payload.get("timestamp"), errors="coerce"),
                "time_of_day": payload.get("_time_of_day") or payload.get("time_of_day"),
                "tjc28": analysis.get("tjc28"),
                "sjc28": analysis.get("sjc28"),
                "ptga": analysis.get("ptga_0_10"),
                "phga": analysis.get("phga_0_10"),
                "das28_esr": analysis.get("das28_esr"),
                "das28_crp": analysis.get("das28_crp"),
                "cdai": analysis.get("cdai"),
                "sdai": analysis.get("sdai"),
                "rapid3": analysis.get("rapid3"),
                "tsh": labs.get("TSH"),
                "freet4": labs.get("FreeT4"),
                "hcq_taking": meds.get("hydroxychloroquine_taken_yes"),
                "notes": payload.get("notes") or "",
            }
        )

    df = pd.DataFrame(rows).dropna(subset=["ts"]).sort_values("ts")
    st.dataframe(df.sort_values("ts", ascending=False), width="stretch", hide_index=True)

    st.divider()
    st.subheader("Trend visualization")
    metric = st.selectbox("Metric", ["das28_esr", "das28_crp", "cdai", "sdai", "rapid3", "tsh", "freet4"])
    trend_df = df[["ts", metric]].dropna().set_index("ts")
    if trend_df.empty:
        st.info("No data available for that metric.")
    else:
        st.line_chart(trend_df)

    st.divider()
    st.subheader("Add / update physician global (PhGA)")
    entry_options = [
        (f"{row['ts'].date()} · id={int(row['id'])}", int(row["id"]))
        for _, row in df.sort_values("ts", ascending=False).iterrows()
    ]
    selected = st.selectbox("Select entry", entry_options, format_func=lambda x: x[0])
    selected_id = int(selected[1])

    selected_payload = next((p for p in entries if int(p.get("_id")) == selected_id), None)
    if selected_payload:
        current_phga = selected_payload.get("symptoms", {}).get("phga_0_10")
        phga_new = st.slider("Physician global assessment (0–10)", 0.0, 10.0, float(current_phga or 0.0), 0.1)
        if st.button("Save PhGA to selected entry"):
            selected_payload["symptoms"]["phga_0_10"] = float(phga_new)
            analysis, alerts = analyze_entry(selected_payload)
            selected_payload["analysis"] = {"analysis": analysis, "alerts": alerts}
            update_entry(selected_id, selected_payload)
            st.success("Entry updated and clinician indices recalculated.")
            st.rerun()

    st.divider()
    st.subheader("Printable doctor visit report")
    patient_name = st.text_input("Patient name", value="")
    c1, c2 = st.columns(2)
    with c1:
        d_from = st.date_input("From", value=df["ts"].min().date() if not df.empty else date.today())
    with c2:
        d_to = st.date_input("To", value=df["ts"].max().date() if not df.empty else date.today())

    mask = (df["ts"].dt.date >= d_from) & (df["ts"].dt.date <= d_to)
    report_df = df.loc[mask].copy()

    if report_df.empty:
        st.info("No entries in that date range.")
    else:
        latest_id = int(report_df.sort_values("ts").iloc[-1]["id"])
        latest_payload = next((p for p in entries if int(p.get("_id")) == latest_id), entries[0])

        st.markdown("**Clinician summary preview**")
        latest_analysis = (latest_payload.get("analysis") or {}).get("analysis", {}) or {}
        latest_labs = latest_payload.get("labs", {}) or {}

        st.write(
            {
                "Date": str(report_df.sort_values("ts").iloc[-1]["ts"].date()),
                "Morning stiffness": STIFFNESS_BUCKETS.get(
                    int(latest_payload.get("symptoms", {}).get("morning_stiffness_duration_cat", 0)),
                    "-",
                ),
                "TJC28": latest_analysis.get("tjc28"),
                "SJC28": latest_analysis.get("sjc28"),
                "Patient Global": latest_analysis.get("ptga_0_10"),
                "CRP": latest_labs.get("CRP"),
                "ESR": latest_labs.get("ESR"),
                "DAS28-ESR": f"{latest_analysis.get('das28_esr','-')} → {latest_analysis.get('das28_esr_category','-')}",
                "DAS28-CRP": f"{latest_analysis.get('das28_crp','-')} → {latest_analysis.get('das28_crp_category','-')}",
                "CDAI": f"{latest_analysis.get('cdai','-')} → {latest_analysis.get('cdai_category','-')}",
                "SDAI": f"{latest_analysis.get('sdai','-')} → {latest_analysis.get('sdai_category','-')}",
                "RAPID3": f"{latest_analysis.get('rapid3','-')} → {latest_analysis.get('rapid3_category','-')}",
            }
        )

        if st.button("Generate PDF report"):
            pdf_bytes = export_doctor_report_pdf(
                patient_name=patient_name,
                date_from=d_from,
                date_to=d_to,
                df=report_df.assign(ts=report_df["ts"].dt.date.astype(str)),
                latest_payload=latest_payload,
            )
            st.download_button(
                "Download doctor visit report (PDF)",
                data=pdf_bytes,
                file_name=f"doctor_visit_report_{d_from.isoformat()}_{d_to.isoformat()}.pdf",
                mime="application/pdf",
            )