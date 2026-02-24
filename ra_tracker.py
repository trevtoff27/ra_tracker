# ==========================================
# RHEUMATOID ARTHRITIS SYMPTOM TRACKER
# The CULPRITS Tracker
# ==========================================

import datetime

def ask_yes_no(question):
    while True:
        answer = input(question + " (yes/no): ").lower()
        if answer in ["yes", "y"]:
            return 1
        elif answer in ["no", "n"]:
            return 0
        else:
            print("Please answer yes or no.")

def ask_float(question):
    value = input(question + " (or press Enter to skip): ")
    if value == "":
        return None
    try:
        return float(value)
    except:
        print("Invalid input. Skipping.")
        return None


# ==========================================
# 1. RA QUESTIONS
# ==========================================
def assess_ra():
    print("\n--- Rheumatoid Arthritis Symptoms ---")
    score = 0
    
    score += ask_yes_no("Morning stiffness lasting more than 30 minutes?")
    score += ask_yes_no("Symmetrical joint pain?")
    score += ask_yes_no("Joint swelling?")
    score += ask_yes_no("Fatigue?")
    score += ask_yes_no("Low-grade fever?")
    score += ask_yes_no("Worsening hand or wrist pain?")
    
    print("\n--- RA Bloodwork ---")
    crp = ask_float("CRP level")
    esr = ask_float("ESR level")
    anti_ccp = ask_float("Anti-CCP level")
    rf = ask_float("Rheumatoid Factor")

    if crp and crp > 5:
        score += 2
    if esr and esr > 20:
        score += 2
    if anti_ccp and anti_ccp > 20:
        score += 3
    if rf and rf > 20:
        score += 2

    return score


# ==========================================
# 2. HYPOTHYROIDISM QUESTIONS
# ==========================================
def assess_hypothyroid():
    print("\n--- Hypothyroidism Symptoms ---")
    score = 0
    
    score += ask_yes_no("Cold intolerance?")
    score += ask_yes_no("Weight gain?")
    score += ask_yes_no("Constipation?")
    score += ask_yes_no("Dry skin?")
    score += ask_yes_no("Hair thinning?")
    score += ask_yes_no("Depression or low mood?")
    score += ask_yes_no("Bradycardia (slow heart rate)?")

    print("\n--- Thyroid Bloodwork ---")
    tsh = ask_float("TSH level")
    ft4 = ask_float("Free T4 level")
    ft3 = ask_float("Free T3 level")

    if tsh and tsh > 4:
        score += 3
    if ft4 and ft4 < 0.8:
        score += 2

    return score


# ==========================================
# 3. SULFASALAZINE SIDE EFFECTS
# ==========================================
def assess_sulfasalazine():
    print("\n--- Sulfasalazine Side Effects ---")
    score = 0
    
    score += ask_yes_no("Nausea or vomiting?")
    score += ask_yes_no("Headache?")
    score += ask_yes_no("Rash?")
    score += ask_yes_no("Mouth ulcers?")
    score += ask_yes_no("Easy bruising?")
    score += ask_yes_no("Yellowing of skin or eyes?")

    print("\n--- Sulfasalazine Bloodwork ---")
    wbc = ask_float("White blood cell count")
    alt = ask_float("ALT level")
    platelets = ask_float("Platelet count")

    if wbc and wbc < 4:
        score += 3
    if alt and alt > 40:
        score += 2
    if platelets and platelets < 150:
        score += 2

    return score


# ==========================================
# 4. LEVOTHYROXINE OVER-REPLACEMENT
# ==========================================
def assess_levothyroxine():
    print("\n--- Levothyroxine Over/Under Replacement ---")
    score = 0
    
    score += ask_yes_no("Heart palpitations?")
    score += ask_yes_no("Anxiety?")
    score += ask_yes_no("Tremors?")
    score += ask_yes_no("Unintentional weight loss?")
    score += ask_yes_no("Insomnia?")

    print("\n--- Thyroid Bloodwork ---")
    tsh = ask_float("TSH level")
    ft4 = ask_float("Free T4 level")

    if tsh and tsh < 0.4:
        score += 3
    if ft4 and ft4 > 1.8:
        score += 2

    return score


# ==========================================
# 5. PREGNANCY
# ==========================================
def assess_pregnancy():
    print("\n--- Pregnancy Symptoms ---")
    score = 0
    
    score += ask_yes_no("Missed period?")
    score += ask_yes_no("Breast tenderness?")
    score += ask_yes_no("Nausea?")
    score += ask_yes_no("Fatigue?")
    score += ask_yes_no("Frequent urination?")

    print("\n--- Pregnancy Bloodwork ---")
    hcg = ask_float("hCG level")

    if hcg and hcg > 25:
        score += 5

    return score


# ==========================================
# INTERPRET RESULTS
# ==========================================
def interpret_scores(scores):
    print("\n==============================")
    print("CULPRITS ANALYSIS REPORT")
    print("==============================\n")

    for culprit, score in scores.items():
        print(f"{culprit} score: {score}")

    likely = max(scores, key=scores.get)
    print(f"\nMost likely contributor today: {likely}")

    print("\nNOTE: This tool supplements medical care. Always consult your physician.")


# ==========================================
# MAIN
# ==========================================
def main():
    print("===================================")
    print("RHEUMATOID ARTHRITIS CULPRITS TRACKER")
    print("===================================")
    print("Date:", datetime.datetime.now())

    scores = {}
    scores["Rheumatoid Arthritis"] = assess_ra()
    scores["Hypothyroidism"] = assess_hypothyroid()
    scores["Sulfasalazine Side Effects"] = assess_sulfasalazine()
    scores["Levothyroxine Imbalance"] = assess_levothyroxine()
    scores["Pregnancy"] = assess_pregnancy()

    interpret_scores(scores)


if __name__ == "__main__":
    main()