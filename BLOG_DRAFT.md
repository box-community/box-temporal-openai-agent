# Building a Durable Multilingual Research Agent with Temporal, OpenAI, and Box

*Why deep research is an orchestration problem—not one long model call.*

An international film distributor is preparing the release of an independent film in four
markets. The team needs to understand how audiences discover films in each country before deciding
where to invest in festivals, theatrical partnerships, streaming promotion, critics, creators, or
social campaigns.

The research brief looks like this:

> Using current local-language industry publications, national film institute reports, festival
> programs, cinema association data, and platform research, compare how audiences in France, Japan,
> Brazil, and Poland discover independent films. Assess the roles of festivals, theatrical release,
> streaming platforms, critics, creators, and social communities. Identify evidence gaps and
> implications for an international distributor designing market-specific release strategies.

This is not four translations of one search.

The useful evidence is distributed across different languages and different information
ecosystems. France has its own film institutions and festival network. Japan has local trade
publications and discovery platforms. Brazil's creator and community landscape is discussed in
Portuguese. Polish audience research, funding bodies, and industry coverage may never appear near
the top of an English-language search.

The multilingual angle is therefore part of retrieval, not just presentation. If the system
searches only in English and translates the final answer, it can produce polished briefs while
missing the local evidence that should shape them.

That creates two separate language requirements: the languages used to retrieve evidence and the
languages used to publish the result. A French source may be needed even if the final brief is only
written in English. Treating those settings as one list is a subtle design error, so the project
models them separately.

That is the problem behind **The Global Signal Desk**: turn one cross-market question into a
durable research process that searches current external sources, preserves citations, produces
localized briefs, and publishes a reusable research pack into Box.

The difficult part is not asking a model to write a report. It is coordinating everything that must
happen before and after that model call.

## Why one prompt is the wrong abstraction

A useful report requires several distinct operations:

1. Turn the business question into a research plan.
2. Generate focused queries for each market and language.
3. Search current external sources.
4. Preserve useful results when one search does not complete.
5. Synthesize evidence without hiding contradictions or gaps.
6. Create localized briefs from the same source report.
7. Upload every artifact without leaving duplicate files behind during retries.
8. Ask Box AI to extract a consistent executive digest from the stored report.

Some operations can run concurrently. Others need outputs created by earlier steps. Every model
call, search, and upload crosses a network boundary.

This is no longer a prompt. It is a distributed workflow with state and side effects.

The project assigns a clear responsibility to each system:

- **OpenAI** plans, searches the web, synthesizes evidence, and creates localized briefs.
- **Temporal** stores execution state and coordinates dependencies, concurrency, retries, and
  failure semantics.
- **Box** stores the report, source manifest, and market briefs as managed content.
- **Box AI** extracts a standardized digest from the report after it has entered Box.

```text
Business question
      ↓
Research plan
      ↓
Market- and language-specific queries
      ↓
Parallel web-search Activities
      ↓
Cited master report
      ↓
Localized executive briefs
      ↓
Retry-safe publication to Box
      ↓
Box AI digest
```

**[Insert short demo video here]**

*Suggested caption: One multilingual research request moving through planning, parallel search,
synthesis, Box publication, and Box AI extraction.*

## Following one durable Workflow execution

The implementation is adapted from Temporal's
[OpenAI deep-research cookbook example](https://github.com/temporalio/ai-cookbook/tree/main/deep_research/basic_openai_python).
The main Workflow reads like ordinary asynchronous Python:

```python
@workflow.defn
class DeepResearchWorkflow:
    @workflow.run
    async def run(
        self,
        request: ResearchRequest,
    ) -> GlobalSignalDeskResult:
        research_plan = await plan_research(request.query)

        query_plan = await generate_queries(
            research_plan,
            request.research_languages,
        )

        search_results = await self._execute_searches(
            query_plan.queries
        )

        if not search_results:
            raise ApplicationError(
                "No web searches produced usable results",
                "NO_SEARCH_RESULTS",
                non_retryable=True,
            )

        final_report = await generate_synthesis(
            request.query,
            research_plan,
            search_results,
        )
```

The method describes the agent's decisions and dependencies. It does not open an HTTP connection,
create an OpenAI client, or upload a file.

That boundary is fundamental to Temporal:

- A **Workflow** contains deterministic orchestration.
- An **Activity** performs non-deterministic work such as API calls and external writes.

Temporal records the Workflow's progress in
[Event History](https://docs.temporal.io/workflow-execution). If a Worker process restarts, the
Workflow is replayed against that history to reconstruct its state. Results from completed
Activities are already recorded, so the orchestration can resume without deliberately repeating
every successful model call.

For an agent, this history is effectively the durable record of what has happened: the plan was
created, these searches completed, synthesis received these results, and publication produced
these Box file IDs.

Durability here does not mean that the model itself has memory. It means the process around the
model has recoverable state.

## Planning multilingual retrieval

The query-generation step receives both the research plan and the required research languages. Its
job is not merely to translate one phrase. It creates searches that use the vocabulary and source
landscape of each market.

```python
request = ResearchRequest(
    query=research_question,
    research_languages=[
        "French",
        "Japanese",
        "Portuguese",
        "Polish",
    ],
    output_languages=[
        "English",
        "French",
        "Japanese",
        "Portuguese",
        "Polish",
    ],
)
```

`research_languages` controls evidence collection. `output_languages` controls the briefs created
after synthesis. Keeping them separate prevents presentation choices from silently narrowing the
source base.

For the film-discovery brief, useful queries might target:

- French film institute research and festival attendance
- Japanese independent cinema and local streaming discovery
- Brazilian audiovisual market studies and creator communities
- Polish film festival, cinema, and audience reports

Each query becomes structured input to an
[OpenAI web-search](https://developers.openai.com/api/docs/guides/tools-web-search) Activity:

```python
result = await workflow.execute_activity(
    invoke_model,
    InvokeModelRequest(
        model=EFFICIENT_PROCESSING_MODEL,
        instructions=WEB_SEARCH_INSTRUCTIONS,
        input=search_input,
        response_format=SearchResult,
        tools=[{"type": "web_search"}],
    ),
    start_to_close_timeout=timedelta(seconds=300),
    summary="Searching web for information",
)
```

`SearchResult` is a Pydantic model rather than an arbitrary block of text. It carries:

- The query that was executed
- Source URLs and descriptions
- Relevant findings
- A relevance score
- Formatted citations

Typed results matter because every stage has a contract. Synthesis should receive evidence and
citations, not reverse-engineer them from prose generated by the previous call. The Temporal client
and Worker use the Pydantic data converter to move those objects across the Workflow boundary.

## Parallel searches without losing useful work

Market searches are independent, so the Workflow fans them out concurrently:

```python
async def _execute_searches(self, search_queries):
    async def execute_single_search(search_query):
        try:
            return await search_web(search_query)
        except Exception:
            workflow.logger.exception(
                "Search did not complete for query %s",
                search_query.query,
            )
            return None

    results = await asyncio.gather(
        *(execute_single_search(query) for query in search_queries)
    )

    return [result for result in results if result is not None]
```

The pattern is fan-out followed by fan-in: searches can progress independently, while synthesis
waits for the available results.

The error handling also encodes a research decision. A terminal failure in one search does not
discard successful evidence from every other market. The Workflow continues with useful partial
results. If no search produces evidence, it stops with a non-retryable `NO_SEARCH_RESULTS` error
instead of asking the model to invent a report from an empty context.

This is a more useful definition of agent durability than “retry everything.” Durable execution
preserves completed work and makes the conditions for continuing explicit.

## Giving one system ownership of retries

All OpenAI operations pass through one generic Temporal Activity:

```python
@activity.defn
async def invoke_model(
    request: InvokeModelRequest[T],
) -> InvokeModelResponse[T]:
    client = AsyncOpenAI(max_retries=0)

    kwargs = {
        "model": request.model,
        "instructions": request.instructions,
        "input": request.input,
    }

    if request.response_format:
        kwargs["text_format"] = request.response_format

    if request.tools:
        kwargs["tools"] = request.tools

    response = await client.responses.parse(**kwargs)
    ...
```

The OpenAI SDK's retry layer is disabled deliberately. If the SDK and Temporal both retry, one
logical Activity attempt can generate several underlying API calls, making cost and behavior harder
to reason about.

The current demo relies on Temporal's default Activity retry behavior. A production version should
make its [Retry Policy](https://docs.temporal.io/encyclopedia/retry-policies) explicit:

```python
MODEL_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
)
```

It should also translate authentication and invalid-request errors into non-retryable
`ApplicationError`s. A timeout or rate limit may deserve another attempt. An invalid credential
does not.

The principle is simple: one layer should own retries, and the retry policy should reflect the
semantics of the external system.

## Synthesis and localization share one evidence base

Once search completes, the synthesis Activity receives the original question, research plan, and
all usable `SearchResult` objects. It creates a master report with:

- An executive summary
- Detailed cross-market analysis
- Key findings
- Confidence assessment
- Citations
- Follow-up questions

The confidence section is important for this example. “Independent film,” “audience discovery,”
and even “streaming adoption” may be measured differently across markets. The report should
distinguish comparable evidence from directional signals rather than force every country into one
ranking.

Localization happens after synthesis:

```python
localized_briefs = await asyncio.gather(
    *(
        generate_localized_brief(
            request.query,
            final_report,
            language,
        )
        for language in request.output_languages
    )
)
```

All briefs derive from the same cited report. This avoids four disconnected research agents
producing four incompatible versions of the evidence. The language and emphasis can be localized;
the underlying facts, uncertainty, and citations remain anchored to one master artifact.

For this scenario, the Workflow can produce briefs in English, French, Japanese, Portuguese, and
Polish for distribution and market teams.

## Making Box publication retry-safe

Model calls are not the only side effects. Temporal may execute an Activity more than once, so
uploading a file must be safe to repeat.

Every output filename contains the stable Temporal Workflow ID. Before uploading, the Box Activity
checks the destination folder for an exact filename:

```python
existing = _existing_file(
    client,
    folder_id,
    artifact.filename,
)

if existing:
    updated = client.uploads.upload_file_version(
        existing.id,
        UploadFileVersionAttributes(
            name=artifact.filename
        ),
        content,
    )
    entry = updated.entries[0]
else:
    uploaded = client.uploads.upload_file(
        UploadFileAttributes(
            name=artifact.filename,
            parent=UploadFileAttributesParentField(
                id=folder_id
            ),
        ),
        content,
    )
    entry = uploaded.entries[0]
```

A repeated upload therefore creates a new version of the intended file rather than another copy
with a slightly different name.

Temporal provides durable retries, but the application still has to make external side effects
safe to repeat. Stable Workflow IDs provide the correlation key; Box file versioning provides the
duplicate-resistant write behavior.

This distinction matters: the implementation is retry-safe, but it is not strictly idempotent.
Each retry after a successful-but-unacknowledged upload can add another file version. Two concurrent
runs using the same Workflow ID could also race between the filename check and upload. A production
implementation should prevent Workflow ID reuse and persist the returned Box file ID so later
attempts can address the object directly.

The completed research pack contains:

```text
global-signal-...--master-report.md
global-signal-...--brief-english.md
global-signal-...--brief-french.md
global-signal-...--brief-japanese.md
global-signal-...--brief-portuguese.md
global-signal-...--brief-polish.md
global-signal-...--sources.json
global-signal-...--box-ai-digest.md
```

The source manifest keeps external references machine-readable. Market briefs are ready for local
teams. The master report remains the shared evidence base.

## Why Box AI is a separate final stage

The workflow could stop after uploading the report. Instead, Temporal passes the new Box file ID
to another Activity:

```python
def _analyze_with_box_ai_sync(
    request: BoxAIReviewRequest,
) -> BoxAIDigest:
    client = _box_client()

    response = client.ai.create_ai_extract(
        BOX_AI_DIGEST_PROMPT,
        [AiItemBase(id=request.report_file_id)],
    )

    payload = response.to_dict()

    return BoxAIDigest(
        answer=_coerce_answer(
            payload.get("answer", {})
        ),
        completion_reason=payload.get(
            "completion_reason"
        ),
        created_at=payload.get("created_at"),
    )
```

[Box AI Extract](https://developer.box.com/guides/box-ai/quick-start/box-ai-extract-freeform)
analyzes the report using its Box file ID and extracts a consistent set of fields:

- Executive digest
- Important themes
- Markets discussed
- Confidence notes
- Follow-up questions

This is not a replacement for external research. OpenAI searched current web sources and produced
the report. Box AI operates on the completed artifact after it enters the content system.

That separation makes the final step useful rather than repetitive. The research pipeline optimizes
for evidence collection and synthesis. The Box AI step optimizes for turning stored content into a
predictable, reusable summary for the next person or application.

## Making durability visible

The current implementation is durable, but a reader mainly sees that durability in Temporal Web.
Four small additions would make it part of the demo itself.

### Explicit Activity policies

Add separate retry policies for OpenAI, Box uploads, and Box AI. Record terminal errors such as
authentication failures as non-retryable, and cap attempts for calls with usage cost.

### An evidence-coverage gate

The current demo continues when at least one search succeeds. That preserves useful work, but it is
too permissive for a four-market comparison: three strong French sources cannot compensate for
missing Japanese evidence.

A production Workflow should track the target market and language on every query and result, then
check coverage before synthesis. If a market remains unsupported after targeted retries, the
Workflow can publish an explicitly incomplete report or wait for a reviewer to choose the next
step. Durability should preserve partial evidence without disguising an evidence gap.

### A progress Query

A [Temporal Query](https://docs.temporal.io/develop/python/workflows/message-passing) can expose
Workflow state without changing it:

```python
@workflow.query
def progress(self) -> dict:
    return {
        "phase": self.phase,
        "searches_total": self.searches_total,
        "searches_completed": self.searches_completed,
        "briefs_completed": self.briefs_completed,
        "report_file_id": self.report_file_id,
    }
```

A small CLI could query the stable Workflow ID while the agent runs. The demo would show that
progress belongs to the Workflow, not to the terminal process that happened to start it.

### An optional review Update

For production research, add a typed
[Temporal Update](https://docs.temporal.io/develop/python/workflows/message-passing) after synthesis.
A reviewer could approve publication or request an additional language. The Workflow could wait
durably without polling a database or keeping an in-memory process open.

These changes expose durability through state, policy, and interaction—not through a staged failure
demo.

## Technical trade-offs

This is an educational implementation, so several production decisions remain intentionally
simple:

- The Box developer token is convenient but short-lived. A deployed worker should use an
  enterprise-approved OAuth, JWT, or Client Credentials Grant flow.
- Report text and intermediate research enter Temporal Event History. For large or sensitive
  research, store artifacts externally and pass Box references, or use an appropriate payload
  codec.
- The source manifest records citations, but production research may also need source snapshots,
  retrieval timestamps, ownership, and review status.
- Workflow code must remain replay-compatible with existing histories. Production deployment
  requires a safe Worker and Workflow versioning strategy.
- Generated market intelligence still requires qualified human review.

These are not reasons to avoid durable orchestration. They are the design decisions that become
visible once an agent moves beyond a single response.

## Run the project

The demo requires:

1. Python 3.11 or newer and `uv`
2. Temporal CLI
3. An OpenAI API key with access to the configured models and web search
4. A Box Platform App with read, write, and AI scopes
5. A Box folder for the generated research pack

Start the persistent local Temporal server:

```bash
make temporal
```

Start the Worker:

```bash
uv run python -m worker
```

Then run the research brief:

```bash
uv run python -m start_workflow \
  "Using current local-language industry publications, national film institute reports, festival programs, cinema association data, and platform research, compare how audiences in France, Japan, Brazil, and Poland discover independent films. Assess the roles of festivals, theatrical release, streaming platforms, critics, creators, and social communities. Identify evidence gaps and implications for an international distributor designing market-specific release strategies." \
  --industry creative-industries \
  --research-languages French Japanese Portuguese Polish \
  --languages English French Japanese Portuguese Polish
```

Temporal Web shows the complete Activity timeline. Box receives the master report, source
manifest, localized briefs, and Box AI digest.

**[Add GitHub repository link here]**

## Final thoughts

The Global Signal Desk is not interesting because it can generate a report. A single model call can
already generate something that looks like one.

The more useful result is a research process with explicit stages, typed evidence, durable state,
controlled retries, partial-result handling, retry-safe publication, and a managed content
destination.

The multilingual design makes that distinction easier to see. The system does not translate one
global answer into five languages. It searches across local information ecosystems, synthesizes one
evidence base, and then produces briefs that different market teams can use.

That is the shift from an AI response to a durable agent workflow.
