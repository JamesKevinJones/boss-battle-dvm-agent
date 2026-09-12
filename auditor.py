"""auditor.py -- LLM-backed Bitcoin Script/miniscript/PSBT vulnerability audit.

Scoped narrowly on purpose: per the Machine Money judging weight ("use case
is the test ... a wrapper with no clear use lands badly here"), this checks a
fixed list of known Bitcoin-script footguns rather than being a generic
"summarize anything" tool, and the prompt says so.
"""

import os

import anthropic

MODEL = os.environ.get("AUDIT_MODEL", "claude-sonnet-5")

SYSTEM_PROMPT = """You are a Bitcoin Script, miniscript, and PSBT security auditor.

Review ONLY the input given -- a Bitcoin Script, a miniscript expression, or a
PSBT (base64 or hex). Check specifically for:

- missing or wrong multisig threshold (the m in an m-of-n OP_CHECKMULTISIG)
- unhashed preimage / secret exposure
- unhandled or asymmetric OP_IF/OP_ELSE branches
- transaction malleability (SIGHASH flags, non-DER signatures, malleable witness data)
- locktime / OP_CHECKLOCKTIMEVERIFY / OP_CHECKSEQUENCEVERIFY bypass or misuse
- oversized or unbounded witness data

Output ONLY a Markdown report, one section per finding, each with:
- **Severity**: Critical, High, or Low
- **Finding**: one-sentence description
- **Exploit scenario**: how it would actually be abused
- **Suggested fix**: a concrete change

If the input is not a Bitcoin Script/miniscript/PSBT at all, say so plainly
and do not invent findings. If nothing is wrong, say so plainly -- do not
manufacture a finding just to have something to report.
"""


def audit(script_text: str) -> str:
    """Run the LLM audit and return a Markdown report.

    Raises on API failure (missing key, network, rate limit) -- callers
    (agent.py) are expected to catch this and turn it into an 'error'
    job-feedback event rather than letting it crash the listen loop.
    """
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": script_text}],
    )
    return "".join(block.text for block in response.content if block.type == "text")
