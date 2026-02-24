import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from db import add_entry, init_db, list_entries

SCALE_0_3 = {
    0: "None",
    1: "Mild (noticeable, does not limit activity)",
    2: "Moderate (limits some activity / needs adjustments)",
    3: "Severe (stops activities / you are miserable)",
}
TIME_OF_DAY_OPTIONS = ["Morning", "Midday", "Evening", "Night", "Custom"]
MORNING_STIFFNESS_DURATION_OPTIONS = {
    0: "None",
    1: "< 15 minutes",
    2: "15-45 minutes",
    3: "45-120 minutes",
    4: "> 120 minutes",
}


def parse_optional_float(raw: str, field: str, errors: List[str]) -> Optional[float]:
    value = (raw or "").strip()
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        errors.append(f"{field} must be a number or blank.")
        return None


def softmax(scores: Dict[str, float]) -> Dict[str, float]:
    m = max(scores.values())
    exps = {k: math.exp(v - m) for k, v in scores.items()}
    total = sum(exps.values())
    return {k: round((exps[k] / total) * 100.0, 1) for k in scores.keys()}


def score_culprits(entry: Dict[str, Any]) -> Tuple[Dict[str, float], List[str]]:
    s = entry["symptoms"]
    meds = entry["meds"]
    labs = entry.get("labs", {}) or {}

    alerts: List[str] = []
    if s.get("jaundice_yes"):
        alerts.append(
            "Yellow skin/eyes or dark urine can be serious (especially on meds). "
            "Contact urgent care/doctor today."
        )
    if s.get("fever_yes") and s.get("sore_throat_0_3", 0) >= 2:
        alerts.append(
            "Fever + significant sore throat on DMARDs can be concerning. "
            "Contact urgent care/doctor today."
        )
    if s.get("rash_0_3", 0) >= 3 and s.get("mouth_sores_0_3", 0) >= 2:
        alerts.append(
            "Severe rash + mouth sores can signal a serious drug reaction. "
            "Seek urgent assessment now."
        )
    if s.get("palpitations_0_3", 0) >= 3:
        alerts.append(
            "Severe palpitations: consider urgent assessment, especially if "
            "dizzy/chest pain/short of breath."
        )

    scores = {
        "RA": 0.0,
        "Hypothyroidism": 0.0,
        "Sulfasalazine": 0.0,
        "Levothyroxine_Imbalance": 0.0,
        "Pregnancy": 0.0,
    }

    scores["RA"] += 1.5 * s.get("morning_stiffness_level_0_3", 0)
    scores["RA"] += 0.8 * s.get("morning_stiffness_duration_cat", 0)
    scores["RA"] += 1.2 * s.get("joint_swelling_0_3", 0)
    scores["RA"] += 0.8 * s.get("joint_warmth_0_3", 0)
    scores["RA"] += 0.8 * s.get("rest_stiffness_gelling_0_3", 0)
    scores["RA"] += 0.6 * (
        s.get("function_dressing_0_3", 0)
        + s.get("function_grip_0_3", 0)
        + s.get("function_walk_0_3", 0)
    )
    if s.get("symmetry_yes"):
        scores["RA"] += 1.0
    scores["RA"] += 0.2 * s.get("pain_0_10", 0)
    if labs.get("CRP") is not None and labs["CRP"] > 5:
        scores["RA"] += 2.0
    if labs.get("ESR") is not None and labs["ESR"] > 20:
        scores["RA"] += 2.0

    scores["Hypothyroidism"] += 1.2 * s.get("cold_intolerance_0_3", 0)
    scores["Hypothyroidism"] += 1.0 * s.get("constipation_0_3", 0)
    scores["Hypothyroidism"] += 1.2 * s.get("brain_fog_0_3", 0)
    scores["Hypothyroidism"] += 0.8 * s.get("fatigue_0_3", 0)
    if labs.get("TSH") is not None and labs["TSH"] > 4:
        scores["Hypothyroidism"] += 3.0
    if labs.get("FreeT4") is not None and labs["FreeT4"] < 0.8:
        scores["Hypothyroidism"] += 2.0
    if not meds.get("levothyroxine_taken_yes", True):
        scores["Hypothyroidism"] += 1.0

    scores["Levothyroxine_Imbalance"] += 1.5 * s.get("palpitations_0_3", 0)
    scores["Levothyroxine_Imbalance"] += 1.2 * s.get("tremor_0_3", 0)
    scores["Levothyroxine_Imbalance"] += 1.0 * s.get("anxiety_restlessness_0_3", 0)
    scores["Levothyroxine_Imbalance"] += 1.0 * s.get("heat_intolerance_0_3", 0)
    scores["Levothyroxine_Imbalance"] += 0.8 * s.get("sweating_0_3", 0)
    scores["Levothyroxine_Imbalance"] += 0.8 * s.get("sleep_trouble_0_3", 0)
    scores["Levothyroxine_Imbalance"] += 0.6 * s.get("diarrhea_0_3", 0)
    if labs.get("TSH") is not None and labs["TSH"] < 0.4:
        scores["Levothyroxine_Imbalance"] += 3.0
    if labs.get("FreeT4") is not None and labs["FreeT4"] > 1.8:
        scores["Levothyroxine_Imbalance"] += 2.0
    if meds.get("levothyroxine_taken_yes", True) and not meds.get(
        "levothyroxine_taken_correctly_yes", True
    ):
        scores["Levothyroxine_Imbalance"] += 0.5

    scores["Sulfasalazine"] += 1.0 * s.get("nausea_0_3", 0)
    scores["Sulfasalazine"] += 0.8 * s.get("abdominal_pain_0_3", 0)
    scores["Sulfasalazine"] += 0.8 * s.get("headache_0_3", 0)
    scores["Sulfasalazine"] += 1.4 * s.get("rash_0_3", 0)
    scores["Sulfasalazine"] += 1.2 * s.get("mouth_sores_0_3", 0)
    scores["Sulfasalazine"] += 1.2 * s.get("easy_bruising_0_3", 0)
    scores["Sulfasalazine"] += 1.0 * s.get("sore_throat_0_3", 0)
    if s.get("fever_yes"):
        scores["Sulfasalazine"] += 1.2
    if s.get("jaundice_yes"):
        scores["Sulfasalazine"] += 3.0
    if labs.get("WBC") is not None and labs["WBC"] < 4:
        scores["Sulfasalazine"] += 3.0
    if labs.get("Platelets") is not None and labs["Platelets"] < 150:
        scores["Sulfasalazine"] += 2.0
    if labs.get("ALT") is not None and labs["ALT"] > 40:
        scores["Sulfasalazine"] += 2.0
    if labs.get("AST") is not None and labs["AST"] > 40:
        scores["Sulfasalazine"] += 1.5

    if entry["symptoms"].get("preg_section_skipped") is True:
        scores["Pregnancy"] += 0.0
    else:
        preg = 0.0
        if s.get("missed_period_yes"):
            preg += 2.0
        preg += 0.8 * s.get("breast_tenderness_0_3", 0)
        preg += 1.0 * s.get("preg_nausea_0_3", 0)
        preg += 0.6 * s.get("frequent_urination_0_3", 0)
        if s.get("preg_test_positive_yes"):
            preg += 5.0
        if labs.get("hCG") is not None and labs["hCG"] > 25:
            preg += 6.0
        scores["Pregnancy"] += preg

    probs = softmax(scores)
    return probs, alerts


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
        "0 = None, 1 = Mild, 2 = Moderate, 3 = Severe. "
        "Use what best matches today."
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


st.set_page_config(page_title="Symptom Tracker", page_icon="🩺", layout="wide")
init_db()

st.title("🩺 CULPRITS Symptom Tracker")
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
    st.subheader("Today Overview")
    pain_0_10 = st.slider("Overall pain today (0-10)", 0, 10, 4)
    global_health_0_10 = st.slider(
        "Overall how unwell today? (0 great, 10 worst)", 0, 10, 4
    )

    st.divider()
    st.subheader("Function")
    render_scale_hint()
    f1, f2, f3 = st.columns(3)
    with f1:
        function_dressing_0_3 = st.slider(
            "Difficulty dressing (buttons, socks, etc.)", 0, 3, 0
        )
    with f2:
        function_grip_0_3 = st.slider(
            "Difficulty gripping/opening jars/turning knobs", 0, 3, 0
        )
    with f3:
        function_walk_0_3 = st.slider("Difficulty walking/stairs from pain", 0, 3, 0)

    st.divider()
    st.subheader("Joint / Inflammation Pattern (RA-focused)")
    render_scale_hint()
    morning_stiffness_level_0_3 = st.slider("Morning stiffness severity", 0, 3, 0)
    morning_stiffness_duration_cat = st.select_slider(
        "Morning stiffness duration",
        options=list(MORNING_STIFFNESS_DURATION_OPTIONS.keys()),
        value=1,
        format_func=lambda x: MORNING_STIFFNESS_DURATION_OPTIONS[x],
    )
    r1, r2 = st.columns(2)
    with r1:
        joint_swelling_0_3 = st.slider("Visible/felt joint swelling", 0, 3, 0)
        joint_warmth_0_3 = st.slider("Warmth/redness over joints", 0, 3, 0)
        rest_stiffness_gelling_0_3 = st.slider(
            "Stiffness after sitting/resting", 0, 3, 0
        )
    with r2:
        symmetry_yes = st.toggle("Both sides affected similarly?", value=False)
        fatigue_0_3 = st.slider("Fatigue/drained feeling today", 0, 3, 0)

    st.divider()
    st.subheader("Thyroid Pattern (Hypo vs Over-replacement)")
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
    st.subheader("Medication Side Effect Check (Sulfasalazine-focused)")
    render_scale_hint()
    s1, s2, s3 = st.columns(3)
    with s1:
        nausea_0_3 = st.slider("Nausea today", 0, 3, 0)
        abdominal_pain_0_3 = st.slider("Abdominal pain/cramps today", 0, 3, 0)
        headache_0_3 = st.slider("Headache today", 0, 3, 0)
    with s2:
        mouth_sores_0_3 = st.slider("Mouth ulcers/sore mouth today", 0, 3, 0)
        rash_0_3 = st.slider("Rash/itchy skin today", 0, 3, 0)
        easy_bruising_0_3 = st.slider("Easy bruising/unusual bleeding today", 0, 3, 0)
    with s3:
        sore_throat_0_3 = st.slider("Sore throat today", 0, 3, 0)
        fever_yes = st.toggle("Fever/chills today", value=False)
        jaundice_yes = st.toggle(
            "Yellow skin/eyes OR dark urine OR pale stools", value=False
        )

    st.divider()
    st.subheader("Pregnancy Check (if relevant)")
    missed_period_yes = st.toggle("Period late/missed right now?", value=False)
    preg_test_positive_yes = st.toggle("Any positive pregnancy test recently?", value=False)
    preg_followups = missed_period_yes or preg_test_positive_yes
    if preg_followups:
        render_scale_hint()
        p1, p2, p3 = st.columns(3)
        with p1:
            breast_tenderness_0_3 = st.slider("Breast tenderness today", 0, 3, 0)
        with p2:
            preg_nausea_0_3 = st.slider("Nausea that feels pregnancy-like", 0, 3, 0)
        with p3:
            frequent_urination_0_3 = st.slider(
                "Needing to urinate more often than usual", 0, 3, 0
            )
    else:
        st.caption("Pregnancy follow-up questions skipped for this entry.")
        breast_tenderness_0_3 = 0
        preg_nausea_0_3 = 0
        frequent_urination_0_3 = 0

    st.divider()
    st.subheader("Medication Adherence")
    m1, m2 = st.columns(2)
    with m1:
        levothyroxine_taken_yes = st.toggle(
            "Took levothyroxine (today or last scheduled dose)", value=True
        )
        levothyroxine_taken_correctly_yes = st.toggle(
            "Levothyroxine taken correctly (empty stomach, away from iron/calcium)",
            value=True,
        )
    with m2:
        sulfasalazine_taken_yes = st.toggle(
            "Took sulfasalazine (today or last scheduled dose)", value=True
        )
        new_meds_or_dose_change_yes = st.toggle(
            "Any new medication or dose change in last 7 days?", value=False
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
            labs_raw["hCG"] = st.text_input("hCG")
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
        placeholder="Food, infection exposure, triggers, medication timing, etc.",
    )

    submitted = st.form_submit_button("Review Entry")

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

        entry = {
            "timestamp": ts.isoformat(timespec="seconds"),
            "time_of_day": resolved_tod,
            "context": {
                "sleep_quality_0_3": sleep_quality_0_3,
                "stress_0_3": stress_0_3,
                "activity_change_0_3": activity_change_0_3,
            },
            "symptoms": {
                "pain_0_10": pain_0_10,
                "global_health_0_10": global_health_0_10,
                "function_dressing_0_3": function_dressing_0_3,
                "function_grip_0_3": function_grip_0_3,
                "function_walk_0_3": function_walk_0_3,
                "morning_stiffness_level_0_3": morning_stiffness_level_0_3,
                "morning_stiffness_duration_cat": morning_stiffness_duration_cat,
                "joint_swelling_0_3": joint_swelling_0_3,
                "joint_warmth_0_3": joint_warmth_0_3,
                "symmetry_yes": symmetry_yes,
                "rest_stiffness_gelling_0_3": rest_stiffness_gelling_0_3,
                "fatigue_0_3": fatigue_0_3,
                "cold_intolerance_0_3": cold_intolerance_0_3,
                "heat_intolerance_0_3": heat_intolerance_0_3,
                "constipation_0_3": constipation_0_3,
                "diarrhea_0_3": diarrhea_0_3,
                "brain_fog_0_3": brain_fog_0_3,
                "anxiety_restlessness_0_3": anxiety_restlessness_0_3,
                "palpitations_0_3": palpitations_0_3,
                "tremor_0_3": tremor_0_3,
                "sweating_0_3": sweating_0_3,
                "sleep_trouble_0_3": sleep_trouble_0_3,
                "nausea_0_3": nausea_0_3,
                "abdominal_pain_0_3": abdominal_pain_0_3,
                "headache_0_3": headache_0_3,
                "mouth_sores_0_3": mouth_sores_0_3,
                "rash_0_3": rash_0_3,
                "easy_bruising_0_3": easy_bruising_0_3,
                "sore_throat_0_3": sore_throat_0_3,
                "fever_yes": fever_yes,
                "jaundice_yes": jaundice_yes,
                "missed_period_yes": missed_period_yes,
                "preg_test_positive_yes": preg_test_positive_yes,
                "preg_section_skipped": not preg_followups,
                "breast_tenderness_0_3": breast_tenderness_0_3,
                "preg_nausea_0_3": preg_nausea_0_3,
                "frequent_urination_0_3": frequent_urination_0_3,
            },
            "meds": {
                "levothyroxine_taken_yes": levothyroxine_taken_yes,
                "levothyroxine_taken_correctly_yes": levothyroxine_taken_correctly_yes,
                "sulfasalazine_taken_yes": sulfasalazine_taken_yes,
                "new_meds_or_dose_change_yes": new_meds_or_dose_change_yes,
            },
            "labs": labs if include_labs else {},
            "cycle": cycle if include_cycle else {},
            "notes": (notes or "").strip() or None,
            "analysis": {},
        }

        probs, alerts = score_culprits(entry)
        entry["analysis"] = {
            "culprit_probabilities_percent": probs,
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

    probs = pending_entry["analysis"]["culprit_probabilities_percent"]
    prob_df = pd.DataFrame(
        sorted(probs.items(), key=lambda item: item[1], reverse=True),
        columns=["Culprit", "Likelihood (%)"],
    )
    st.dataframe(prob_df, width="stretch", hide_index=True)

    alerts = pending_entry["analysis"]["alerts"]
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

saved_entry = st.session_state.get("last_saved_entry")
if saved_entry:
    st.divider()
    st.subheader("Latest Saved Summary")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Timestamp", saved_entry["timestamp"])
    with c2:
        st.metric("Pain (0-10)", saved_entry["symptoms"]["pain_0_10"])
    with c3:
        st.metric("Unwell (0-10)", saved_entry["symptoms"]["global_health_0_10"])

    probs = saved_entry["analysis"]["culprit_probabilities_percent"]
    prob_df = pd.DataFrame(
        sorted(probs.items(), key=lambda item: item[1], reverse=True),
        columns=["Culprit", "Likelihood (%)"],
    )
    st.dataframe(prob_df, width="stretch", hide_index=True)

    alerts = saved_entry["analysis"]["alerts"]
    if alerts:
        st.warning("Safety alerts")
        for alert in alerts:
            st.write(f"- {alert}")

    with st.expander("View full saved payload"):
        st.json(saved_entry)

st.divider()
history = list_entries()

if not history:
    st.info("No entries yet. Save your first daily entry above.")
else:
    st.subheader("Recent Entries")
    summary_rows: List[Dict[str, Any]] = []
    for row in history:
        analysis = row.get("analysis", {}) or {}
        alerts = analysis.get("alerts", []) if isinstance(analysis, dict) else []
        summary_rows.append(
            {
                "ts": row.get("ts"),
                "time_of_day": row.get("time_of_day") or "-",
                "pain": row.get("pain") if row.get("pain") is not None else row.get("severity"),
                "global_health": row.get("global_health"),
                "top_culprit": row.get("top_culprit") or row.get("symptom") or "-",
                "alerts": len(alerts),
                "notes": row.get("notes") or "",
            }
        )

    df = pd.DataFrame(summary_rows)
    st.dataframe(df, width="stretch", hide_index=True)

    st.subheader("Quick Trend")
    metric_name = st.selectbox("Metric", ["Pain (0-10)", "Global health (0-10)"])
    culprit_options = sorted(
        [v for v in df["top_culprit"].dropna().unique().tolist() if v and v != "-"]
    )
    culprit_filter = st.multiselect("Filter by top culprit", culprit_options)

    metric_col = "pain" if metric_name.startswith("Pain") else "global_health"
    plot_df = df.copy()
    if culprit_filter:
        plot_df = plot_df[plot_df["top_culprit"].isin(culprit_filter)]

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
