"""llm-judgement-eval: can you trust an LLM's judgement call inside an automated system?

Pipeline:  archive every live call -> replay it under controlled arms (model,
prompt, transform, provider mode) -> score consistency, cost and outcomes.
"""
__version__ = "0.1.0"
