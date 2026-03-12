import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from db import add_entry, init_db, list_entries

# -----------------------------
# Constants / labels
# -----------------------------
SCALE_0_3 = {
    0: "None",
    1: "Mild (noticeable, does not limit activity)",
    2: "Moderate (limits some activity / needs adjustments)",
    3: "Severe (stops activities / you are miserable)",
}
TIME_OF_DAY_OPTIONS = ["Morning", "Midday", "Evening", "Night", "Custom"]

STIFFNESS_BUCKETS = {
    0: "0–15 min",
    1: "15–30 min",
    2: "30–60 min",
    3: "60–120 min",
    4: ">120 min",
}

# Early-RA weighted regions (simple, high-yield, non-DAS28)
JOINT_REGIONS = [
    ("L_wrist", "Left wrist"),
    ("R_wrist", "Right wrist"),
    ("L_mcp_2_5", "Left knuckles (MCP 2–5)"),
    ("R_mcp_2_5", "Right knuckles (MCP 2–5)"),
    ("L_pip_2_5", "Left finger middle joints (PIP 2–5)"),
    ("R_pip_2_5", "Right finger middle joints (PIP 2–5)"),
    ("L_mtp_2_5", "Left ball of foot (MTP 2–5)"),
    ("R_mtp_2_5", "Right ball of foot (MTP 2–5)"),
]


# -----------------------------
# Helpers
# -----------------------------
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


def render_scale_hint() -> None:
    st.caption(
        "0 = None, 1 = Mild, 2 = Moderate, 3 = Severe. Use what best matches today."
    )


def pretty_value(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if value is None:
        return "(blank)"
    return str(value)


def review_rows(section: str, payload: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"Section": section, "Field": key, "Value": pretty_value(val)}
        for key, val in payload.items()
    ]


def safe_get(d: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


# -----------------------------
# Clinical analysis (RA + Thyroid)
# -----------------------------
def score_stiffness_bucket(bucket: int) -> int:
    # 0–20 points
    return {0: 0, 1: 5, 2: 10, 3: 15, 4: 20}.get(int(bucket), 0)


def ra_activity_score_0_100(symptoms: Dict[str, Any]) -> int:
    """
    Practical, trend-friendly RA score (NOT a diagnosis):
    - Pain 0–10 weighted
    - RA-type fatigue 0–10 weighted
    - Morning stiffness duration bucket weighted
    - Swollen region burden across early-RA joints
    """
    pain = max(0, min(10, int(symptoms.get("pain_0_10", 0)))) * 4  # 0–40
    fatigue = max(0, min(10, int(symptoms.get("fatigue_0_10", 0)))) * 2  # 0–20
    stiffness = score_stiffness_bucket(int(symptoms.get("morning_stiffness_duration_cat", 0)))  # 0–20

    jm = symptoms.get("joint_map", {}) or {}
    sjc = sum(1 for v in jm.values() if isinstance(v, dict) and v.get("swollen") is True)

    # Swollen-burden points (0–20)
    if sjc == 0:
        swollen_points = 0
    elif sjc <= 2:
        swollen_points = 5
    elif sjc <= 5:
        swollen_points = 10
    elif sjc <= 7:
        swollen_points = 15
    else:
        swollen_points = 20

    return int(min(100, pain + fatigue + stiffness + swollen_points))


def early_ra_pattern_flags(symptoms: Dict[str, Any]) -> Dict[str, Any]:
    """
    Early inflammatory arthritis / possible early RA pattern flags (NOT a diagnosis).
    Built around:
    - stiffness >= 30 min
    - small joint involvement (hands/wrists/feet)
    - gelling and/or improves with movement
    - swelling and/or MCP/MTP squeeze positivity and/or symmetry
    """
    stiffness_ge_30 = int(symptoms.get("morning_stiffness_duration_cat", 0)) >= 2
    gelling_present = int(symptoms.get("rest_stiffness_gelling_0_3", 0)) >= 1
    improves = symptoms.get("improves_with_movement", "unsure") in ("yes", "unsure")

    jm = symptoms.get("joint_map", {}) or {}
    key_joints = [
        "L_wrist",
        "R_wrist",
        "L_mcp_2_5",
        "R_mcp_2_5",
        "L_pip_2_5",
        "R_pip_2_5",
        "L_mtp_2_5",
        "R_mtp_2_5",
    ]
    small_joint_involved = any(
        (jm.get(k, {}) or {}).get("tender") or (jm.get(k, {}) or {}).get("swollen")
        for k in key_joints
    )
    swollen_regions_count = sum(
        1 for v in jm.values() if isinstance(v, dict) and v.get("swollen") is True
    )

    squeeze_positive = bool(symptoms.get("mcp_squeeze_pain")) or bool(
        symptoms.get("mtp_squeeze_pain")
    )
    symmetric = bool(symptoms.get("symmetry_yes"))

    # Inflammatory arthritis pattern
    pattern_suggests_inflammatory = bool(
        stiffness_ge_30 and small_joint_involved and (gelling_present or improves)
    )

    # Higher priority / possible early RA pattern
    pattern_higher_priority = bool(
        pattern_suggests_inflammatory and (swollen_regions_count >= 2 or squeeze_positive or symmetric)
    )

    return {
        "stiffness_ge_30min": stiffness_ge_30,
        "small_joint_involved": small_joint_involved,
        "swollen_regions_count": swollen_regions_count,
        "mcp_or_mtp_squeeze_positive": squeeze_positive,
        "symmetry_reported": symmetric,
        "pattern_suggests_inflammatory_arthritis": pattern_suggests_inflammatory,
        "pattern_higher_priority_possible_early_RA": pattern_higher_priority,
    }


def thyroid_flags(symptoms: Dict[str, Any], meds: Dict[str, Any], labs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Separate module: hypothyroid drift vs possible over-replacement.
    Trend tool only; labs (if provided) can support suspicion.
    """
    # Under-replacement symptom cluster (use moderate+ threshold)
    under_symptoms = 0
    under_symptoms += int(int(symptoms.get("cold_intolerance_0_3", 0)) >= 2)
    under_symptoms += int(int(symptoms.get("constipation_0_3", 0)) >= 2)
    under_symptoms += int(int(symptoms.get("brain_fog_0_3", 0)) >= 2)

    tsh_high = labs.get("TSH") is not None and labs["TSH"] > 4
    ft4_low = labs.get("FreeT4") is not None and labs["FreeT4"] < 0.8
    missed = not meds.get("levothyroxine_taken_yes", True)

    possible_under = bool(under_symptoms >= 2 or tsh_high or ft4_low or missed)

    # Over-replacement cluster (moderate+)
    over_cluster = 0
    over_cluster += int(int(symptoms.get("palpitations_0_3", 0)) >= 2)
    over_cluster += int(int(symptoms.get("tremor_0_3", 0)) >= 2)
    over_cluster += int(int(symptoms.get("heat_intolerance_0_3", 0)) >= 2)
    over_cluster += int(int(symptoms.get("sleep_trouble_0_3", 0)) >= 2)
    over_cluster += int(int(symptoms.get("sweating_0_3", 0)) >= 2)
    over_cluster += int(int(symptoms.get("diarrhea_0_3", 0)) >= 2)

    tsh_low = labs.get("TSH") is not None and labs["TSH"] < 0.4
    ft4_high = labs.get("FreeT4") is not None and labs["FreeT4"] > 1.8

    possible_over = bool(over_cluster >= 2 or tsh_low or ft4_high)

    # Adherence / timing note
    taken_correctly = meds.get("levothyroxine_taken_correctly_yes", True)

    return {
        "possible_under_replacement": possible_under,
        "possible_over_replacement": possible_over,
        "under_symptom_count_ge2": under_symptoms >= 2,
        "over_cluster_count": over_cluster,
        "tsh_high": bool(tsh_high),
        "tsh_low": bool(tsh_low),
        "ft4_low": bool(ft4_low),
        "ft4_high": bool(ft4_high),
        "levothyroxine_taken_correctly": bool(taken_correctly),
    }


def analyze_entry(entry: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Returns analysis dict + safety alerts list.
    """
    s = entry.get("symptoms", {}) or {}
    meds = entry.get("meds", {}) or {}
    labs = entry.get("labs", {}) or {}

    alerts: List[str] = []
    # Minimal safety flags (keep strict, avoid alarm fatigue)
    if int(s.get("palpitations_0_3", 0)) >= 3:
        alerts.append(
            "Severe palpitations: seek urgent assessment if chest pain, fainting, severe shortness of breath, "
            "or persistent rapid heartbeat."
        )

    ra_score = ra_activity_score_0_100(s)
    ra_flags = early_ra_pattern_flags(s)
    thyroid = thyroid_flags(s, meds, labs)

    # Derived quick counts (useful for clinicians)
    jm = s.get("joint_map", {}) or {}
    tjc_proxy = sum(1 for v in jm.values() if isinstance(v, dict) and v.get("tender") is True)
    sjc_proxy = sum(1 for v in jm.values() if isinstance(v, dict) and v.get("swollen") is True)

    return (
        {
            "ra_activity_score_0_100": ra_score,
            "ra_tender_regions_proxy": tjc_proxy,
            "ra_swollen_regions_proxy": sjc_proxy,
            "early_ra_pattern": ra_flags,
            "thyroid_flags": thyroid,
        },
        alerts,
    )


# -----------------------------
# App UI
# -----------------------------
st.set_page_config(page_title="Symptom Tracker", page_icon="🩺", layout="wide")
init_db()

st.title("🩺 RA + Thyroid Daily Tracker")
st.caption("Tracking tool only. Not medical advice.")

with st.form("daily_survey_form", clear_on_submit=False):
    st.subheader("Entry Timing")
    ts = st.datetime_input("Date & time", value=datetime.now())
    tod = st.selectbox(
        "Time of day for this entry",
        TIME_OF_DAY_OPTIONS,
        index=TIME_OF_DAY_OPTIONS.index(default_time_of_day()),
    )
    custom_tod = st.text_input(
        "Custom time-of-day label",
        placeholder="e.g., after lunch, post-work",
        disabled=(tod != "Custom"),
    )

    st.divider()
    st.subheader("Context")
    render_scale_hint()
    c1, c2, c3 = st.columns(3)
    with c1:
        sleep_quality_0_3 = st.slider("Sleep quality last night", 0, 3, 1)
    with c2:
        stress_0_3 = st.slider("Stress in last 24 hours", 0, 3, 1)
    with c3:
        activity_change_0_3 = st.slider("Unusual activity vs normal", 0, 3, 0)

    st.divider()
    st.subheader("Early RA Pattern (hands/feet + inflammation pattern)")
    st.caption("Focus: rheumatoid arthritis disease activity (not medication side effects).")
    # Inflammatory pattern
    morning_stiffness_duration_cat = st.select_slider(
        "Morning stiffness duration",
        options=list(STIFFNESS_BUCKETS.keys()),
        value=2,
        format_func=lambda x: STIFFNESS_BUCKETS[x],
    )
    render_scale_hint()
    rest_stiffness_gelling_0_3 = st.slider("Stiffness after sitting/resting (gelling)", 0, 3, 0)
    improves_with_movement = st.selectbox(
        "Do symptoms improve with gentle movement?",
        ["yes", "no", "unsure"],
        index=0,
    )

    # Global RA symptom intensity
    pain_0_10 = st.slider("Overall joint pain today (0–10)", 0, 10, 4)
    fatigue_0_10 = st.slider("RA-type fatigue today (0–10)", 0, 10, 4)
    global_health_0_10 = st.slider("Overall how unwell today? (0 great, 10 worst)", 0, 10, 4)

    st.markdown("**Joint map (today):** mark tenderness and swelling for common early-RA joints.")
    jm1, jm2 = st.columns(2)
    joint_map: Dict[str, Dict[str, bool]] = {}
    for i, (key, label) in enumerate(JOINT_REGIONS):
        col = jm1 if i % 2 == 0 else jm2
        with col:
            tender = st.toggle(f"{label} — tender?", value=False, key=f"{key}_t")
            swollen = st.toggle(f"{label} — swollen/puffy?", value=False, key=f"{key}_s")
            joint_map[key] = {"tender": tender, "swollen": swollen}

    st.markdown("**Quick home screens:**")
    mcp_squeeze_pain = st.toggle(
        "MCP squeeze painful? (gently squeeze across knuckles)",
        value=False,
    )
    mtp_squeeze_pain = st.toggle(
        "MTP squeeze painful? (gently squeeze across ball of foot)",
        value=False,
    )
    symmetry_yes = st.toggle("Both sides affected similarly?", value=False)

    st.markdown("**Function (0–3):**")
    render_scale_hint()
    f1, f2, f3 = st.columns(3)
    with f1:
        fn_open_jar_0_3 = st.slider("Opening jars / twisting lids", 0, 3, 0)
    with f2:
        fn_buttons_0_3 = st.slider("Buttons / fine finger tasks", 0, 3, 0)
    with f3:
        fn_stairs_0_3 = st.slider("Stairs / walking from joint pain", 0, 3, 0)

    st.divider()
    st.subheader("Thyroid Pattern (Hypothyroid drift vs possible over-replacement)")
    st.caption("This module tracks symptoms that can relate to thyroid levels and levothyroxine balance.")
    render_scale_hint()
    t1, t2, t3 = st.columns(3)
    with t1:
        cold_intolerance_0_3 = st.slider("Feeling unusually cold", 0, 3, 0)
        heat_intolerance_0_3 = st.slider("Feeling unusually hot", 0, 3, 0)
        brain_fog_0_3 = st.slider("Brain fog / slow thinking", 0, 3, 0)
        sleep_trouble_0_3 = st.slider("Trouble sleeping", 0, 3, 0)
    with t2:
        constipation_0_3 = st.slider("Constipation today", 0, 3, 0)
        diarrhea_0_3 = st.slider("Diarrhea today", 0, 3, 0)
        anxiety_restlessness_0_3 = st.slider("Anxiety/restlessness today", 0, 3, 0)
    with t3:
        palpitations_0_3 = st.slider("Palpitations/heart racing", 0, 3, 0)
        tremor_0_3 = st.slider("Shaky hands/tremor", 0, 3, 0)
        sweating_0_3 = st.slider("Unusual sweating", 0, 3, 0)

    st.divider()
    st.subheader("Levothyroxine Adherence (no RA meds module yet)")
    m1, m2 = st.columns(2)
    with m1:
        levothyroxine_taken_yes = st.toggle(
            "Took levothyroxine (today or last scheduled dose)", value=True
        )
    with m2:
        levothyroxine_taken_correctly_yes = st.toggle(
            "Taken correctly (empty stomach, away from iron/calcium)",
            value=True,
        )

    st.divider()
    st.subheader("Labs Module (optional)")
    include_labs = st.toggle("Add bloodwork results", value=False)
    labs_raw: Dict[str, str] = {}
    if include_labs:
        st.caption("Enter values you have. Leave blank to skip any item.")
        l1, l2, l3 = st.columns(3)
        with l1:
            labs_raw["CRP"] = st.text_input("CRP")
            labs_raw["ESR"] = st.text_input("ESR")
            labs_raw["TSH"] = st.text_input("TSH")
            labs_raw["FreeT4"] = st.text_input("Free T4")
            labs_raw["FreeT3"] = st.text_input("Free T3")
        with l2:
            labs_raw["WBC"] = st.text_input("WBC")
            labs_raw["Hemoglobin"] = st.text_input("Hemoglobin")
            labs_raw["Platelets"] = st.text_input("Platelets")
            labs_raw["ALT"] = st.text_input("ALT")
            labs_raw["AST"] = st.text_input("AST")
        with l3:
            labs_raw["AntiCCP"] = st.text_input("Anti-CCP")
            labs_raw["RF"] = st.text_input("Rheumatoid Factor")

    st.divider()
    st.subheader("Period / Cycle Overlay (optional)")
    include_cycle = st.toggle("Add period/cycle info", value=False)
    currently_bleeding_yes = False
    period_day_number_raw = ""
    cycle_day_number_raw = ""
    ovulation_test_positive_yes = False
    ovulation_symptoms_0_3 = 0
    pms_symptoms_0_3 = 0
    if include_cycle:
        c1, c2 = st.columns(2)
        with c1:
            currently_bleeding_yes = st.toggle(
                "Currently bleeding (period) today?", value=False
            )
            period_day_number_raw = st.text_input(
                "If bleeding: day number of period (1, 2, 3...)"
            )
            cycle_day_number_raw = st.text_input(
                "Cycle day number (Day 1 = first day of bleeding)"
            )
        with c2:
            ovulation_test_positive_yes = st.toggle(
                "Ovulation/LH test positive in last 48 hours?", value=False
            )
            render_scale_hint()
            ovulation_symptoms_0_3 = st.slider("Ovulation-type symptoms today", 0, 3, 0)
            pms_symptoms_0_3 = st.slider("PMS-type symptoms today", 0, 3, 0)

    notes = st.text_area(
        "Notes (optional)",
        placeholder="Food, infection exposure, stressors, triggers, sleep, timing details, etc.",
    )

    submitted = st.form_submit_button("Review Entry")


# -----------------------------
# Review / Save
# -----------------------------
if submitted:
    errors: List[str] = []

    labs: Dict[str, Optional[float]] = {}
    if include_labs:
        for field, raw in labs_raw.items():
            labs[field] = parse_optional_float(raw, field, errors)

    cycle: Dict[str, Any] = {}
    if include_cycle:
        cycle["currently_bleeding_yes"] = currently_bleeding_yes
        cycle["period_day_number"] = parse_optional_float(
            period_day_number_raw, "period_day_number", errors
        )
        cycle["cycle_day_number"] = parse_optional_float(
            cycle_day_number_raw, "cycle_day_number", errors
        )
        cycle["ovulation_test_positive_yes"] = ovulation_test_positive_yes
        cycle["ovulation_symptoms_0_3"] = ovulation_symptoms_0_3
        cycle["pms_symptoms_0_3"] = pms_symptoms_0_3

    if errors:
        for err in errors:
            st.error(err)
    else:
        resolved_tod = tod
        if tod == "Custom":
            custom_clean = (custom_tod or "").strip()
            resolved_tod = custom_clean if custom_clean else "Custom"

        entry: Dict[str, Any] = {
            "timestamp": ts.isoformat(timespec="seconds"),
            "time_of_day": resolved_tod,
            "context": {
                "sleep_quality_0_3": sleep_quality_0_3,
                "stress_0_3": stress_0_3,
                "activity_change_0_3": activity_change_0_3,
            },
            "symptoms": {
                # RA pattern
                "morning_stiffness_duration_cat": int(morning_stiffness_duration_cat),
                "rest_stiffness_gelling_0_3": int(rest_stiffness_gelling_0_3),
                "improves_with_movement": improves_with_movement,
                "pain_0_10": int(pain_0_10),
                "fatigue_0_10": int(fatigue_0_10),
                "global_health_0_10": int(global_health_0_10),
                "joint_map": joint_map,
                "mcp_squeeze_pain": bool(mcp_squeeze_pain),
                "mtp_squeeze_pain": bool(mtp_squeeze_pain),
                "symmetry_yes": bool(symmetry_yes),
                # Function
                "fn_open_jar_0_3": int(fn_open_jar_0_3),
                "fn_buttons_0_3": int(fn_buttons_0_3),
                "fn_stairs_0_3": int(fn_stairs_0_3),
                # Thyroid symptom pattern
                "cold_intolerance_0_3": int(cold_intolerance_0_3),
                "heat_intolerance_0_3": int(heat_intolerance_0_3),
                "brain_fog_0_3": int(brain_fog_0_3),
                "sleep_trouble_0_3": int(sleep_trouble_0_3),
                "constipation_0_3": int(constipation_0_3),
                "diarrhea_0_3": int(diarrhea_0_3),
                "anxiety_restlessness_0_3": int(anxiety_restlessness_0_3),
                "palpitations_0_3": int(palpitations_0_3),
                "tremor_0_3": int(tremor_0_3),
                "sweating_0_3": int(sweating_0_3),
            },
            "meds": {
                "levothyroxine_taken_yes": bool(levothyroxine_taken_yes),
                "levothyroxine_taken_correctly_yes": bool(
                    levothyroxine_taken_correctly_yes
                ),
                # Reserved for future RA medication module
                "new_meds_or_dose_change_yes": False,
            },
            "labs": labs if include_labs else {},
            "cycle": cycle if include_cycle else {},
            "notes": (notes or "").strip() or None,
            "analysis": {},
        }

        analysis, alerts = analyze_entry(entry)

        # Store analysis in a stable structure (avoid old "culprit probabilities")
        entry["analysis"] = {
            "analysis": analysis,
            "alerts": alerts,
        }

        st.session_state["pending_entry"] = entry
        st.info(
            "Review ready below. Confirm save to write this entry, "
            "or edit answers above and review again."
        )

pending_entry = st.session_state.get("pending_entry")
if pending_entry:
    st.divider()
    st.subheader("Review Entry Before Save")
    st.caption("Nothing is saved until you click Confirm & Save.")

    meta_df = pd.DataFrame(
        [
            {"Field": "timestamp", "Value": pending_entry.get("timestamp")},
            {"Field": "time_of_day", "Value": pending_entry.get("time_of_day")},
            {"Field": "notes", "Value": pretty_value(pending_entry.get("notes"))},
        ]
    )
    st.dataframe(meta_df, width="stretch", hide_index=True)

    rows: List[Dict[str, str]] = []
    rows.extend(review_rows("context", pending_entry.get("context", {}) or {}))
    rows.extend(review_rows("symptoms", pending_entry.get("symptoms", {}) or {}))
    rows.extend(review_rows("meds", pending_entry.get("meds", {}) or {}))
    rows.extend(review_rows("labs", pending_entry.get("labs", {}) or {}))
    rows.extend(review_rows("cycle", pending_entry.get("cycle", {}) or {}))

    review_df = pd.DataFrame(rows)
    if not review_df.empty:
        st.dataframe(review_df, width="stretch", hide_index=True)

    # Analysis summary (RA score + flags + thyroid)
    st.subheader("Computed Summary")
    a = safe_get(pending_entry, ["analysis", "analysis"], {}) or {}
    ra_score = a.get("ra_activity_score_0_100")
    tjc = a.get("ra_tender_regions_proxy")
    sjc = a.get("ra_swollen_regions_proxy")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("RA Activity Score (0–100)", ra_score if ra_score is not None else "-")
    with c2:
        st.metric("Tender regions (proxy)", tjc if tjc is not None else "-")
    with c3:
        st.metric("Swollen regions (proxy)", sjc if sjc is not None else "-")

    ra_flags = a.get("early_ra_pattern", {}) or {}
    if ra_flags:
        st.markdown("**Early RA Pattern Flags (screening logic, not diagnosis):**")
        st.write(
            {
                "stiffness ≥ 30 min": ra_flags.get("stiffness_ge_30min"),
                "small joints involved": ra_flags.get("small_joint_involved"),
                "MCP/MTP squeeze positive": ra_flags.get("mcp_or_mtp_squeeze_positive"),
                "symmetry reported": ra_flags.get("symmetry_reported"),
                "pattern suggests inflammatory arthritis": ra_flags.get(
                    "pattern_suggests_inflammatory_arthritis"
                ),
                "higher priority possible early RA": ra_flags.get(
                    "pattern_higher_priority_possible_early_RA"
                ),
            }
        )

    thyroid = a.get("thyroid_flags", {}) or {}
    if thyroid:
        st.markdown("**Thyroid Flags (trend tool, not diagnosis):**")
        st.write(
            {
                "possible under-replacement": thyroid.get("possible_under_replacement"),
                "possible over-replacement": thyroid.get("possible_over_replacement"),
                "levothyroxine taken correctly": thyroid.get(
                    "levothyroxine_taken_correctly"
                ),
            }
        )

    alerts = safe_get(pending_entry, ["analysis", "alerts"], []) or []
    if alerts:
        st.warning("Safety alerts")
        for alert in alerts:
            st.write(f"- {alert}")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Confirm & Save", type="primary"):
            add_entry(pending_entry)
            st.session_state["last_saved_entry"] = pending_entry
            st.session_state.pop("pending_entry", None)
            st.success("Saved daily entry.")
    with c2:
        if st.button("Edit Answers"):
            st.session_state.pop("pending_entry", None)
            st.info("Review cleared. Update the form above and click Review Entry again.")
    with c3:
        if st.button("Discard Draft"):
            st.session_state.pop("pending_entry", None)
            st.warning("Draft entry discarded.")


# -----------------------------
# Latest saved summary
# -----------------------------
saved_entry = st.session_state.get("last_saved_entry")
if saved_entry:
    st.divider()
    st.subheader("Latest Saved Summary")

    a = safe_get(saved_entry, ["analysis", "analysis"], {}) or {}
    ra_score = a.get("ra_activity_score_0_100")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Timestamp", saved_entry.get("timestamp", "-"))
    with c2:
        st.metric("Pain (0–10)", safe_get(saved_entry, ["symptoms", "pain_0_10"], "-"))
    with c3:
        st.metric("RA Score (0–100)", ra_score if ra_score is not None else "-")

    alerts = safe_get(saved_entry, ["analysis", "alerts"], []) or []
    if alerts:
        st.warning("Safety alerts")
        for alert in alerts:
            st.write(f"- {alert}")

    with st.expander("View full saved payload"):
        st.json(saved_entry)


# -----------------------------
# History + Trend
# -----------------------------
st.divider()
history = list_entries()

def extract_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Try to be backwards-compatible with older DB rows.
    - Some DBs store flattened columns (pain/global_health/top_culprit)
    - Some store a JSON payload with analysis embedded
    """
    # best effort fields
    ts_val = row.get("ts") or row.get("timestamp")
    time_of_day = row.get("time_of_day") or "-"
    notes = row.get("notes") or ""

    # Pain/global health might be stored flat
    pain = row.get("pain")
    global_health = row.get("global_health")

    # If not, try within payload-like dicts
    payload_symptoms = row.get("symptoms") if isinstance(row.get("symptoms"), dict) else {}
    if pain is None:
        pain = payload_symptoms.get("pain_0_10")
    if global_health is None:
        global_health = payload_symptoms.get("global_health_0_10")

    # Try RA score from analysis (new)
    ra_score = None
    analysis = row.get("analysis")
    if isinstance(analysis, dict):
        ra_score = safe_get(analysis, ["analysis", "ra_activity_score_0_100"])
        alerts = analysis.get("alerts", [])
    else:
        ra_score = None
        alerts = []

    return {
        "ts": ts_val,
        "time_of_day": time_of_day,
        "pain": pain,
        "global_health": global_health,
        "ra_score": ra_score,
        "alerts": len(alerts) if isinstance(alerts, list) else 0,
        "notes": notes,
    }

if not history:
    st.info("No entries yet. Save your first daily entry above.")
else:
    st.subheader("Recent Entries")
    summary_rows = [extract_from_row(r) for r in history]
    df = pd.DataFrame(summary_rows)
    st.dataframe(df, width="stretch", hide_index=True)

    st.subheader("Quick Trend")
    metric_name = st.selectbox("Metric", ["Pain (0–10)", "Global health (0–10)", "RA score (0–100)"])

    metric_col = "pain" if metric_name.startswith("Pain") else ("global_health" if metric_name.startswith("Global") else "ra_score")
    plot_df = df.copy()

    plot_df["ts"] = pd.to_datetime(plot_df["ts"], errors="coerce")
    plot_df[metric_col] = pd.to_numeric(plot_df[metric_col], errors="coerce")
    series = (
        plot_df.dropna(subset=["ts", metric_col])
        .sort_values("ts")
        .set_index("ts")[metric_col]
    )

    if series.empty:
        st.info("No data available for the selected trend view.")
    else:
        st.line_chart(series)