import json
import re
from bs4 import BeautifulSoup

def clean_html(html):
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Remove iframes (video embeds, code playgrounds)
    for tag in soup.find_all("iframe"):
        tag.decompose()

    # Remove style/script tags
    for tag in soup.find_all(["style", "script"]):
        tag.decompose()

    # Convert <pre> blocks to preserve formatting
    for pre in soup.find_all("pre"):
        pre.string = "\n" + pre.get_text() + "\n"

    # Convert <code> to backticks
    for code in soup.find_all("code"):
        code.string = f"`{code.get_text()}`"

    # Get text
    text = soup.get_text()

    # Clean up whitespace
    text = re.sub(r"\xa0", " ", text)         # &nbsp;
    text = re.sub(r"\n{3,}", "\n\n", text)    # collapse multiple newlines
    text = re.sub(r"[ \t]+\n", "\n", text)    # trailing whitespace
    text = re.sub(r"\n[ \t]+", "\n", text)    # leading whitespace on lines
    text = text.strip()

    # Remove [TOC] markers
    text = text.replace("[TOC]", "").strip()

    # Remove LaTeX $$ markers, keep the content
    text = re.sub(r"\$\$(.*?)\$\$", r"\1", text)

    return text


if __name__ == "__main__":
    with open("data/core/problems.json") as f:
        problems = json.load(f)

    print(f"Cleaning {len(problems)} problems...")

    for p in problems:
        p["content_clean"] = clean_html(p["content"])
        p["solution_clean"] = clean_html(p["solution"])

    with open("data/core/problems.json", "w") as f:
        json.dump(problems, f, indent=2)

    # Stats
    with_content = sum(1 for p in problems if p["content_clean"])
    with_solution = sum(1 for p in problems if p["solution_clean"])
    print(f"With content: {with_content}")
    print(f"With solution: {with_solution}")

    # Preview
    sample = next(p for p in problems if p["slug"] == "two-sum")
    print("\n=== CLEANED CONTENT ===")
    print(sample["content_clean"][:500])
    print("\n=== CLEANED SOLUTION ===")
    print(sample["solution_clean"][:500])
