"""generate_contract.py – Task 1

CLI: Convert natural‑language spec → secure Solidity code (ERC‑20 etc.)
Now automatically **saves** the generated contract to `<ContractName>.sol` (or a
custom path via `--out`).

Changes in this revision
────────────────────────
1. `--out PATH` option (default derives from first `contract Foo` name).
2. Writes the file after static‑analysis passes and prints its location.
3. Minor refactor: `call_llm()` returns `ContractResponse` object for clarity.
"""

import os
import re
import sys
import json
from pathlib import Path
from typing import List, Dict, Tuple, Union

import click
import openai
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError, model_validator

# ── Static‑analysis guardrail (stub) ────────────
try:
    from security.static_analysis import analyze as run_static_analysis  # type: ignore
except ImportError:
    def run_static_analysis(_: str) -> List[str]:
        return []

# ── OpenAI API init ─────────────────────────────
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    click.echo("Missing OPENAI_API_KEY", err=True)
    sys.exit(1)
openai.api_key = api_key

# ── Pydantic schema ─────────────────────────────
class ContractResponse(BaseModel):
    code: str
    explanation: Union[str, List[str]]

    @model_validator(mode="before")
    def _normalise_expl(cls, values: Dict) -> Dict:
        exp = values.get("explanation")
        if isinstance(exp, list):
            values["explanation"] = "\n".join(f"- {e}" for e in exp)
        return values

# ── JSON helpers ────────────────────────────────
MD_FENCE = re.compile(r"```(?:json)?|```", re.I)

def extract_json(raw: str) -> str:
    raw = MD_FENCE.sub("", raw).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    return raw[start : end + 1]

# Escape raw newlines inside the "code" string for JSON validity
def patch_newlines(json_txt: str) -> str:
    pat = re.compile(r'("code"\s*:\s*")(.*?)("\s*,\s*"explanation")', re.S)
    def repl(m: re.Match):  # type: ignore
        body = m.group(2).replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
        return f'{m.group(1)}{body}{m.group(3)}'
    return pat.sub(repl, json_txt, count=1)

# ── LLM call ────────────────────────────────────

def call_llm(requirement: str) -> ContractResponse:
    prompt = f"""
You are a Solidity security expert.
Generate a minimal, secure Solidity contract for:
"{requirement}"

• Use Solidity ^0.8.13 with OpenZeppelin audited contracts.
• Apply proper access control.
• Avoid reentrancy/public mint/self‑destruct.
Respond only in JSON with keys `code` and `explanation` (array preferred).
"""
    resp = openai.ChatCompletion.create(
        model="gpt-4",
        temperature=0.2,
        messages=[
            {"role": "system", "content": "You generate secure Solidity smart contracts."},
            {"role": "user", "content": prompt},
        ],
    )
    raw = resp.choices[0].message.content  # type: ignore
    try:
        data = json.loads(extract_json(raw))
    except json.JSONDecodeError:
        patched = patch_newlines(extract_json(raw))
        data = json.loads(patched)
    return ContractResponse(**data)

# ── Utility: derive filename ────────────────────

def default_filename(code: str) -> Path:
    match = re.search(r"contract\s+(\w+)", code)
    name = match.group(1) if match else "Contract"
    return Path(f"{name}.sol")

# ── CLI ─────────────────────────────────────────
@click.command()
@click.argument("requirement", nargs=-1)
@click.option("--out", "out_path", type=click.Path(path_type=Path), help="Save generated contract to this path.")
def main(requirement: Tuple[str, ...], out_path: Path | None):
    spec = " ".join(requirement).strip()
    if not spec:
        click.echo("Provide a contract requirement.", err=True)
        sys.exit(1)

    try:
        result = call_llm(spec)
    except (ValidationError, ValueError, RuntimeError) as e:
        click.echo(f"{e}", err=True)
        sys.exit(1)

    # Guardrail
    issues = run_static_analysis(result.code)
    if issues:
        click.echo("Static analysis found issues:", err=True)
        for iss in issues:
            click.echo(f" • {iss}", err=True)
        sys.exit(1)

    # Determine output filename
    dst = out_path if out_path else default_filename(result.code)
    try:
        dst.write_text(result.code)
        click.echo(f"Contract code saved to {dst.resolve()}")
    except Exception as e:
        click.echo(f"Failed to save file: {e}", err=True)

    # Console output
    click.echo("\n=== Generated Solidity Contract ===\n")
    click.echo(result.code)
    click.echo("\n=== Security Considerations ===\n")
    click.echo(result.explanation)


if __name__ == "__main__":
    main()
