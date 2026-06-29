"""Job #4 — Q&A over client documents.

Paste a statement's text (or upload a PDF) and ask questions about it. Claude
answers using only the document, citing figures, and says so when the answer
isn't there. This is the one job where Claude reads source material directly
rather than working from numbers the engine computed.
"""

import os

from .agent import MODEL

DOCQA_SYSTEM = """\
You are a financial planning assistant helping an advisor. Answer the question \
using ONLY the provided client document(s). Cite the specific figures or lines \
you used. If the answer is not in the document, say so plainly — do not guess \
or fill in from general knowledge. Be concise and concrete. This is for advisor \
review, not personalized investment advice."""


def answer_question(question, doc_text=None, pdf_b64=None) -> str:
    """Ask Claude a question grounded in a pasted text and/or an uploaded PDF."""
    if not (doc_text or pdf_b64):
        raise ValueError("Provide a document — paste text or upload a PDF.")
    if not question or not question.strip():
        raise ValueError("Ask a question about the document.")

    import anthropic
    from dotenv import load_dotenv

    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Open .env and paste your key, "
            "or run: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    content = []
    if pdf_b64:
        content.append({
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
        })
    if doc_text:
        content.append({"type": "text", "text": "CLIENT DOCUMENT:\n" + doc_text})
    content.append({"type": "text", "text": "QUESTION: " + question})

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        thinking={"type": "adaptive"},
        system=DOCQA_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(b.text for b in response.content if b.type == "text")
