# Movie Production Studio — Architecture Foundation

## Objective

Add a cinematic, long-form production division to ConGenAI without replacing or destabilizing the monetizable short-form content factory.

The platform has two independently operated production divisions:

1. **Content Factory** — channel-scoped Shorts, Reels and YouTube content, using the existing discovery, nightly orchestration, content pipeline and human approval flow.
2. **Movie Studio** — standalone and episodic films, from brief and screenplay through shot-level generation, editing, quality review and human approval.

They may reuse platform capabilities, but must not share project state, editorial decisions, production queues or budgets.

## Architectural boundaries

- Keep movie domain logic under a dedicated `movie` package/module.
- Keep existing short-form routes, models, pipeline states and channel ownership semantics backward-compatible.
- Reuse provider adapters only through stable service interfaces; movie-specific orchestration must not call short-form pipeline internals directly.
- Use separate queues and worker concurrency limits for movie and short-form jobs.
- Share only cross-cutting capabilities: LLM gateway, media-provider adapters, asset storage, voice/audio adapters, rendering primitives, observability and resource admission.
- Publishing is out of scope. Both divisions stop at an explicit human review/approval boundary.

## Movie project lifecycle

A movie project moves through these stages:

1. `DRAFT_BRIEF` — genre, premise, audience, language, runtime, rating, visual style, budget and delivery profile.
2. `STORY_DEVELOPMENT` — logline, synopsis, outline, screenplay, dialogue and character arcs.
3. `PRE_PRODUCTION` — character bibles, world/location bible, reference assets, storyboard and shot list.
4. `SHOT_PLANNING` — shot specifications, duration, framing, camera, performance, audio and continuity requirements.
5. `PRODUCTION` — shot jobs and take generation, with retry/regeneration at shot granularity.
6. `POST_PRODUCTION` — scene assembly, dialogue, sound effects, score, subtitles, colour and final render.
7. `QUALITY_REVIEW` — continuity, coverage, technical media checks, audio, captions, runtime and genre-specific review.
8. `AWAITING_APPROVAL` — reviewable output exists; no automatic publication.
9. Terminal outcomes: `APPROVED`, `REVISION_REQUIRED`, `REJECTED`, `FAILED`, `CANCELLED`.

Persist transitions and stage outputs. Long-running generation must be resumable; do not restart completed shots because a later shot failed.

## Genre system

The Genre Registry is data-driven. Built-in profiles are configuration, not branches in the orchestration code. A project can select one genre, a hybrid list (for example, historical thriller), or a user-defined profile.

Each genre profile can provide:
- narrative conventions and pacing guidance;
- visual and sound-design guidance;
- research/accuracy requirements;
- content-rating considerations;
- genre-specific review checks;
- optional weights for creative evaluation.

The common production workflow remains the same for every genre. Unknown custom genres inherit the neutral base profile and can override any supported fields.

## Shot as the production unit

A film is not generated as one long video prompt. The screenplay is decomposed into scenes and shots. A shot specification should capture:

- stable shot ID and scene ID;
- screenplay beat and purpose;
- target duration and aspect ratio;
- shot size, camera angle, movement and lens/look intent;
- location, time of day, characters, props and action;
- dialogue, voice/performance direction and audio layers;
- references to character, environment and prop bibles;
- continuity constraints and previous/next shot relationships;
- provider requirements, generation attempts, selected take and QA status.

Generate multiple takes where budget permits. Keep all take metadata and selected-take rationale. A failed shot should be retried independently, not force a full-film rerun.

## Shared resource scheduler contract

All media generation and rendering jobs request capacity through one admission interface. The scheduler is a resource broker, not a creative orchestrator.

A job request includes:
- division: `content_factory` or `movie_studio`;
- project/channel and job identifiers;
- workload class: `llm`, `image`, `video`, `audio`, `render` or `qa`;
- preferred execution: `local`, `cloud` or `hybrid`;
- estimated VRAM/RAM, GPU slots, CPU slots and storage needs where known;
- priority, deadline, estimated cost ceiling and retry policy;
- cancellation and resumability metadata.

Admission rules:
- Enforce per-division concurrency and budget limits.
- Enforce global GPU/VRAM and CPU capacity; never assume two jobs can safely fit because they are from different divisions.
- Reserve capacity before dispatch and release it on completion, failure or cancellation.
- Apply fair scheduling so a movie render cannot starve nightly channel jobs, and vice versa.
- Permit pause/resume for resumable work; do not kill active work without an explicit policy.
- Route to cloud only when the project policy permits it and the cost ceiling is respected.
- Record actual provider, runtime, resource use and cost for every attempt.
- If no safe capacity is available, queue the job and report the reason; do not silently overcommit.

The first implementation should use a provider-neutral interface and a deterministic in-process admission policy. Hardware telemetry, distributed leases and advanced preemption are later increments; do not claim these exist until implemented and tested.

## Initial movie profile

The initial acceptance profile is a 15-minute, English-language, standalone science-fiction short film, photorealistic cinematic look, 1080p target, hybrid local/cloud generation and manual approval. These are editable project defaults, not system-wide restrictions.

A 60–90 second proof of concept should validate identity consistency, shot-to-shot continuity, dialogue/voice, lip-sync and camera motion before attempting a complete short film. A 3-minute multi-scene sequence is the next gate. Runtime and quality are measured on actual provider/hardware combinations; no throughput guarantee is assumed.

## Data ownership (logical model)

- `MovieProject`: brief, genre profile IDs, creative settings, lifecycle, budget and approval state.
- `MovieCharacter`: canonical identity, appearance/performance bible and reference asset links.
- `MovieLocation`: environment bible, geography, lighting and reference assets.
- `MovieScene`: screenplay section, order, setting and continuity context.
- `MovieShot`: shot contract, status, selected take and continuity links.
- `MovieTake`: provider/model, prompt version, input references, output asset, cost, duration and QA result.
- `MovieAsset`: typed asset metadata and storage reference.
- `ProductionJob`: resumable stage/job record with idempotency key and retry history.
- `ResourceLease`: capacity reservation and lifecycle for a dispatched workload.
- `MovieReview`: human decision, notes and immutable review history.

These are logical entities. Map them to the repository's actual ORM and migration conventions only after inspecting the current source and existing open PRs.

## API boundary (proposed)

- `POST /api/v1/movies/projects` — create a project from a validated brief.
- `GET /api/v1/movies/projects` and `GET /api/v1/movies/projects/{id}` — list/detail.
- `PATCH /api/v1/movies/projects/{id}` — update editable brief fields.
- `POST /api/v1/movies/projects/{id}/plan` — create story/pre-production/shot plans.
- `POST /api/v1/movies/projects/{id}/produce` — enqueue eligible production work.
- `GET /api/v1/movies/projects/{id}/jobs` — stage, shot and queue status.
- `POST /api/v1/movies/projects/{id}/review` — record approve/revise/reject after required QA.

Do not expose endpoints until their schemas, authorization, persistence, idempotency and tests are implemented.

## Delivery sequence

1. Establish this additive architecture and genre configuration.
2. Inspect the current application models, provider adapters, queue and migrations; map the contracts to existing conventions.
3. Implement movie project/scene/shot/take persistence and migrations.
4. Implement brief validation, Genre Registry loading and story/pre-production contracts.
5. Implement resumable shot orchestration and provider adapter reuse.
6. Implement shared resource admission and per-division accounting.
7. Implement post-production/QA and human review.
8. Run unit, migration, API, queue and provider-mocked integration tests.
9. Benchmark the proof-of-concept and only then set realistic runtime/cost targets.

## Non-goals and safeguards

- No automatic publishing.
- No assumption that a specific GPU has arrived or is available.
- No promise that a 15-minute film can be generated in one pass.
- No silent use of paid cloud providers; provider and budget policy must be explicit.
- No replacement of the existing nightly content factory.
- No claims of perfect character continuity; continuity is measured and reviewed.
