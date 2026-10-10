import anthropic
import os


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=api_key)

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
    client = _get_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    parts: list[str] = []
    for block in message.content:
        block_text = getattr(block, "text", None)
        if isinstance(block_text, str) and block_text.strip():
            parts.append(block_text.strip())
    return "\n".join(parts)