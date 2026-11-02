# Evaluation and tracing

This phase provides offline dataset validation, agent/tool safety checks, and opt-in live model evaluation for the enterprise support platform.

## Included
- 35 JSONL golden cases across normal, negative, edge, and multi-step scenarios
- Expected tool calls and human-approval requirements on every case
- CI-blocking dataset and approval-safety contract checks
- DeepEval GEval scoring for adherence to expected behavior
- RAGAS answer-relevancy scoring
- Per-case LangSmith traces with model latency/token usage, agent latency, retrieval counts, and tool execution details
- JSON report export containing model outputs, metrics, latency, and LangSmith filter details
- REST endpoint to read dataset quality and an opt-in endpoint mode for live evaluation

## Run

Offline validation does not make model calls:

```powershell
python -m evaluation.run_evaluation
```

Live scoring generates an answer for each row with `OPENAI_MODEL`, then evaluates it with the selected provider and `OPENAI_EVALUATION_MODEL`:

```powershell
python -m evaluation.run_evaluation --live --provider deepeval
python -m evaluation.run_evaluation --live --provider ragas
python -m evaluation.run_evaluation --live --provider both --output evaluation/reports/latest.json
```

Live evaluation also runs each scenario through the support agent and compares actual tool events
with `expected_tool_calls`. Cases marked `requires_approval` must produce a pending approval and
must never execute `create_support_ticket`. The live command exits nonzero if these critical
safety checks fail or if the provider scores do not meet the defaults (0.70 mean score); tune the
thresholds explicitly with `--min-deepeval-score` and `--min-ragas-score`.

Set `OPENAI_API_KEY` before running live evaluations. LangSmith tracing is optional; set `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT` to group generated model spans by run. Open `https://smith.langchain.com` and filter the project traces by the report's `evaluation_run_id`.

Live calls incur OpenAI costs. RAGAS currently uses its `answer_relevancy` metric; DeepEval uses a GEval rubric against the expected behavior. RAGAS 0.4.x imports a legacy Vertex AI adapter from LangChain Community, so dependencies constrain `langchain-community` to the compatible 0.3.x line. After changing dependencies, run `python -m pip install -r backend/requirements.txt`. Provider import/runtime failures are reported rather than represented as successful evaluations.

## Push CI

The `CI` workflow always runs offline Python tests, the frontend build, and the dataset quality
gate on pushes and pull requests. When the repository has an Actions secret named
`OPENAI_API_KEY`, it also runs the live OpenAI smoke test and both metric providers after offline
checks pass. Without the secret, the live job explicitly skips API calls and offline CI still runs.
The live job fails on any agent tool/approval safety failure or score below 0.70.

Add the secret under **Settings → Secrets and variables → Actions**. Live runs use billable model,
embedding, and evaluator calls. Optional LangSmith publishing requires both a `LANGSMITH_API_KEY`
secret and a `LANGSMITH_TRACING` repository variable set to `true`. The JSON report is uploaded as
the `live-evaluation-report` workflow artifact.
