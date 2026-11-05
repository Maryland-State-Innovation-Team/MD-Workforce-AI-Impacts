"""Export Maryland occupation AI exposure labels.

Writes output/md_occupation_ai_exposure.csv with two columns:
  Occupation, MD State Innovation Team Assessment

Occupation names are BLS titles, except for a few shortened names (see
SHORT_TITLES) so the export can be joined directly to an existing table.
"""
import pandas as pd

from common import OUTPUT_DIR
from process_bls import load_detailed_occupations

ASSESSMENT_COLUMN = "MD State Innovation Team Assessment"

DISPLAY_LABELS = {
    "high_ai_exposure": "High AI Exposure",
    "high_augmentation_potential": "High Augmentation Potential",
    "low_exposure": "Low Exposure",
}

# BLS title -> shortened name used in the export (matched on title and
# Maryland 2025 employment).
SHORT_TITLES = {
    "Sales Representatives of Services, Except Advertising, Insurance, Financial Services, and Travel":
        "Sales Representatives of Services",
    "Secretaries and Administrative Assistants, Except Legal, Medical, and Executive":
        "Secretaries and Administrative Assistants",
    "First-Line Supervisors of Office and Administrative Support Workers":
        "First-Line Supervisors of Office/Administrative Support Workers",
}


def occupation_labels():
    """Return BLS occupation titles with their exposure class, from the task ratings."""
    from process_output import classify  # reuse the exact classification rule

    ratings = pd.read_csv(OUTPUT_DIR / "all_occupation_task_ratings.csv").dropna(subset=["rating"])
    agg = ratings.groupby("occupation_title")["rating"].agg(
        pct_average_or_better=lambda r: (r >= 3).mean(),
        pct_assisted_or_better=lambda r: (r >= 2).mean(),
    ).reset_index()
    agg["label"] = agg.apply(classify, axis=1)
    return agg[["occupation_title", "label"]]


def main():
    labels = occupation_labels()
    md = load_detailed_occupations().query("AREA_TITLE == 'Maryland'")[["OCC_TITLE"]]
    md = md.merge(labels, left_on="OCC_TITLE", right_on="occupation_title", how="left")
    missing = md[md["label"].isna()]
    if len(missing):
        print(f"WARNING: {len(missing)} Maryland occupations have no rating: {missing['OCC_TITLE'].tolist()}")
        md = md.dropna(subset=["label"])

    export = pd.DataFrame({
        "Occupation": md["OCC_TITLE"].replace(SHORT_TITLES),
        ASSESSMENT_COLUMN: md["label"].map(DISPLAY_LABELS),
    }).sort_values("Occupation").reset_index(drop=True)
    csv_filepath = OUTPUT_DIR / "md_occupation_ai_exposure.csv"
    export.to_csv(csv_filepath, index=False)
    print(f"{len(export)} Maryland occupations saved to {csv_filepath}")
    print("\nAll Maryland occupations:\n" + export[ASSESSMENT_COLUMN].value_counts().to_string())


if __name__ == "__main__":
    main()
