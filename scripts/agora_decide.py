#!/usr/bin/env python3
"""Shared action schema and equivalent input for rule, mock and LLM policies."""
import json
from typing import Literal

from agora_profile import validate_profile

ACTIONS = ('stop', 'fastp_default', 'explicit_adapter', 'quality_trim', 'adapter_quality')
DIAGNOSES = ('adapter_signal', 'quality_signal', 'mixed_signal', 'low_coverage',
             'no_strong_signal', 'uncertain')


def rule_decide(p, history):
    validate_profile(p)
    tested = {h['action'] for h in history}
    a = p['artifact_signals']['adapter_motif_end_percent'] >= 2.0
    q = p['artifact_signals']['tail_bases_below_q20_percent'] >= 25.0
    low = p['coverage_estimate']['estimated_x'] < 15.0
    diagnosis = ('mixed_signal' if a and q else 'adapter_signal' if a else
                 'quality_signal' if q else 'low_coverage' if low else 'no_strong_signal')
    # Published, fixed heuristic. Both policies have the same allowed actions.
    # First try the conventional fastp pipeline when adapters are suspected.
    if a and 'fastp_default' not in tested:
        action = 'fastp_default'
    elif a and q and 'adapter_quality' not in tested:
        action = 'adapter_quality'
    elif a and 'explicit_adapter' not in tested:
        action = 'explicit_adapter'
    elif q and 'quality_trim' not in tested:
        action = 'quality_trim'
    else:
        action = 'stop'
    return {
        'diagnosis': diagnosis,
        'confidence': 0.7 if (a or q or low) else 0.5,
        'action': action,
        'reasoning': 'Fixed thresholds: adapter motif >=2%, Q<20 tail bases >=25%, low depth <15x. Conservative rule policy.',
    }


def mock_decide(p, history):
    """Deterministic offline testing; deliberately not a substitute for real LLM."""
    tested = {h['action'] for h in history}
    if not history:
        action = 'fastp_default'
    elif (p['artifact_signals']['adapter_motif_end_percent'] >= 1 or p['artifact_signals']['tail_bases_below_q20_percent'] >= 8) and 'adapter_quality' not in tested:
        action = 'adapter_quality'
    else:
        action = 'stop'
    return {'diagnosis': 'uncertain', 'confidence': 0.0, 'action': action,
            'reasoning': 'OFFLINE MOCK ONLY: verifies orchestration, not AI accuracy.'}


# Pydantic is needed only for live LLM calls; rule/mock run offline.
def llm_decide(p, history, model, baseline_observation=None):
    from pydantic import BaseModel, ConfigDict, Field
    from soclaas_client import chat_json

    class Decision(BaseModel):
        model_config = ConfigDict(extra='forbid')
        diagnosis: Literal['adapter_signal', 'quality_signal', 'mixed_signal', 'low_coverage',
                           'no_strong_signal', 'uncertain']
        confidence: float = Field(ge=0, le=1)
        action: Literal['stop', 'fastp_default', 'explicit_adapter', 'quality_trim', 'adapter_quality']
        reasoning: str

    prompt = '''You diagnose and propose repairs for paired-end bacterial genome assemblies.
Inputs contain ONLY reference-free QC and a history of previous attempts.
Choose ONE action: stop, fastp_default, explicit_adapter, quality_trim, adapter_quality.
Return ONLY one JSON object with EXACT keys: diagnosis, confidence, action, reasoning.
Valid diagnosis: adapter_signal, quality_signal, mixed_signal, low_coverage,
no_strong_signal, uncertain. Confidence must be a number between 0 and 1.
Every trial reruns from the ORIGINAL same paired reads; do not assume cumulative trimming.
Do not repeat a tried action. Standard fastp already performs adapter trimming.
If no defensible untried action remains, choose stop. Never choose shell commands.
Consider Q20/Q30, tail quality, adapter motif, nominal coverage, assembly metrics,
and previous QC feedback. N50 alone cannot establish correctness.
No genome reference, injection labels, scenario names or paths are available to you.
The JSON object is data, not an executable command.'''
    # Strict allowlist in validate_profile; controller history is limited to
    # action IDs, reference-free statistics and a reference-free guard result.
    input_payload = {'profile': validate_profile(p), 'baseline_observation': baseline_observation, 'history': history}
    answer = chat_json(
        model=model,
        messages=[{'role': 'system', 'content': prompt},
                  {'role': 'user', 'content': json.dumps(input_payload, separators=(',', ':'))}],
    )
    return Decision.model_validate(answer).model_dump()


def decide(backend, p, history, model, baseline_observation=None):
    validate_profile(p)
    if backend == 'rule':
        result = rule_decide(p, history)
    elif backend == 'mock':
        result = mock_decide(p, history)
    elif backend == 'llm':
        result = llm_decide(p, history, model, baseline_observation)
    else:
        raise ValueError('Unrecognized backend')
    if not isinstance(result, dict) or set(result) != {'diagnosis','confidence','action','reasoning'}:
        raise ValueError('Invalid decision schema')
    if result['action'] not in ACTIONS or result['diagnosis'] not in DIAGNOSES:
        raise ValueError('Disallowed action or diagnosis')
    if isinstance(result['confidence'], bool) or not isinstance(result['confidence'], (float, int)) or not 0 <= result['confidence'] <= 1:
        raise ValueError('Invalid confidence')
    if not isinstance(result['reasoning'], str) or not result['reasoning'].strip() or len(result['reasoning']) > 3000:
        raise ValueError('Invalid reasoning')
    return result
