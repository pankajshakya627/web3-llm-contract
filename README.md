# web3-llm-contract


# Smart-Contract Assistant

> **Status:** prototype - only the two core CLIs are implemented.

---

## 1. Contents

```

.
├─ generate_contract.py   # Task 1 – NL → secure Solidity
├─ explain_contract.py    # Task 2 – Contract explainer
├─ requirements.txt
└─ README.md

````


---

## 2. What’s implemented?

| File | Purpose | Key points |
|------|---------|------------|
| **generate_contract.py** | Converts natural-language specs into Solidity. | • GPT-4 call → JSON `{code, explanation}`<br>• Pydantic validation + newline-escape patch<br>• Slither guardrail stub<br>• Saves output to `--out` path (default `<Title>.sol`) |
| **explain_contract.py**  | Plain-English summary of a contract. | • Accepts Sepolia **address** or local `.sol` / stdin<br>• Pulls ABI via Etherscan (if key set) else raw bytecode<br>• GPT-4 summary → JSON with `summary`, `key_functions`, `permissions`, `security_patterns`<br>• Normalises lists/dicts to strings to avoid validation errors |

---

## 3. Quick setup

```bash
# deps
pip install -r requirements.txt                # openai, web3, pydantic, python-dotenv, click

````

Create a `.env`:

```dotenv
OPENAI_API_KEY=sk-...

```

---

## 4. Usage

### Task 1 – generate contract

```bash
python generate_contract.py \
  "Create an ERC-20 token with minting restricted to an allowlist" \
  --out AllowlistToken.sol
```

### Task 2 – explain contract

```bash
# by address
python explain_contract.py 0xAbc...123

# by local file
python explain_contract.py MyToken.sol
```

Outputs JSON to stdout. If Slither (or another tool you add in `security/static_analysis.py`) detects high-severity issues, the CLI exits with code 1.

---

## 5. Disclaimer

Generated Solidity and LLM summaries are **not audits**. Review and test thoroughly before deployment.

MIT © 2025



