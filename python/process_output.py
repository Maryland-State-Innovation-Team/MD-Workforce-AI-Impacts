"""Aggregate task ratings into occupation AI exposure classes and produce charts.

Python port of the former r/process_output.R. Also prints the summary
statistics quoted in the README.
"""
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, PercentFormatter
import pandas as pd

from common import INPUT_DIR, OUTPUT_DIR
from process_bls import BLS_YEAR, load_detailed_occupations

RED = "#C84A35"
PINK = "#EDC5BD"
BLUE = "#3C4586"

LABELS = {
    "high_ai_exposure": "High AI exposure",
    "high_augmentation_potential": "High augmentation potential",
    "low_exposure": "Low exposure",
}
LABEL_COLORS = {
    "High AI exposure": RED,
    "High augmentation potential": PINK,
    "Low exposure": BLUE,
}
CLASSES = list(LABELS)

# Headline cutoff for the share of an occupation's tasks rated >= 3, plus the
# alternative cutoffs reported in the sensitivity table.
EXPOSURE_THRESHOLD = 0.5
SENSITIVITY_THRESHOLDS = [0.5, 0.6, 2 / 3, 0.7, 0.75, 0.8]


def classify(row, threshold=EXPOSURE_THRESHOLD):
    # High AI exposure: at least `threshold` of tasks done at average human level or better by AI
    # High augmentation potential: below that, but 50%+ doable with human assistance
    # Low exposure: otherwise
    if row.pct_average_or_better >= threshold:
        return "high_ai_exposure"
    if row.pct_assisted_or_better >= 0.5:
        return "high_augmentation_potential"
    return "low_exposure"


def style_axes(ax):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.yaxis.grid(True, color="#CCCCCC")
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")


def share_by_class(df, by):
    wide = (df.groupby([by, "label"])["TOT_EMP"].sum()
              .unstack("label").reindex(columns=CLASSES).fillna(0))
    total = wide.sum(axis=1)
    pct = wide.div(total, axis=0).add_suffix("_pct")
    return pd.concat([wide, pct], axis=1).assign(total=total)


def threshold_sensitivity(detailed, agg):
    """Share of employment with high AI exposure under alternative cutoffs.

    Raising the cutoff only moves occupations from high AI exposure to high
    augmentation potential; the low exposure class is unchanged.
    """
    df = detailed.merge(agg.rename(columns={"occupation_title": "OCC_TITLE"}), on="OCC_TITLE")
    total_by_area = df.groupby("AREA_TITLE")["TOT_EMP"].sum()
    rows = []
    for t in SENSITIVITY_THRESHOLDS:
        high = df[df["pct_average_or_better"] >= t]
        share = (high.groupby("AREA_TITLE")["TOT_EMP"].sum() / total_by_area).fillna(0)
        share = share.sort_values(ascending=False)
        rows.append({
            "threshold": round(t, 3),
            "occupations_high_ai_exposure": int((agg["pct_average_or_better"] >= t).sum()),
            "maryland_pct": round(share["Maryland"], 4),
            "maryland_rank": list(share.index).index("Maryland") + 1,
            "all_areas_pct": round(high["TOT_EMP"].sum() / df["TOT_EMP"].sum(), 4),
            "dc_pct": round(share["District of Columbia"], 4),
            "top_5_areas": "; ".join(share.index[:5]),
        })
    return pd.DataFrame(rows)


def main():
    detailed = load_detailed_occupations()

    ratings = pd.read_csv(OUTPUT_DIR / "all_occupation_task_ratings.csv").dropna(subset=["rating"])
    agg = ratings.groupby("occupation_title")["rating"].agg(
        pct_average_or_better=lambda r: (r >= 3).mean(),
        pct_assisted_or_better=lambda r: (r >= 2).mean(),
        mean_rating="mean",
        n_tasks="size",
    ).reset_index()
    agg["label"] = agg.apply(classify, axis=1)

    results_table = agg["label"].value_counts().sort_index().rename_axis("label").reset_index(name="count")
    results_table.to_csv(OUTPUT_DIR / "occupation_results_table.csv", index=False)

    industries = pd.read_csv(INPUT_DIR / "all_occupation_titles_industry.csv")
    merged = (detailed
              .merge(industries.rename(columns={"occupation_title": "OCC_TITLE"}), on="OCC_TITLE")
              .merge(agg.rename(columns={"occupation_title": "OCC_TITLE"}), on="OCC_TITLE"))

    # --- Exposure by state ---
    by_state = share_by_class(merged, "AREA_TITLE").sort_values("high_ai_exposure_pct", ascending=False)
    fig, ax = plt.subplots(figsize=(15, 5))
    colors = [RED if area == "Maryland" else BLUE for area in by_state.index]
    ax.bar(by_state.index, by_state["high_ai_exposure_pct"], color=colors, width=0.9)
    ax.set_xlim(-0.6, len(by_state) - 0.4)
    ax.set_ylim(0, by_state["high_ai_exposure_pct"].max() * 1.1)
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_ylabel("Percent of workforce")
    ax.set_title("Workforce with high AI exposure", loc="left")
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "exposure_by_state.png", dpi=300)
    plt.close(fig)

    # --- Top 15 Maryland occupations ---
    md = merged[merged["AREA_TITLE"] == "Maryland"].copy()
    md["label_name"] = md["label"].map(LABELS)
    top = md.sort_values("TOT_EMP", ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(15, 5))
    names = [textwrap.fill(t, 30) for t in top["OCC_TITLE"]]
    ax.bar(names, top["TOT_EMP"], color=top["label_name"].map(LABEL_COLORS), width=0.9)
    ax.set_xlim(-0.6, len(top) - 0.4)
    ax.set_ylim(0, top["TOT_EMP"].max() * 1.1)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylabel("Total employees")
    ax.set_title(f"Top 15 occupations in Maryland by AI exposure ({BLS_YEAR})", loc="left")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in LABEL_COLORS.values()]
    fig.legend(handles, LABEL_COLORS.keys(), loc="lower center", ncol=3, frameon=False)
    style_axes(ax)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(OUTPUT_DIR / "md_top_occupations.png", dpi=300)
    plt.close(fig)

    # --- Maryland lighthouse industries ---
    md["industry"] = md["industry_classification"].replace("None of the above", "All other industries")
    by_ind = share_by_class(md, "industry")
    by_ind = by_ind.assign(_other=by_ind.index == "All other industries").sort_values(
        ["_other", "high_ai_exposure_pct"], ascending=[True, False])
    fig, ax = plt.subplots(figsize=(8, 5))
    bottom = pd.Series(0.0, index=by_ind.index)
    for cls in reversed(CLASSES):  # low exposure at the bottom, high exposure on top
        name = LABELS[cls]
        ax.bar(by_ind.index, by_ind[f"{cls}_pct"], bottom=bottom, color=LABEL_COLORS[name], label=name, width=0.9)
        bottom += by_ind[f"{cls}_pct"]
    ax.set_xlim(-0.6, len(by_ind) - 0.4)
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_ylabel("Percent of current workforce\nin lighthouse industry")
    ax.set_title("Maryland lighthouse industries by AI exposure class", loc="left")
    h, l = ax.get_legend_handles_labels()
    fig.legend(h[::-1], l[::-1], loc="lower center", ncol=3, frameon=False)
    style_axes(ax)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(OUTPUT_DIR / "md_by_industry.png", dpi=300)
    plt.close(fig)

    sensitivity = threshold_sensitivity(detailed, agg)
    sensitivity.to_csv(OUTPUT_DIR / "threshold_sensitivity.csv", index=False)

    # --- Summary statistics for the README ---
    pd.set_option("display.width", 200, "display.max_colwidth", 80, "display.max_rows", 100)
    print(f"Occupation titles: {ratings['occupation_title'].nunique()}, tasks rated: {len(ratings)}")
    print("\nRating distribution:\n", ratings["rating"].value_counts().sort_index().to_string())
    print("\nOccupation classes:\n", results_table.to_string(index=False))
    print("\nTop 10 occupations by mean task rating:")
    print(agg.sort_values("mean_rating", ascending=False).head(10)[["occupation_title", "mean_rating", "label"]].to_string(index=False))
    print("\nOccupations with mean rating of 1:")
    print("\n".join(agg.loc[agg["mean_rating"] == 1, "occupation_title"]))
    print("\nHigh AI exposure share by area (top 10):")
    print(by_state["high_ai_exposure_pct"].head(10).map("{:.1%}".format).to_string())
    print(f"Maryland rank: {list(by_state.index).index('Maryland') + 1} of {len(by_state)}")
    print("\nMaryland top 15 occupations:")
    print(top[["OCC_TITLE", "TOT_EMP", "label", "pct_average_or_better"]].to_string(index=False))
    print("\nOccupations per lighthouse industry:")
    print(industries["industry_classification"].value_counts().to_string())
    print("\nMaryland lighthouse industry shares:")
    print(by_ind[[f"{c}_pct" for c in CLASSES]].map("{:.1%}".format).to_string())
    print("\nThreshold sensitivity (share of tasks rated >= 3 needed for high AI exposure):")
    print(sensitivity.to_string(index=False))


if __name__ == "__main__":
    main()
