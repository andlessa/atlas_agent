from datetime import datetime
from scrape_atlas import fetch_new_papers, get_arxiv_pdf_text, load_seen, save_seen
from summarize import summarize_paper
import pathlib, json

def run_agent():
    print(f"\n[{datetime.now():%Y-%m-%d %H:%M}] Running ATLAS agent...")
    seen = load_seen()
    papers = fetch_new_papers(seen)

    if not papers:
        print("No new papers found.")
        return

    output_lines = [f"# ATLAS digest — {datetime.now():%Y-%m-%d}\n"]

    for paper in papers:
        print(f"  Processing: {paper['title']}")
        text = get_arxiv_pdf_text(paper["link"])
        if not text:
            continue

        summary = summarize_paper(paper["title"], text)
        output_lines.append(f"## [{paper['group']}] {paper['title']}")
        output_lines.append(summary)
        output_lines.append("")

        seen.add(paper["id"])

    digest = "\n".join(output_lines)
    out_path = pathlib.Path(f"digest_{datetime.now():%Y%m%d}.md")
    out_path.write_text(digest)
    print(f"Digest saved to {out_path}")
    save_seen(seen)


import schedule, time

schedule.every().day.at("08:00").do(run_agent)

if __name__ == "__main__":
    run_agent()          # run once immediately on start
    while True:
        schedule.run_pending()
        time.sleep(60)    