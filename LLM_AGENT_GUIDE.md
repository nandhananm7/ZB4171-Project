# AGORA — Milestone 5A: LLM diagnosis (proposal-only)

This patch adds `scripts/llm_agent.py` and `tests/test_llm_agent.py`. It **does not alter your Snakefile**, replay assemblies, call SPAdes, or execute any model-selected action. The controller/feedback loop is a separate milestone.

## Install

From the activated `agora-mvp` environment, in your existing AGORA project directory:

```bash
# unzip the patch into your project folder
python -m pip install 'openai>=1.90' 'pydantic>=2'
python -m unittest discover -s tests -p 'test_llm_agent.py' -v
python scripts/llm_agent.py --profile results/agent_profiles/8x/profile.json --output results/llm/8x/decision.json --validate-only
```

### Set API credentials (optional for offline validation, required for LLM calls)

An OpenAI Platform API key and billing access may be necessary; a ChatGPT subscription is separate from API billing. Create a key at https://platform.openai.com/api-keys. Set `OPENAI_API_KEY` using a secure environment variable or secret manager. Avoid putting credentials in code, notebooks, chat, source control, or shell history. One interactive shell option:

```bash
read -rsp 'OpenAI API key: ' OPENAI_API_KEY; echo
export OPENAI_API_KEY
```

### Run one real LLM decision

```bash
python scripts/llm_agent.py \
  --profile results/agent_profiles/8x/profile.json \
  --output results/llm/8x/decision.json \
  --model gpt-5-mini
python -m json.tool results/llm/8x/decision.json
```

A decision may be `no_change`, `short_k`, or `auto_cutoff`; these are **only proposals**. Do not assume the LLM will match the rule-based diagnosis, or that any action improves accuracy. The client uses the OpenAI Responses API structured-output parser with Pydantic, then validates the action name against a small whitelist before saving the result. No arbitrary parameters from the LLM can enter the action configuration.

For other existing profiles, repeat with 15x, 30x, or full. Profile filenames are selected locally and are not included in the LLM prompt; only the validated JSON content is sent. Never include benchmark_metadata, reference-based QUAST, filenames that encode the scenario, or previous labeled evaluations in the prompt.

## Research cautions

- The model receives an approximate depth estimate that relies on a genome-size prior, so its success is a **reasoning-over-provided-metrics** test, not autonomous discovery of coverage.
- The 8x/15x profiles and our previous manual trials are development cases, not independent test results. Hold out additional read-sampling seeds and species for the final comparison.
- Later evaluate incorrect diagnoses, unwarranted changes, cost, and run-to-run variability. Freeze the prompts/decision schema before held-out trials.
- Schema adherence is not scientific truth. Rejecting dangerous parameters does not establish the biological quality of a proposed repair.
- Access to the API depends on your account/model permissions and can incur charges. Check your account limits and pricing.
