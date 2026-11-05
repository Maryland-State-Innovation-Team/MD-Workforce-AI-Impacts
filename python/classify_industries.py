import argparse
from typing import Literal

import pandas as pd
from pydantic import BaseModel

from common import INPUT_DIR, add_common_args, get_client, query_many

lighthouse_industries = [
    'Aerospace and Defense',
    'Artificial Intelligence',
    'Bio-tech',
    'Clean Energy',
    'Life Sciences',
    'Quantum Computing',
    'Information Technology',
    'None of the above'
]

SYSTEM_PROMPT = (
    "For the cross-industry occupation title given by the user, classify it into the industry category it most closely fits into. "
    "The industry categories are:\n{}\n"
    "If the occupation title does not closely fit into any of the categories, choose 'None of the above'. "
    "Please respond only with valid JSON in the specified format."
).format("\n".join(f'- {value}' for value in lighthouse_industries))


class Classification(BaseModel):
    classification: Literal[tuple(lighthouse_industries)]


def main():
    parser = argparse.ArgumentParser(description='Classify occupations into lighthouse industries')
    args = add_common_args(parser).parse_args()
    client = get_client(args.model)

    input_occupations = pd.read_csv(INPUT_DIR / 'all_occupation_titles.csv')['occupation_title'].tolist()
    responses = query_many(args.model, client, SYSTEM_PROMPT, input_occupations, Classification,
                           workers=args.workers, desc="Classifying")

    failed = [occ for occ, resp in zip(input_occupations, responses) if resp is None]
    if failed:
        print(f"WARNING: {len(failed)} occupations could not be classified: {failed}")

    df = pd.DataFrame({
        'occupation_title': input_occupations,
        'industry_classification': [resp['classification'] if resp else None for resp in responses],
    })
    csv_filepath = INPUT_DIR / "all_occupation_titles_industry.csv"
    df.to_csv(csv_filepath, index=False)
    print(f"Data saved to {csv_filepath}")


if __name__ == '__main__':
    main()
