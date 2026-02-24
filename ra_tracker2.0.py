import json
import os
import datetime
from typing import Dict, Any, Optional, List, Tuple

DATA_FILE = "culprits_daily_log.jsonl"

# -----------------------------
# Input helpers
# -----------------------------
SCALE_0_3 = {
    0: "None",
    1: "Mild (noticeable, doesn’t limit activity)",
    2: "Moderate (limits some activity / needs adjustments)",
    3: "Severe (stops activities / you’re miserable)"
}

def ask_scale_0_3(prompt: str) -> int:
    while True:
        print(f"\n{prompt}")
        for k, v in SCALE_0_3.items():
            print(f"  {k} = {v}")
        raw = input("Choose 0-3: ").strip()
        if raw in {"0", "1", "2", "3"}:
            return int(raw)
        print("Please enter 0, 1, 2, or 3.")

def ask_scale_0_10(prompt: str) -> int:
    while True:
        raw = input(f"\n{prompt} (0-10): ").strip()
        if raw.isdigit():
            val = int(raw)
            if 0 <= val <= 10:
                return val
        print("Please enter a number from 0 to 10.")

def ask_yes_no(prompt: str) -> bool:
    while True:
        raw = input(f"\n{prompt} (y/n): ").strip().lower()
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Please enter y or n.")

def ask_optional_float(prompt: str) -> Optional[float]:
    raw = input(f"\n{prompt} (press Enter to skip): ").strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        print("Invalid number. Skipping.")
        return None

def ask_optional_text(prompt: str) -> Optional[str]:
    raw = input(f"\n{prompt} (press Enter to skip): ").strip()
    return raw if raw else None

def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")

# -----------------------------
# Questionnaire (daily)
# -----------------------------
def run_daily_survey() -> Dict[str, Any]:
    print("\n==============================")
    print("CULPRITS Daily Check-In (v2)")
    print("==============================")
    print("This is a tracking tool, not a diagnosis.\n")

    entry: Dict[str, Any] = {
        "timestamp": now_iso(),
        "context": {},
        "symptoms": {},
        "meds": {},
        "labs": {},
        "notes": None,
    }

    # ---- Context quick taps (useful for interpretation)
    entry["context"]["sleep_quality_0_3"] = ask_scale_0_3("How was your sleep quality last night?")
    entry["context"]["stress_0_3"] = ask_scale_0_3("How high was your stress in the last 24 hours?")
    entry["context"]["activity_change_0_3"] = ask_scale_0_3("Any unusual physical activity compared to your normal?")

    # ---- Core “today” outcome measures (RAPID3-inspired)
    entry["symptoms"]["pain_0_10"] = ask_scale_0_10("Overall pain today")
    entry["symptoms"]["global_health_0_10"] = ask_scale_0_10("Overall how unwell do you feel today (0=great, 10=worst)?")

    # Function mini-set (daily-friendly)
    entry["symptoms"]["function_dressing_0_3"] = ask_scale_0_3("Difficulty getting dressed (buttons, socks, bra, etc.)?")
    entry["symptoms"]["function_grip_0_3"] = ask_scale_0_3("Difficulty gripping / opening jars / turning knobs?")
    entry["symptoms"]["function_walk_0_3"] = ask_scale_0_3("Difficulty walking / stairs because of joint or body pain?")

    # ---- RA-focused inflammatory pattern questions
    print("\n--- Joint / Inflammation Pattern (RA-focused) ---")
    entry["symptoms"]["morning_stiffness_level_0_3"] = ask_scale_0_3("Morning stiffness severity")
    # stiffness duration as a category (daily useful, avoids long text)
    print("\nMorning stiffness duration today:")
    print("  0 = none")
    print("  1 = < 15 minutes")
    print("  2 = 15–45 minutes")
    print("  3 = 45–120 minutes")
    print("  4 = > 120 minutes")
    while True:
        raw = input("Choose 0-4: ").strip()
        if raw in {"0","1","2","3","4"}:
            entry["symptoms"]["morning_stiffness_duration_cat"] = int(raw)
            break
        print("Please enter 0-4.")

    entry["symptoms"]["joint_swelling_0_3"] = ask_scale_0_3("Visible or felt joint swelling today?")
    entry["symptoms"]["joint_warmth_0_3"] = ask_scale_0_3("Warmth/redness over joints today?")
    entry["symptoms"]["symmetry_yes"] = ask_yes_no("Are BOTH sides affected in a similar way (both hands/wrists/feet)?")
    entry["symptoms"]["rest_stiffness_gelling_0_3"] = ask_scale_0_3("Stiffness after sitting/resting (the 'gelling' feeling)?")
    entry["symptoms"]["fatigue_0_3"] = ask_scale_0_3("Fatigue / drained feeling today?")

    # Joint distribution (simple multi-select)
    print("\nWhich areas are most affected today? (comma-separated numbers, or Enter to skip)")
    areas = [
        "Hands/fingers", "Wrists", "Elbows", "Shoulders", "Jaw",
        "Knees", "Ankles", "Feet/toes", "Hips", "Neck/back (inflammatory-type)"
    ]
    for i, a in enumerate(areas, start=1):
        print(f"  {i}. {a}")
    raw = input("Selection: ").strip()
    if raw:
        chosen = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                idx = int(part)
                if 1 <= idx <= len(areas):
                    chosen.append(areas[idx-1])
        entry["symptoms"]["joint_areas"] = sorted(set(chosen))
    else:
        entry["symptoms"]["joint_areas"] = []

    # ---- Endocrinology: hypo vs hyper-ish signals (daily sensitive)
    print("\n--- Thyroid Pattern (Hypo vs Over-replacement) ---")
    entry["symptoms"]["cold_intolerance_0_3"] = ask_scale_0_3("Feeling unusually cold compared to others?")
    entry["symptoms"]["heat_intolerance_0_3"] = ask_scale_0_3("Feeling unusually hot / heat intolerance?")
    entry["symptoms"]["constipation_0_3"] = ask_scale_0_3("Constipation today?")
    entry["symptoms"]["diarrhea_0_3"] = ask_scale_0_3("Diarrhea today?")
    entry["symptoms"]["brain_fog_0_3"] = ask_scale_0_3("Brain fog / slow thinking / forgetful today?")
    entry["symptoms"]["anxiety_restlessness_0_3"] = ask_scale_0_3("Anxiety / restlessness today?")
    entry["symptoms"]["palpitations_0_3"] = ask_scale_0_3("Heart racing / palpitations today?")
    entry["symptoms"]["tremor_0_3"] = ask_scale_0_3("Shaky hands / tremor today?")
    entry["symptoms"]["sweating_0_3"] = ask_scale_0_3("Unusual sweating today?")
    entry["symptoms"]["sleep_trouble_0_3"] = ask_scale_0_3("Trouble falling or staying asleep?")

    # ---- Sulfasalazine adverse effect pattern (including red flags)
    print("\n--- Medication Side Effect Check (Sulfasalazine-focused) ---")
    entry["symptoms"]["nausea_0_3"] = ask_scale_0_3("Nausea today?")
    entry["symptoms"]["abdominal_pain_0_3"] = ask_scale_0_3("Abdominal pain/cramps today?")
    entry["symptoms"]["headache_0_3"] = ask_scale_0_3("Headache today?")
    entry["symptoms"]["mouth_sores_0_3"] = ask_scale_0_3("Mouth ulcers / sore mouth today?")
    entry["symptoms"]["rash_0_3"] = ask_scale_0_3("Rash / itchy skin today?")
    entry["symptoms"]["easy_bruising_0_3"] = ask_scale_0_3("Easy bruising or unusual bleeding today?")
    entry["symptoms"]["sore_throat_0_3"] = ask_scale_0_3("Sore throat today?")
    entry["symptoms"]["fever_yes"] = ask_yes_no("Fever today (or felt feverish/chills)?")
    entry["symptoms"]["jaundice_yes"] = ask_yes_no("Yellow skin/eyes OR very dark urine OR pale stools?")

    # ---- Pregnancy check (kept non-graphic; daily-friendly)
    print("\n--- Pregnancy Check (if relevant) ---")
    entry["symptoms"]["missed_period_yes"] = ask_yes_no("Is your period late/missed right now?")
    entry["symptoms"]["breast_tenderness_0_3"] = ask_scale_0_3("Breast tenderness today?")
    entry["symptoms"]["preg_nausea_0_3"] = ask_scale_0_3("Nausea that feels 'pregnancy-like' today?")
    entry["symptoms"]["frequent_urination_0_3"] = ask_scale_0_3("Needing to pee more often than usual today?")
    entry["symptoms"]["preg_test_positive_yes"] = ask_yes_no("Any positive pregnancy test recently?")

    # ---- Medication adherence (critical for interpretation)
    print("\n--- Medication Adherence (today) ---")
    entry["meds"]["levothyroxine_taken_yes"] = ask_yes_no("Did you take levothyroxine today (or last scheduled dose)?")
    entry["meds"]["levothyroxine_taken_correctly_yes"] = ask_yes_no("Was it taken correctly (empty stomach + away from iron/calcium if applicable)?")
    entry["meds"]["sulfasalazine_taken_yes"] = ask_yes_no("Did you take sulfasalazine today (or last scheduled dose)?")
    entry["meds"]["new_meds_or_dose_change_yes"] = ask_yes_no("Any new medication OR dose change in the last 7 days?")

    # ---- Optional labs (enter if you have them)
    if ask_yes_no("Do you want to enter bloodwork results now?"):
        entry["labs"] = run_labs_module()
    else:
        entry["labs"] = {}

    entry["notes"] = ask_optional_text("Any notes (food, infection exposure, period symptoms, flare triggers, etc.)?")

    return entry

def run_labs_module() -> Dict[str, Any]:
    labs: Dict[str, Any] = {}
    print("\n--- Labs Module (optional) ---")
    print("Enter what you have. Leave blank to skip any item.")

    # RA / inflammation
    labs["CRP"] = ask_optional_float("CRP")
    labs["ESR"] = ask_optional_float("ESR")

    # Thyroid
    labs["TSH"] = ask_optional_float("TSH")
    labs["FreeT4"] = ask_optional_float("Free T4")
    labs["FreeT3"] = ask_optional_float("Free T3")

    # Sulfasalazine safety monitoring
    labs["WBC"] = ask_optional_float("WBC")
    labs["Hemoglobin"] = ask_optional_float("Hemoglobin")
    labs["Platelets"] = ask_optional_float("Platelets")
    labs["ALT"] = ask_optional_float("ALT")
    labs["AST"] = ask_optional_float("AST")
    labs["Creatinine"] = ask_optional_float("Creatinine (optional)")

    # Pregnancy
    labs["hCG"] = ask_optional_float("hCG (if done)")

    # Optional: antibodies if known
    labs["AntiCCP"] = ask_optional_float("Anti-CCP (if known)")
    labs["RF"] = ask_optional_float("Rheumatoid Factor (if known)")

    return labs

# -----------------------------
# Scoring logic (backend nuance)
# -----------------------------
def score_culprits(entry: Dict[str, Any]) -> Tuple[Dict[str, float], List[str]]:
    s = entry["symptoms"]
    meds = entry["meds"]
    labs = entry.get("labs", {}) or {}

    # Red flags to surface immediately (NOT diagnosis; just safety prompts)
    alerts: List[str] = []
    if s.get("jaundice_yes"):
        alerts.append("Possible liver/bile issue (jaundice/dark urine). Contact urgent care/doctor today.")
    if s.get("fever_yes") and s.get("sore_throat_0_3", 0) >= 2:
        alerts.append("Fever + significant sore throat can be concerning for infection or low white count on DMARDs. Contact urgent care/doctor today.")
    if s.get("rash_0_3", 0) >= 3 and s.get("mouth_sores_0_3", 0) >= 2:
        alerts.append("Severe rash + mouth sores can be a serious drug reaction. Seek urgent medical assessment now.")

    # Initialize scores
    scores = {
        "RA": 0.0,
        "Hypothyroidism": 0.0,
        "Sulfasalazine": 0.0,
        "Levothyroxine_Imbalance": 0.0,
        "Pregnancy": 0.0
    }

    # ---- RA scoring: inflammatory pattern + function impact
    stiffness_duration = s.get("morning_stiffness_duration_cat", 0)
    scores["RA"] += 1.5 * s.get("morning_stiffness_level_0_3", 0)
    scores["RA"] += 0.8 * stiffness_duration  # longer duration supports inflammatory activity
    scores["RA"] += 1.2 * s.get("joint_swelling_0_3", 0)
    scores["RA"] += 0.8 * s.get("joint_warmth_0_3", 0)
    scores["RA"] += 0.8 * s.get("rest_stiffness_gelling_0_3", 0)
    scores["RA"] += 1.0 * s.get("fatigue_0_3", 0)
    if s.get("symmetry_yes"):
        scores["RA"] += 1.0
    # Function mini-set (captures daily disability)
    scores["RA"] += 0.6 * (s.get("function_dressing_0_3", 0) + s.get("function_grip_0_3", 0) + s.get("function_walk_0_3", 0))
    # Pain influences but is non-specific
    scores["RA"] += 0.2 * s.get("pain_0_10", 0)

    # Labs support
    if labs.get("CRP") is not None and labs["CRP"] > 5:
        scores["RA"] += 2.0
    if labs.get("ESR") is not None and labs["ESR"] > 20:
        scores["RA"] += 2.0
    if labs.get("AntiCCP") is not None and labs["AntiCCP"] > 20:
        scores["RA"] += 2.0
    if labs.get("RF") is not None and labs["RF"] > 20:
        scores["RA"] += 1.0

    # ---- Hypothyroidism scoring: “slowed down” cluster
    scores["Hypothyroidism"] += 1.2 * s.get("cold_intolerance_0_3", 0)
    scores["Hypothyroidism"] += 1.0 * s.get("constipation_0_3", 0)
    scores["Hypothyroidism"] += 1.2 * s.get("brain_fog_0_3", 0)
    # fatigue overlaps; keep moderate weight
    scores["Hypothyroidism"] += 0.8 * s.get("fatigue_0_3", 0)

    # Labs
    if labs.get("TSH") is not None and labs["TSH"] > 4:
        scores["Hypothyroidism"] += 3.0
    if labs.get("FreeT4") is not None and labs["FreeT4"] < 0.8:
        scores["Hypothyroidism"] += 2.0
    # Adherence signal (missed doses can mimic hypothyroid symptoms over days)
    if not meds.get("levothyroxine_taken_yes", True):
        scores["Hypothyroidism"] += 1.0

    # ---- Levothyroxine imbalance: “revved up” cluster (often over-replacement)
    scores["Levothyroxine_Imbalance"] += 1.5 * s.get("palpitations_0_3", 0)
    scores["Levothyroxine_Imbalance"] += 1.2 * s.get("tremor_0_3", 0)
    scores["Levothyroxine_Imbalance"] += 1.0 * s.get("anxiety_restlessness_0_3", 0)
    scores["Levothyroxine_Imbalance"] += 1.0 * s.get("heat_intolerance_0_3", 0)
    scores["Levothyroxine_Imbalance"] += 0.8 * s.get("sweating_0_3", 0)
    scores["Levothyroxine_Imbalance"] += 0.8 * s.get("sleep_trouble_0_3", 0)
    scores["Levothyroxine_Imbalance"] += 0.6 * s.get("diarrhea_0_3", 0)

    # Labs
    if labs.get("TSH") is not None and labs["TSH"] < 0.4:
        scores["Levothyroxine_Imbalance"] += 3.0
    if labs.get("FreeT4") is not None and labs["FreeT4"] > 1.8:
        scores["Levothyroxine_Imbalance"] += 2.0
    # incorrect intake timing can cause swings / symptoms (not proof; small bump)
    if meds.get("levothyroxine_taken_yes", True) and not meds.get("levothyroxine_taken_correctly_yes", True):
        scores["Levothyroxine_Imbalance"] += 0.5

    # ---- Sulfasalazine: GI + hypersensitivity/infection/cytopenia/liver pattern
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

    # Labs
    if labs.get("WBC") is not None and labs["WBC"] < 4:
        scores["Sulfasalazine"] += 3.0
    if labs.get("Platelets") is not None and labs["Platelets"] < 150:
        scores["Sulfasalazine"] += 2.0
    if labs.get("ALT") is not None and labs["ALT"] > 40:
        scores["Sulfasalazine"] += 2.0
    if labs.get("AST") is not None and labs["AST"] > 40:
        scores["Sulfasalazine"] += 1.5

    # ---- Pregnancy: symptom cluster + test/lab dominance
    pregnancy_signal = 0.0
    if s.get("missed_period_yes"):
        pregnancy_signal += 2.0
    pregnancy_signal += 0.8 * s.get("breast_tenderness_0_3", 0)
    pregnancy_signal += 1.0 * s.get("preg_nausea_0_3", 0)
    pregnancy_signal += 0.6 * s.get("frequent_urination_0_3", 0)
    if s.get("preg_test_positive_yes"):
        pregnancy_signal += 5.0
    if labs.get("hCG") is not None and labs["hCG"] > 25:
        pregnancy_signal += 6.0
    scores["Pregnancy"] += pregnancy_signal

    # Normalize into “likelihood-ish” percentages (softmax)
    probs = softmax(scores)
    return probs, alerts

def softmax(scores: Dict[str, float]) -> Dict[str, float]:
    import math
    vals = list(scores.values())
    m = max(vals)
    exps = {k: math.exp(v - m) for k, v in scores.items()}
    total = sum(exps.values())
    return {k: round((exps[k] / total) * 100.0, 1) for k in scores.keys()}

# -----------------------------
# Persistence + report
# -----------------------------
def append_entry(entry: Dict[str, Any]) -> None:
    with open(DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def print_daily_report(entry: Dict[str, Any], probs: Dict[str, float], alerts: List[str]) -> None:
    print("\n==============================")
    print("Daily Summary")
    print("==============================")
    print(f"Timestamp: {entry['timestamp']}")
    print("\nMost important numbers (today):")
    print(f"  Pain (0-10): {entry['symptoms']['pain_0_10']}")
    print(f"  Overall unwell (0-10): {entry['symptoms']['global_health_0_10']}")
    print(f"  Morning stiffness duration category: {entry['symptoms']['morning_stiffness_duration_cat']}")

    if alerts:
        print("\n⚠️ Alerts to take seriously:")
        for a in alerts:
            print(f"  - {a}")

    print("\nCULPRITS likelihood estimate (not a diagnosis):")
    # Sort descending
    for k, v in sorted(probs.items(), key=lambda x: x[1], reverse=True):
        print(f"  {k}: {v}%")

    top = max(probs, key=probs.get)
    print(f"\nTop signal today: {top}")

    if entry.get("labs"):
        print("\nLabs recorded today:")
        for k, v in entry["labs"].items():
            if v is not None:
                print(f"  {k}: {v}")

    if entry.get("notes"):
        print("\nNotes:")
        print(f"  {entry['notes']}")

    print("\nSaved to log:", os.path.abspath(DATA_FILE))
    print("Tip: Fill this 1–3x/day at consistent times (wake / mid-day / evening).")

# -----------------------------
# Main
# -----------------------------
def main():
    entry = run_daily_survey()
    probs, alerts = score_culprits(entry)
    entry["analysis"] = {"culprit_probabilities_percent": probs, "alerts": alerts}
    append_entry(entry)
    print_daily_report(entry, probs, alerts)

if __name__ == "__main__":
    main()