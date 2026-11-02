# AGORA — NUS SoCLaaS backend

The two AGORA LLM entry points now use **NUS School of Computing SoCLaaS**, not OpenAI Platform billing:

- `python scripts/agora_controller.py --backend llm` — iterative adapter/quality repair
- `python scripts/llm_agent.py` — earlier, diagnosis-only low-coverage experiment

Both use an OpenAI-compatible Python SDK pointed at the **NUS gateway**. The key is read from `SOCLAAS_API_KEY`, never `OPENAI_API_KEY`. Model IDs must come from the user's own `/v1/models` response; do not assume a model name.

**Documentation:** https://soclaas.comp.nus.edu.sg/guides/api.html

## Installation

In Ubuntu WSL2, inside your current AGORA project directory:

```bash
cp Snakefile Snakefile.pre_soclaas.bak
unzip -o /mnt/c/Users/nandh/Downloads/AGORA_SoCLaaS_patch.zip -d .
python -m pip install 'openai>=1.90' 'pydantic>=2'
python -m unittest discover -s tests -p 'test_soclaas_backend.py' -v
python -m unittest discover -s tests -p 'test_llm_agent.py' -v
python -m unittest discover -s tests -p 'test_agora_extension.py' -v
```

No Snakemake changes or genome re-download are required.

## 1. Obtain a NUS SoCLaaS key

Open https://soclaas.comp.nus.edu.sg/ and follow **Get My API Key**. The key portal requires NUS network access; use campus network or NUS VPN if needed. Access depends on your NUS/SoC account permissions. The API gateway itself is Internet accessible. Do not paste the key into chat, source code or commit history.

In your **Ubuntu** terminal (not Windows PowerShell):

```bash
read -rsp 'SoCLaaS key: ' SOCLAAS_API_KEY; echo
export SOCLAAS_API_KEY
```

The key only lasts in that terminal session unless you configure a secure credential solution. Never write it to the repository.

## 2. Discover and verify a chat model

```bash
python scripts/soclaas_check.py
python scripts/soclaas_check.py --ping MODEL_ID_FROM_LIST
export SOCLAAS_MODEL='MODEL_ID_FROM_LIST'
```

Replace the placeholder with the exact model `id` returned by the gateway. Not all models support chat. Use a chat-capable model.

## 3. Test the original diagnosis-only LLM

```bash
python scripts/llm_agent.py \
  --profile results/agent_profiles/8x/profile.json \
  --output results/llm/8x/decision.json \
  --validate-only

python scripts/llm_agent.py \
  --profile results/agent_profiles/8x/profile.json \
  --output results/llm/8x/decision.json \
  --model "$SOCLAAS_MODEL"
```

## 4. Test combined-failure iterative LLM

**First** verify the challenge profile exists (this may run Snakemake once):

```bash
snakemake --cores 4 results/challenges/combined/raw/profile.json
```

Then run one proposal and a two-step feedback loop:

```bash
python scripts/agora_controller.py --scenario combined \
  --backend llm --mode zero --cores 4 \
  --model "$SOCLAAS_MODEL"

python scripts/agora_controller.py --scenario combined \
  --backend llm --mode iterative --max-steps 2 --cores 4 \
  --model "$SOCLAAS_MODEL"
```

Audit outputs remain `results/agent_runs/combined/llm_zero.json` and `llm_iterative.json`. They now include `"provider": "soclaas"`. The action whitelist is unchanged and no model-authored shell command is executed. If the selected model outputs invalid JSON, schema-invalid fields, or an unavailable action, the controller **fails closed** rather than executing the repair.

## Important limitations

- The official SoCLaaS API documentation guarantees OpenAI-compatible chat completion, **not** that every model supports OpenAI-specific structured output settings. The integration requests a JSON text response, parses it, and validates locally with Pydantic. It doesn't rely on model-specific `response_format` or Responses `.parse()` capabilities.
- This patch was tested offline using simulated SDK replies. A live call requires your own NUS key and a chat-capable model ID.
- Eligibility, fair use or other service limits are controlled by NUS SoCLaaS. Its homepage advertises no per-call user API bill for eligible SoC community members, but verify your own access and applicable terms in the portal.
- Keep reference-based QUAST evaluation separate from model prompts, as in the original AGORA workflow.
