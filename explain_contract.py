#!/usr/bin/env python3
"""explain_contract.py – Task 2

CLI: Explain a Sepolia testnet contract (address) **or** a Solidity/ABI/bytecode
blob and output a structured JSON‑based summary.

Latest fixes
────────────
* Prompt builder now returns a **syntactically correct** Python string block.
* No functional logic changed elsewhere.
"""
from __future__ import annotations

import os
import re
import sys
import json
from pathlib import Path
from typing import List, Union, Dict, Tuple

import click
import openai
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError, model_validator
from web3 import Web3, HTTPProvider

# ── ENV & Web3 init ────────────────────────────────────────────────────────────
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    click.echo("Missing OPENAI_API_KEY", err=True)
    sys.exit(1)
openai.api_key = api_key

SEPOLIA_RPC = os.getenv("SEPOLIA_RPC")
ETHERSCAN_KEY = os.getenv("ETHERSCAN_API_KEY")  # optional
w3: Web3 | None = Web3(HTTPProvider(SEPOLIA_RPC)) if SEPOLIA_RPC else None

ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

# ── Pydantic schema with flexible coercion ────────────────────────────────────
class Summary(BaseModel):
    summary: str
    key_functions: List[Union[str, Dict]]
    permissions: List[Union[str, Dict]]
    security_patterns: List[Union[str, Dict]]

    @model_validator(mode="before")
    def _normalise_lists(cls, values: Dict):
        for k in ("key_functions", "permissions", "security_patterns"):
            items = values.get(k, [])
            normd: List[str] = []
            if isinstance(items, str):
                items = [items]
            for item in items:
                if isinstance(item, dict):
                    normd.append(" – ".join(str(v) for v in item.values()))
                else:
                    normd.append(str(item))
            values[k] = normd
        return values

# ── Static‑analysis stub ───────────────────────────────────────────────────────
try:
    from security.static_analysis import analyze as run_static
except ImportError:
    def run_static(_: str):
        return []

# ── Fetch helpers ──────────────────────────────────────────────────────────────

def fetch_abi(address: str) -> str | None:
    if not ETHERSCAN_KEY:
        return None
    url = (
        "https://api-sepolia.etherscan.io/api?module=contract&action=getabi"
        f"&address={address}&apikey={ETHERSCAN_KEY}"
    )
    try:
        res = requests.get(url, timeout=10).json()
        if res.get("status") == "1":
            return res["result"]
    except Exception:
        pass
    return None

def fetch_bytecode(address: str) -> str:
    if w3 is None:
        raise RuntimeError("SEPOLIA_RPC not set for bytecode fetch.")
    return w3.eth.get_code(Web3.to_checksum_address(address)).hex()

# ── Input loader ───────────────────────────────────────────────────────────────

def load_target(target: str) -> Tuple[str, str]:
    """Return (kind, payload) where kind ∈ {abi, bytecode, solidity}."""
    if ADDRESS_RE.fullmatch(target):
        abi = fetch_abi(target)
        if abi:
            return "abi", abi
        return "bytecode", fetch_bytecode(target)

    if target == "-":
        return "solidity", sys.stdin.read()

    path = Path(target)
    if path.exists():
        return "solidity", path.read_text()

    return "solidity", target  # treat as raw solidity/ABI string

# ── Prompt builder ─────────────────────────────────────────────────────────────

def build_prompt(kind: str, payload: str) -> str:
    intro_map = {
        "abi": "Here is the JSON ABI of a smart contract:",
        "bytecode": "Here is the EVM bytecode (hex):",
        "solidity": "Here is the Solidity source code:",
    }
    intro = intro_map[kind]

    # Trim very large payloads
    snippet = (
        payload
        if len(payload) < 8000
        else payload[:4000] + "\n…\n" + payload[-4000:]
    )

    # Final prompt
    return ( f"{intro}\n\n{snippet}"
        "Produce a concise technical summary **in JSON only** with these keys: "
        "summary, key_functions, permissions, security_patterns."

        "Formatting guidelines:"
        "• **summary** – one sentence (≤ 50 words)."
        "• **key_functions** – list of strings like \"mint(address,uint256) – mints tokens to an address\"."
        "• **permissions** – list of strings like \"mint: MINTER_ROLE\" or \"addMinter: DEFAULT_ADMIN_ROLE\"."
        "• **security_patterns** – list of plain strings (e.g. \"Role‑based access via AccessControl\", \"ReentrancyGuard used\")."
        "Access‑control rule: any function that ultimately calls or is gated by "
        "OpenZeppelin’s `grantRole`, `revokeRole`, `hasRole`, `onlyRole`, or an "
        "inherited modifier such as `onlyRole(MINTER_ROLE)` **is considered "
        "protected**. Do NOT mark it ‘unprotected’."
        "Respond with valid minified JSON (no Markdown fences, no commentary)."
    )

# ── LLM call ───────────────────────────────────────────────────────────────────

def call_llm(prompt: str) -> Summary:
    resp = openai.ChatCompletion.create(
        model="gpt-4",
        temperature=0.0,
        messages=[
            {"role": "system", "content": "You are a senior Solidity auditor."},
            {"role": "user", "content": prompt},
        ],
    )
    raw = resp.choices[0].message.content.strip()  # type: ignore
    raw = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from LLM: {e}\nRaw output:\n{raw}")
    return Summary(**data)

# ── CLI ────────────────────────────────────────────────────────────────────────
@click.command()
@click.argument("target")
@click.option("--raw", is_flag=True, help="Treat TARGET as raw solidity string.")
def main(target: str, raw: bool):
    """Explain a Sepolia contract address, .sol file, or raw solidity/ABI."""
    try:
        kind, payload = ("solidity", target) if raw else load_target(target)
    except Exception as exc:
        click.echo(f"Input error: {exc}", err=True)
        sys.exit(1)

    prompt = build_prompt(kind, payload)
    try:
        summary = call_llm(prompt)
    except (ValidationError, RuntimeError) as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(1)

    if kind == "solidity":
        issues = run_static(payload)
        if issues:
            click.echo("Static‑analysis issues:", err=True)
            for iss in issues:
                click.echo(f" • {iss}", err=True)
            click.echo()

    click.echo("\n=== Contract Summary ===\n")
    click.echo(summary.summary)

    def pprint(title: str, items: List[str]):
        click.echo(f"\n{title}:")
        for itm in items:
            click.echo(f" • {itm}")

    pprint("Key Functions", summary.key_functions)
    pprint("Permissions", summary.permissions)
    pprint("Security Patterns", summary.security_patterns)


if __name__ == "__main__":
    main()
