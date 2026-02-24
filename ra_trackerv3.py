import json
import os
import datetime
from typing import Dict, Any, Optional, List, Tuple

DATA_FILE = "culprits_daily_log.jsonl"

SCALE_0_3 = {
    0: "None",
    1: "Mild (noticeable, doesn’t limit activity)",
    2: "Moderate (limits some activity / needs adjustments)",
    3: "Severe (stops activities / you’re miserable)"
}

TIME_OF_DAY_OPTIONS = ["Morning", "Midday", "Evening", "Night", "Custom"]

def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")

# -----------------------------
# Input helpers
# -----------------------------
def ask_yes_no(prompt: str) -> bool:
    while True:
        raw = input(f"{prompt} (y/n): ").strip().lower()
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Please enter y or n.")

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

def ask_optional_float(prompt: str) -> Optional[float]:
    raw = input(f"{prompt} (press Enter to skip): ").strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        print("Invalid number. Skipping.")
        return None

def ask_optional_text(prompt: str) -> Optional[str]:
    raw = input(f"{prompt} (press Enter to skip): ").strip()
    return raw if raw else None

def ask_choice(prompt: str, options: List[str]) -> str:
    while True:
        print(f"\n{prompt}")
        for i, opt in enumerate(options, start=1):
            print(f"  {i}. {opt}")
        raw = input(f"Choose 1-{len(options)}: ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        print("Invalid selection.")

# -----------------------------
# Questionnaire engine with edit
# -----------------------------
class Question:
    def __init__(self, key: str, label: str, qtype: str, extra: Any = None):
        self.key = key
        self.label = label
        self.qtype = qtype  # "yn", "0_3", "0_10", "choice", "text", "float_opt"
        self.extra = extra  # options, etc.

def ask_question(q: Question):
    if q.qtype == "yn":
        return ask_yes_no(q.label)
    if q.qtype == "0_3":
        return ask_scale_0_3(q.label)
    if q.qtype == "0_10":
        return ask_scale_0_10(q.label)
    if q.qtype == "choice":
        return ask_choice(q.label, q.extra)
    if q.qtype == "text":
        return ask_optional_text(q.label)
    if q.qtype == "float_opt":
        return ask_optional_float(q.label)
    raise ValueError(f"Unknown question type: {q.qtype}")

def pretty_value(v: Any) -> str:
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if v is None:
        return "(blank)"
    return str(v)

def review_and_edit(flat_answers: Dict[str, Any], questions: List[Question]) -> Dict[str, Any]:
    key_to_question = {q.key: q for q in questions}

    while True:
        print("\n==============================")
        print("Review Your Answers")
        print("==============================")
        numbered_keys = []
        for i, q in enumerate(questions, start=1):
            if q.key in flat_answers:
                numbered_keys.append(q.key)
                print(f"{i}. {q.label} -> {pretty_value(flat_answers[q.key])}")

        print("\nOptions:")
        print("  E = Edit an answer")
        print("  S = Save (confirm)")
        print("  Q = Quit without saving")

        choice = input("Choose E/S/Q: ").strip().lower()
        if choice == "q":
            raise SystemExit("Exited without saving.")
        if choice == "s":
            return flat_answers
        if choice == "e":
            raw = input("Enter the question number to edit: ").strip()
            if not raw.isdigit():
                print("Please enter a number.")
                continue
            idx = int(raw)
            if not (1 <= idx <= len(questions)):
                print("Out of range.")
                continue
            q = questions[idx - 1]
            if q.key not in flat_answers:
                print("That item was skipped/not asked today.")
                continue
            print(f"\nEditing: {q.label}")
            flat_answers[q.key] = ask_question(q)
        else:
            print("Invalid choice.")

# -----------------------------
# Labs module
# -----------------------------
def run_labs_module() -> Dict[str, Any]:
    labs: Dict[str, Any] = {}
    print("\n--- Labs Module (optional) ---")
    print("Enter what you have. Leave blank to skip any item.\n")

    labs["CRP"] = ask_optional_float("CRP")
    labs["ESR"] = ask_optional_float("ESR")

    labs["TSH"] = ask_optional_float("TSH")
    labs["FreeT4"] = ask_optional_float("Free T4")
    labs["FreeT3"] = ask_optional_float("Free T3")

    labs["WBC"] = ask_optional_float("WBC")
    labs["Hemoglobin"] = ask_optional_float("Hemoglobin")
    labs["Platelets"] = ask_optional_float("Platelets")
    labs["ALT"] = ask_optional_float("ALT")
    labs["AST"] = ask_optional_float("AST")

    labs["hCG"] = ask_optional_float("hCG (if done)")
    labs["AntiCCP"] = ask_optional_float("Anti-CCP (if known)")
    labs["RF"] = ask_optional_float("Rheumatoid Factor (if known)")

    return labs

# -----------------------------
# Period tracker overlay (optional)
# -----------------------------
def run_cycle_overlay() -> Dict[str, Any]:
    cycle: Dict[str, Any] = {}
    print("\n--- Period / Cycle Overlay (optional) ---")
    cycle["currently_bleeding_yes"] = ask_yes_no("Currently bleeding (period) today?")
    cycle["period_day_number"] = ask_optional_float("If bleeding: which day of period is it? (1,2,3...)")
    cycle["cycle_day_number"] = ask_optional_float("Cycle day number (Day 1 = first day of bleeding), if known")
    cycle["ovulation_test_positive_yes"] = ask_yes_no("Ovulation/LH test positive in last 48 hours?")
    cycle["ovulation_symptoms_0_3"] = ask_scale_0_3("Ovulation-type symptoms today (one-sided pelvic ache, egg-white discharge, etc.)?")
    cycle["pms_symptoms_0_3"] = ask_scale_0_3("PMS-type symptoms today (cramps, mood, bloating, etc.)?")
    return cycle

# -----------------------------
# Scoring logic (same philosophy, refined)
# -----------------------------
def softmax(scores: Dict[str, float]) -> Dict[str, float]:
    import math
    m = max(scores.values())
    exps = {k: math.exp(v - m) for k, v in scores.items()}
    total = sum(exps.values())
    return {k: round((exps[k] / total) * 100.0, 1) for k in scores.keys()}

def score_culprits(entry: Dict[str, Any]) -> Tuple[Dict[str, float], List[str]]:
    s = entry["symptoms"]
    meds = entry["meds"]
    labs = entry.get("labs", {}) or {}

    alerts: List[str] = []
    # Safety prompts (non-diagnostic)
    if s.get("jaundice_yes"):
        alerts.append("Yellow skin/eyes or dark urine can be serious (especially on meds). Contact urgent care/doctor today.")
    if s.get("fever_yes") and s.get("sore_throat_0_3", 0) >= 2:
        alerts.append("Fever + significant sore throat on DMARDs can be concerning. Contact urgent care/doctor today.")
    if s.get("rash_0_3", 0) >= 3 and s.get("mouth_sores_0_3", 0) >= 2:
        alerts.append("Severe rash + mouth sores can signal a serious drug reaction. Seek urgent assessment now.")
    if s.get("palpitations_0_3", 0) >= 3:
        alerts.append("Severe palpitations: consider urgent assessment, especially if dizzy/chest pain/short of breath.")

    scores = {"RA": 0.0, "Hypothyroidism": 0.0, "Sulfasalazine": 0.0, "Levothyroxine_Imbalance": 0.0, "Pregnancy": 0.0}

    # RA
    scores["RA"] += 1.5 * s.get("morning_stiffness_level_0_3", 0)
    scores["RA"] += 0.8 * s.get("morning_stiffness_duration_cat", 0)
    scores["RA"] += 1.2 * s.get("joint_swelling_0_3", 0)
    scores["RA"] += 0.8 * s.get("joint_warmth_0_3", 0)
    scores["RA"] += 0.8 * s.get("rest_stiffness_gelling_0_3", 0)
    scores["RA"] += 0.6 * (s.get("function_dressing_0_3", 0) + s.get("function_grip_0_3", 0) + s.get("function_walk_0_3", 0))
    if s.get("symmetry_yes"):
        scores["RA"] += 1.0
    scores["RA"] += 0.2 * s.get("pain_0_10", 0)
    if labs.get("CRP") is not None and labs["CRP"] > 5:
        scores["RA"] += 2.0
    if labs.get("ESR") is not None and labs["ESR"] > 20:
        scores["RA"] += 2.0

    # Hypothyroid
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

    # Levo imbalance (often over-replacement pattern)
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
    if meds.get("levothyroxine_taken_yes", True) and not meds.get("levothyroxine_taken_correctly_yes", True):
        scores["Levothyroxine_Imbalance"] += 0.5

    # Sulfasalazine
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

    # Pregnancy (if pregnancy section was skipped, this stays low)
    # We store pregnancy fields only when asked; missing keys will default
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

# -----------------------------
# Main survey flow (with gating + edit)
# -----------------------------
def run_daily_survey() -> Tuple[Dict[str, Any], List[Question], Dict[str, Any]]:
    entry: Dict[str, Any] = {
        "timestamp": now_iso(),
        "time_of_day": None,
        "context": {},
        "symptoms": {},
        "meds": {},
        "labs": {},
        "cycle": {},
        "notes": None,
        "analysis": {}
    }

    # Time-of-day
    tod = ask_choice("Time of day for this entry:", TIME_OF_DAY_OPTIONS)
    if tod == "Custom":
        custom = ask_optional_text("Enter custom time-of-day label (e.g., 'after lunch', 'post-work'):")
        entry["time_of_day"] = custom if custom else "Custom"
    else:
        entry["time_of_day"] = tod

    # Questions list (for review/edit)
    questions: List[Question] = []

    def add(section: Dict[str, Any], q: Question):
        questions.append(q)
        section[q.key] = ask_question(q)

    # Context
    print("\n--- Context (helps interpretation) ---")
    add(entry["context"], Question("sleep_quality_0_3", "How was your sleep quality last night?", "0_3"))
    add(entry["context"], Question("stress_0_3", "How high was your stress in the last 24 hours?", "0_3"))
    add(entry["context"], Question("activity_change_0_3", "Any unusual physical activity compared to your normal?", "0_3"))

    # Core outcomes
    print("\n--- Today Overview ---")
    add(entry["symptoms"], Question("pain_0_10", "Overall pain today", "0_10"))
    add(entry["symptoms"], Question("global_health_0_10", "Overall how unwell do you feel today (0=great, 10=worst)?", "0_10"))

    # Function (daily-friendly)
    print("\n--- Function (quick) ---")
    add(entry["symptoms"], Question("function_dressing_0_3", "Difficulty getting dressed (buttons, socks, etc.)?", "0_3"))
    add(entry["symptoms"], Question("function_grip_0_3", "Difficulty gripping / opening jars / turning knobs?", "0_3"))
    add(entry["symptoms"], Question("function_walk_0_3", "Difficulty walking / stairs because of pain?", "0_3"))

    # RA pattern
    print("\n--- Joint / Inflammation Pattern (RA-focused) ---")
    add(entry["symptoms"], Question("morning_stiffness_level_0_3", "Morning stiffness severity", "0_3"))

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
    questions.append(Question("morning_stiffness_duration_cat", "Morning stiffness duration category", "choice", None))

    add(entry["symptoms"], Question("joint_swelling_0_3", "Visible or felt joint swelling today?", "0_3"))
    add(entry["symptoms"], Question("joint_warmth_0_3", "Warmth/redness over joints today?", "0_3"))
    add(entry["symptoms"], Question("symmetry_yes", "Are BOTH sides affected similarly (both hands/wrists/feet)?", "yn"))
    add(entry["symptoms"], Question("rest_stiffness_gelling_0_3", "Stiffness after sitting/resting (the 'gelling' feeling)?", "0_3"))
    add(entry["symptoms"], Question("fatigue_0_3", "Fatigue / drained feeling today?", "0_3"))

    # Thyroid pattern
    print("\n--- Thyroid Pattern (Hypo vs Over-replacement) ---")
    add(entry["symptoms"], Question("cold_intolerance_0_3", "Feeling unusually cold compared to others?", "0_3"))
    add(entry["symptoms"], Question("heat_intolerance_0_3", "Feeling unusually hot / heat intolerance?", "0_3"))
    add(entry["symptoms"], Question("constipation_0_3", "Constipation today?", "0_3"))
    add(entry["symptoms"], Question("diarrhea_0_3", "Diarrhea today?", "0_3"))
    add(entry["symptoms"], Question("brain_fog_0_3", "Brain fog / slow thinking / forgetful today?", "0_3"))
    add(entry["symptoms"], Question("anxiety_restlessness_0_3", "Anxiety / restlessness today?", "0_3"))
    add(entry["symptoms"], Question("palpitations_0_3", "Heart racing / palpitations today?", "0_3"))
    add(entry["symptoms"], Question("tremor_0_3", "Shaky hands / tremor today?", "0_3"))
    add(entry["symptoms"], Question("sweating_0_3", "Unusual sweating today?", "0_3"))
    add(entry["symptoms"], Question("sleep_trouble_0_3", "Trouble falling or staying asleep?", "0_3"))

    # Sulfasalazine
    print("\n--- Medication Side Effect Check (Sulfasalazine-focused) ---")
    add(entry["symptoms"], Question("nausea_0_3", "Nausea today?", "0_3"))
    add(entry["symptoms"], Question("abdominal_pain_0_3", "Abdominal pain/cramps today?", "0_3"))
    add(entry["symptoms"], Question("headache_0_3", "Headache today?", "0_3"))
    add(entry["symptoms"], Question("mouth_sores_0_3", "Mouth ulcers / sore mouth today?", "0_3"))
    add(entry["symptoms"], Question("rash_0_3", "Rash / itchy skin today?", "0_3"))
    add(entry["symptoms"], Question("easy_bruising_0_3", "Easy bruising or unusual bleeding today?", "0_3"))
    add(entry["symptoms"], Question("sore_throat_0_3", "Sore throat today?", "0_3"))
    add(entry["symptoms"], Question("fever_yes", "Fever today (or felt feverish/chills)?", "yn"))
    add(entry["symptoms"], Question("jaundice_yes", "Yellow skin/eyes OR very dark urine OR pale stools?", "yn"))

    # Pregnancy gating
    print("\n--- Pregnancy Check (if relevant) ---")
    missed_period = ask_yes_no("Is your period late/missed right now?")
    entry["symptoms"]["missed_period_yes"] = missed_period
    questions.append(Question("missed_period_yes", "Is your period late/missed right now?", "yn"))

    preg_test_pos = ask_yes_no("Any positive pregnancy test recently?")
    entry["symptoms"]["preg_test_positive_yes"] = preg_test_pos
    questions.append(Question("preg_test_positive_yes", "Any positive pregnancy test recently?", "yn"))

    if (missed_period is False) and (preg_test_pos is False):
        entry["symptoms"]["preg_section_skipped"] = True
        # Do not ask follow-ups
    else:
        entry["symptoms"]["preg_section_skipped"] = False
        add(entry["symptoms"], Question("breast_tenderness_0_3", "Breast tenderness today?", "0_3"))
        add(entry["symptoms"], Question("preg_nausea_0_3", "Nausea that feels 'pregnancy-like' today?", "0_3"))
        add(entry["symptoms"], Question("frequent_urination_0_3", "Needing to pee more often than usual today?", "0_3"))

    # Med adherence
    print("\n--- Medication Adherence ---")
    add(entry["meds"], Question("levothyroxine_taken_yes", "Did you take levothyroxine today (or last scheduled dose)?", "yn"))
    add(entry["meds"], Question("levothyroxine_taken_correctly_yes", "Was levothyroxine taken correctly (empty stomach + away from iron/calcium if applicable)?", "yn"))
    add(entry["meds"], Question("sulfasalazine_taken_yes", "Did you take sulfasalazine today (or last scheduled dose)?", "yn"))
    add(entry["meds"], Question("new_meds_or_dose_change_yes", "Any new medication OR dose change in the last 7 days?", "yn"))

    # Optional labs
    if ask_yes_no("\nDo you want to enter bloodwork results now?"):
        entry["labs"] = run_labs_module()
    else:
        entry["labs"] = {}

    # Optional cycle overlay
    if ask_yes_no("\nDo you want to add period/cycle info (overlay) today?"):
        entry["cycle"] = run_cycle_overlay()
    else:
        entry["cycle"] = {}

    entry["notes"] = ask_optional_text("\nAny notes (food, infection exposure, triggers, etc.)?")

    # Prepare flat answers for editing
    flat = {}
    # time_of_day is also editable as a field
    flat["time_of_day"] = entry["time_of_day"]

    # Combine entry sections into one flat dict for editing
    for section_name in ["context", "symptoms", "meds"]:
        for k, v in entry[section_name].items():
            flat[k] = v

    # Add edit-capable “time_of_day” question at top
    edit_questions = [Question("time_of_day", "Time of day label", "choice", TIME_OF_DAY_OPTIONS)] + questions

    # Review/edit loop
    edited = review_and_edit(flat, edit_questions)

    # Apply edits back into entry
    entry["time_of_day"] = edited["time_of_day"]
    for k, v in edited.items():
        if k in entry["context"]:
            entry["context"][k] = v
        elif k in entry["symptoms"]:
            entry["symptoms"][k] = v
        elif k in entry["meds"]:
            entry["meds"][k] = v

    return entry

def append_entry(entry: Dict[str, Any]) -> None:
    with open(DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def print_daily_report(entry: Dict[str, Any]) -> None:
    probs = entry["analysis"]["culprit_probabilities_percent"]
    alerts = entry["analysis"]["alerts"]

    print("\n==============================")
    print("Saved Daily Summary")
    print("==============================")
    print(f"Timestamp: {entry['timestamp']}")
    print(f"Time-of-day: {entry['time_of_day']}")
    print(f"Pain (0-10): {entry['symptoms']['pain_0_10']}")
    print(f"Unwell (0-10): {entry['symptoms']['global_health_0_10']}")

    if alerts:
        print("\n⚠️ Alerts:")
        for a in alerts:
            print(f"  - {a}")

    print("\nCULPRITS likelihood estimate (not a diagnosis):")
    for k, v in sorted(probs.items(), key=lambda x: x[1], reverse=True):
        print(f"  {k}: {v}%")

    if entry.get("cycle"):
        print("\nCycle overlay (today):")
        for k, v in entry["cycle"].items():
            print(f"  {k}: {pretty_value(v)}")

    if entry.get("labs"):
        nonempty = {k: v for k, v in entry["labs"].items() if v is not None}
        if nonempty:
            print("\nLabs recorded today:")
            for k, v in nonempty.items():
                print(f"  {k}: {v}")

    if entry.get("notes"):
        print("\nNotes:")
        print(f"  {entry['notes']}")

    print("\nSaved to log:", os.path.abspath(DATA_FILE))

def main():
    print("\n===================================")
    print("CULPRITS Tracker (v3) - Survey First")
    print("===================================")
    print("Tracking tool only. Not medical advice.\n")

    entry = run_daily_survey()
    probs, alerts = score_culprits(entry)
    entry["analysis"] = {"culprit_probabilities_percent": probs, "alerts": alerts}

    append_entry(entry)
    print_daily_report(entry)

if __name__ == "__main__":
    main()