"""Extract unique detailed occupation titles from the BLS state OEWS workbook.

Python port of the former r/process_bls.R.
"""
import pandas as pd

from common import INPUT_DIR

# BLS May 2025 State Occupational Employment and Wage Estimates
# https://www.bls.gov/oes/special-requests/oesm25st.zip
BLS_YEAR = 2025
BLS_FILE = INPUT_DIR / "state_M2025_dl.xlsx"
BLS_NA_VALUES = ["", "*", "**", "#"]


def load_detailed_occupations():
    dat = pd.read_excel(BLS_FILE, na_values=BLS_NA_VALUES, keep_default_na=False)
    return dat[dat["O_GROUP"] == "detailed"].copy()


def main():
    detailed = load_detailed_occupations()
    titles = pd.DataFrame({"occupation_title": detailed["OCC_TITLE"].drop_duplicates()})
    csv_filepath = INPUT_DIR / "all_occupation_titles.csv"
    titles.to_csv(csv_filepath, index=False)
    print(f"{len(titles)} occupation titles saved to {csv_filepath}")


if __name__ == "__main__":
    main()
