import anthropic

client = anthropic.Anthropic(api_key="YOUR_API_KEY")

def summarize_paper(title: str, text: str) -> str:
    prompt = f"""You are a particle physics analyst. Read the following excerpt from an ATLAS paper and extract:
1. The final state investigated (e.g. "two leptons + missing energy")
2. The physics models tested (e.g. "RPV SUSY, gravitino LSP, ADD large extra dimensions")
3. One sentence on the main result or exclusion limit

Paper title: {title}

Paper text:
{text}

Respond in this exact format:
Final state: ...
Models tested: ...
Key result: ...
"""
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text