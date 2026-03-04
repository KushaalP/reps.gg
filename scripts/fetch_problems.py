import requests
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

LEETCODE_GRAPHQL = "https://leetcode.com/graphql"
CSRF = os.getenv("LEETCODE_CSRF_TOKEN")
SESSION = os.getenv("LEETCODE_SESSION")

COOKIES = {"csrftoken": CSRF, "LEETCODE_SESSION": SESSION}
HEADERS = {"x-csrftoken": CSRF, "referer": "https://leetcode.com"}


def fetch_problem_list(limit=50, skip=0):
    query = """
    query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int) {
        problemsetQuestionList: questionList(
            categorySlug: $categorySlug
            limit: $limit
            skip: $skip
            filters: {}
        ) {
            total: totalNum
            questions: data {
                questionFrontendId
                title
                titleSlug
                difficulty
                isPaidOnly
                topicTags { name }
                stats
                hints
            }
        }
    }
    """
    resp = requests.post(LEETCODE_GRAPHQL, json={
        "query": query,
        "variables": {"categorySlug": "", "limit": limit, "skip": skip}
    }, cookies=COOKIES, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]["problemsetQuestionList"]


def fetch_problem_detail(title_slug):
    query = """
    query questionDetail($titleSlug: String!) {
        question(titleSlug: $titleSlug) {
            questionFrontendId
            title
            titleSlug
            content
            difficulty
            isPaidOnly
            topicTags { name }
            hints
            stats
            solution {
                content
            }
        }
    }
    """
    resp = requests.post(LEETCODE_GRAPHQL, json={
        "query": query,
        "variables": {"titleSlug": title_slug}
    }, cookies=COOKIES, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]["question"]


def clean_problem(raw):
    stats = json.loads(raw["stats"]) if raw.get("stats") else {}
    return {
        "id": int(raw["questionFrontendId"]),
        "title": raw["title"],
        "slug": raw["titleSlug"],
        "difficulty": raw["difficulty"],
        "paid": raw["isPaidOnly"],
        "topics": [t["name"] for t in (raw.get("topicTags") or [])],
        "hints": raw.get("hints") or [],
        "acceptance_rate": stats.get("acRate"),
        "total_accepted": stats.get("totalAcceptedRaw"),
        "total_submissions": stats.get("totalSubmissionRaw"),
        "content": raw.get("content"),
        "solution": (raw.get("solution") or {}).get("content"),
    }


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)

    # Fetch all slugs first
    print("Fetching problem list...")
    all_questions = []
    skip = 0
    batch_size = 100
    total = None

    while total is None or skip < total:
        result = fetch_problem_list(limit=batch_size, skip=skip)
        if total is None:
            total = result["total"]
            print(f"Total problems: {total}")
        all_questions.extend(result["questions"])
        skip += batch_size
        print(f"  Listed {len(all_questions)}/{total}")

    print(f"\nFetching details for {len(all_questions)} problems...")

    # Load existing progress if resuming
    output_path = "data/problems.json"
    done = {}
    if os.path.exists(output_path):
        with open(output_path) as f:
            existing = json.load(f)
            done = {p["slug"]: p for p in existing}
        print(f"  Resuming — {len(done)} already fetched")

    problems = list(done.values())
    errors = []

    for i, q in enumerate(all_questions):
        slug = q["titleSlug"]
        if slug in done:
            continue

        try:
            detail = fetch_problem_detail(slug)
            problems.append(clean_problem(detail))
            done[slug] = problems[-1]
        except Exception as e:
            print(f"  ERROR [{q['questionFrontendId']}] {q['title']}: {e}")
            errors.append({"slug": slug, "error": str(e)})

        # Save progress every 50 problems
        if len(problems) % 50 == 0:
            problems.sort(key=lambda p: p["id"])
            with open(output_path, "w") as f:
                json.dump(problems, f, indent=2)
            print(f"  Fetched {len(problems)}/{total} (saved checkpoint)")

        time.sleep(0.3)

    # Final save
    problems.sort(key=lambda p: p["id"])
    with open(output_path, "w") as f:
        json.dump(problems, f, indent=2)

    print(f"\nDone. Saved {len(problems)} problems to {output_path}")
    if errors:
        print(f"Errors: {len(errors)}")
        with open("data/fetch_errors.json", "w") as f:
            json.dump(errors, f, indent=2)
