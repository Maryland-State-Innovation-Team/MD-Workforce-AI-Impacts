import argparse

import pandas as pd
from pydantic import BaseModel

from common import INPUT_DIR, add_common_args, get_client, query_many

SYSTEM_PROMPT = (
    "For the cross-industry occupation title given by the user, please enumerate a full list of reasonable tasks that a person "
    "in that occupation would need to perform on a daily basis. Consider the entire spectrum of that individual's "
    "duties and responsibilities, both online (if applicable) and in person, in formulating the tasks. "
    "Please respond only with valid JSON in the specified format."
)


class EnumeratedTasks(BaseModel):
    tasks: list[str]


def main():
    parser = argparse.ArgumentParser(description='Generate occupation tasks')
    args = add_common_args(parser).parse_args()
    client = get_client(args.model)

    input_occupations = pd.read_csv(INPUT_DIR / 'all_occupation_titles.csv')['occupation_title'].tolist()
    responses = query_many(args.model, client, SYSTEM_PROMPT, input_occupations, EnumeratedTasks,
                           workers=args.workers, desc="Generating tasks")

    output_records = []
    failed = []
    for occupation, resp in zip(input_occupations, responses):
        if resp is None:
            failed.append(occupation)
            continue
        output_records.extend({'occupation_title': occupation, 'task': task} for task in resp['tasks'])
    if failed:
        print(f"WARNING: {len(failed)} occupations returned no tasks: {failed}")

    df = pd.DataFrame.from_records(output_records)
    csv_filepath = INPUT_DIR / "all_occupation_tasks.csv"
    df.to_csv(csv_filepath, index=False)
    print(f"Data saved to {csv_filepath}")


if __name__ == '__main__':
    main()
