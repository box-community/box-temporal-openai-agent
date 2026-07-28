# Proposed durability enhancements

These changes are intentionally proposed, not yet implemented. They make Temporal's value easier
to see without changing the core Global Signal Desk story.

## Recommended first iteration

### 1. Explicit Activity retry policies

Add separate policies for:

- OpenAI planning, search, synthesis, and localization
- Box uploads
- Box AI extraction

Recommended behavior:

- Retry timeouts, rate limits, and transient network failures.
- Fail fast on authentication, authorization, invalid request, and unsupported model/file errors.
- Keep SDK-level retries disabled so Temporal remains the single retry owner.

Files:

- `agents/research_planning.py`
- `agents/research_query_generation.py`
- `agents/research_web_search.py`
- `agents/research_report_synthesis.py`
- `agents/localized_brief.py`
- `workflows/deep_research_workflow.py`

### 2. Queryable progress

Add Workflow state:

- `phase`
- `searches_total`
- `searches_completed`
- `briefs_total`
- `briefs_completed`
- `report_file_id`
- `box_ai_digest_file_id`

Expose it with `@workflow.query`, plus a small `show_progress.py` client.

This provides a positive durability demo: start a run, inspect its state while it works, and show
that the state is part of the Workflow rather than local terminal memory.

Files:

- `agents/shared.py`
- `workflows/deep_research_workflow.py`
- `show_progress.py`
- `tests/test_workflow.py`

### 3. Search-attempt visibility

Return a structured outcome for every query:

- `completed`
- `failed_after_retries`
- `skipped`

Preserve successful partial research, but include missing evidence in the source manifest and
confidence section. This makes graceful degradation auditable instead of silently dropping `None`
results.

Files:

- `agents/shared.py`
- `workflows/deep_research_workflow.py`
- `tests/test_workflow.py`

### 4. Evidence-coverage gate

Record `target_market` and `query_language` on each search query and outcome. Before synthesis,
compare successful evidence against every market required by the research request.

Recommended behavior:

- Retry missing market coverage with one focused query.
- Do not let several sources from one market hide a gap in another.
- If coverage remains incomplete, either publish an explicitly incomplete report or wait for a
  reviewer decision.

Files:

- `agents/shared.py`
- `agents/research_query_generation.py`
- `agents/research_web_search.py`
- `workflows/deep_research_workflow.py`
- `tests/test_workflow.py`

## Optional second iteration

### 5. Human review checkpoint

Add `--require-review`.

When enabled:

1. Synthesize the master report.
2. Set Workflow phase to `awaiting_review`.
3. Wait on `workflow.wait_condition`.
4. Accept an approval Signal or a typed Update that can add another output language.
5. Publish only after approval.

This demonstrates a long-lived agent waiting durably for a human without polling or keeping a
process alive.

### 6. External payload storage

The educational version places research and report text in Workflow History. For sensitive or
large reports:

- Upload intermediate artifacts to a restricted Box staging folder.
- Store only Box file IDs and integrity metadata in Workflow History.
- Consider a Temporal payload codec when values must remain in History.

This keeps the orchestration durable without turning Event History into the document store.

### 7. Safe Workflow evolution

Before changing orchestration for running production Workflows, add a deployment/versioning
strategy. Durable histories can outlive the code version that started them, so Workflow changes
must remain replay-compatible.

## Suggested demo sequence

1. Start the workflow and print its stable Workflow ID.
2. Query progress during planning and parallel search.
3. Open Temporal Web to show Activity attempts and completed results.
4. Show partial search outcomes and the explicit retry policy.
5. Show stable filenames derived from the Workflow ID.
6. Open the master report and Box AI digest in Box.
7. Optionally enable review mode and approve publication.

This demonstrates durability through visible state, traceability, and safe side effects—without
turning the story into a failure stunt.
