from datetime import datetime

import anthropic
from scrape_atlas import fetch_new_papers, get_arxiv_pdf_text, load_seen, save_seen
from summarize import summarize_paper
import os, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pathlib, json

def send_email(subject: str, body: str):
    sender   = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ.get("RECIPIENT_EMAIL", sender)  # defaults to sending to yourself

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = recipient

    # Plain-text version
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())

def run_agent():
    print(f"\n[{datetime.now():%Y-%m-%d %H:%M}] Running ATLAS agent...")
    seen  = load_seen()
    papers = fetch_new_papers(seen)

    if not papers:
        print("No new papers found.")
        return  # no email sent on quiet days — avoids inbox noise

    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"# ATLAS digest — {today}\n"]

    for paper in papers:
        print(f"  Processing: {paper['title']}")
        text = get_arxiv_pdf_text(paper["link"])
        if not text:
            continue

        summary = summarize_paper(paper["title"], text)
        lines.append(f"## [{paper['group']}] {paper['title']}")
        lines.append(f"Link: {paper['link']}")
        lines.append(summary)
        lines.append("")
        seen.add(paper["id"])

    digest = "\n".join(lines)

    # 1. Save to repo
    out_dir = pathlib.Path("digests")
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"{today}.md").write_text(digest)
    print(f"Saved digests/{today}.md")

    # 2. Send email
    send_email(
        subject=f"ATLAS digest {today} — {len(papers)} new paper(s)",
        body=digest,
    )
    print("Email sent.")

    save_seen(seen)

## Only if running locally:
#import schedule, time
#schedule.every().day.at("08:00").do(run_agent)

if __name__ == "__main__":
    import os
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    run_agent()
#    while True:
#        schedule.run_pending()
#        time.sleep(60)    