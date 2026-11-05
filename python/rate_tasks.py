import argparse

import pandas as pd
from pydantic import BaseModel, Field

from common import INPUT_DIR, OUTPUT_DIR, add_common_args, get_client, query_many

# Grounding paragraph summarizing published evidence on agentic AI capabilities.
# Sources are listed in the README "References" section; update both together.
CAPABILITY_CONTEXT = (
    "Capability context (as of November 2026): AI agents can now autonomously carry out many well-specified digital tasks, "
    "such as coding, data analysis, document drafting, research synthesis, and routine software operation, often at or near "
    "the quality of experienced professionals. Independent measurements from early 2026 show frontier agents completing "
    "software tasks that take human experts roughly 6-12 hours with 50% reliability, but only about 1-3 hours with 80% "
    "reliability; this horizon has doubled roughly every four months since 2023. Reliability drops as tasks become longer, "
    "more open-ended, or less clearly specified. On real end-to-end freelance projects, the best agents produce "
    "client-acceptable work for only about one in five projects, and on long multi-application computer workflows they fully "
    "succeed about 20% of the time. Agents still miss implicit standards, make unflagged errors, and generally need human "
    "review. Tasks that require legal accountability, professional licensure, sustained interpersonal trust, or emotional "
    "care remain mainly human. Physical automation is growing but concentrated in structured settings: factory and "
    "warehouse robots, robot-assisted surgery, and driverless taxis in a few U.S. cities. General-purpose humanoid robots "
    "remain at pilot scale, and most tasks needing dexterous manipulation in unstructured environments cannot yet be "
    "performed by robots."
)

SYSTEM_PROMPT = (
    "For the cross-industry occupation title and specific task given by the user, rate the task's exposure to AI automation from 1-5. "
    "The ratings have the following interpretations:\n"
    "- 1: AI cannot perform the task at all\n"
    "- 2: AI can perform the task with assistance from a human operator\n"
    "- 3: AI can perform the task as well as an average human\n"
    "- 4: AI can perform the task as well as an expert human\n"
    "- 5: AI can perform the task better than an expert human\n"
    "Consider the entire spectrum of that occupation's duties and responsibilities, both online (if applicable) and in person, in formulating the ratings. "
    "Also consider the legal, physical, and emotional requirements of the task. Most tasks that require a physical presence should be rated 1; "
    "rate a physical task 2 only if robots already perform it in comparable structured real-world settings. "
    "Base your rating on the current state of AI described below rather than on assumptions about earlier or future systems.\n\n"
    f"{CAPABILITY_CONTEXT}\n\n"
    "Please respond only with valid JSON in the specified format."
)


class TaskRating(BaseModel):
    rating: int = Field(ge=1, le=5)


def main():
    parser = argparse.ArgumentParser(description='Rate occupation tasks')
    args = add_common_args(parser).parse_args()
    client = get_client(args.model)

    tasks_df = pd.read_csv(INPUT_DIR / 'all_occupation_tasks.csv')
    user_contents = [f"{occ} - {task}" for occ, task in zip(tasks_df['occupation_title'], tasks_df['task'])]
    responses = query_many(args.model, client, SYSTEM_PROMPT, user_contents, TaskRating,
                           workers=args.workers, desc="Rating tasks")

    tasks_df['rating'] = [resp['rating'] if resp else None for resp in responses]
    n_failed = int(tasks_df['rating'].isna().sum())
    if n_failed:
        print(f"WARNING: {n_failed} tasks could not be rated and are left blank.")
    tasks_df['rating'] = tasks_df['rating'].astype('Int64')

    csv_filepath = OUTPUT_DIR / "all_occupation_task_ratings.csv"
    tasks_df.to_csv(csv_filepath, index=False)
    print(f"Data saved to {csv_filepath}")


if __name__ == '__main__':
    main()
