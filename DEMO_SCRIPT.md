# Demo Script -- Deliverables 2 & 3 (15 minutes)

Use this as talking points for the live demo.  Times are approximate --
adjust based on how the conversation flows.

---

## Part 1: What We Built (5 minutes)

### The Problem (30 seconds)

The existing Socratic Oracle is a single-user system.  One global Python
dict holds the session state.  If two students connect at the same time,
they overwrite each other's conversations.  There is no way to know how
loaded the server is, and no support for design image critique.

We were asked to solve two things: make it work for 250 students, and
add a visual design critique mode for architecture students.

### Deliverable 2: Multi-User Infrastructure (2 minutes)

Walk through these three files:

**Session Manager** (`deliv2_session_manager.py`):
- Each user gets a UUID-based session.  Sessions live in a Python dict
  guarded by asyncio.Lock -- one dict entry per active user.
- An asyncio.Semaphore (capped at 10 by default) limits how many GPU
  inference calls run simultaneously.  When all 10 slots are taken,
  additional requests queue up in FIFO order.
- Users who are queued get a status message: "you are in queue,
  position X, estimated wait Y seconds" -- not a timeout or a crash.
- The estimated wait is calculated using an exponential moving average
  of recent inference durations.

**Admin Dashboard** (`deliv2_admin_dashboard.py`):
- Hit `/admin/dashboard` in a browser -- you see active sessions,
  inference slots used, queue depth, and estimated wait.
- It is a single HTML page with inline CSS.  Auto-refreshes every 5
  seconds via a `<meta>` tag.  No JavaScript framework needed.
- There is also `/admin/api/stats` that returns the same data as JSON
  for programmatic access.

**Resource Estimation** (`deliv2_resource_estimation.py`):
- Models realistic peak concurrency: 250 students does not mean 250
  simultaneous users.  This is an async tutoring tool, not a live
  lecture.  We estimate ~8% peak concurrency (about 20 users).
- Calculates GPU requirements for four scenarios: single A100 80 GB
  (text only), single A100 80 GB (text + vision), 2x A100 40 GB, and
  RTX 4090 for dev.
- Bottom line: a single A100 80 GB handles the pilot comfortably.
  Adding vision reduces headroom but remains feasible.

### Deliverable 3: Visual Design Critique (2 minutes)

Walk through these three files:

**Vision Client** (`deliv3_vision_client.py`):
- Wraps Ollama's multimodal API to send base64-encoded images + text
  to LLaVA.
- The system prompt is specifically written for architectural critique --
  it asks about spatial organization, circulation paths, structural
  logic, and material choices.  A generic "describe this image" prompt
  produces shallow captions; the domain-specific prompt is what makes
  the responses useful.
- Supports both synchronous and async streaming, matching the existing
  OllamaClient interface.

**Vision Routes** (`deliv3_vision_routes.py`):
- `POST /api/vision/analyze`: upload an image + text, get a Socratic
  design critique back.
- `POST /api/vision/analyze-stream`: same thing but streamed as
  Server-Sent Events so the frontend can show tokens as they arrive.
- Images are saved per-session under `uploads/sessions/<session_id>/`
  for later reference.

**Schema Extension** (modified `conversation_manager.py`):
- Added an optional `image` field to conversation messages.  When
  present, it stores the filename, MIME type, and server-side path.
- Voice-only conversations are completely unchanged -- the field is
  simply absent.

**Compute Assessment** (`deliv3_compute_assessment.py`):
- LLaVA 7B (4-bit) needs ~8 GB VRAM on top of LLaMA's ~6 GB.
- On a single A100 80 GB, both fit with ample room for concurrent
  KV caches.
- Vision inference is roughly 50% slower than text-only because of
  image token processing (~576 tokens per image).

### What I Learned (30 seconds)

Coming in, I had Flask experience and ML background, but this was my
first time doing:

- **Async concurrency control in Python** -- asyncio.Semaphore is
  genuinely elegant for rate-limiting without external dependencies.
- **GPU capacity planning** -- VRAM is the bottleneck, not CPU.
  Modeling realistic peak concurrency (8%, not 100%) is crucial.
- **FastAPI routers for modular architecture** -- similar to Flask
  blueprints but with better type safety.  I could bolt on entire
  subsystems without touching the original routes.
- **Prompt engineering for VLMs** -- the difference between a generic
  prompt and a domain-tuned one is night and day for output quality.
- **Backward-compatible schema design** -- making the image field
  optional instead of creating a new message type saved us from
  touching any existing parsing code.

---

## Part 2: Decisions We Made (5 minutes)

For each decision, briefly state what we chose, the main alternative,
and why we went with our approach.

### 1. Session store: Python dict vs. Redis

| | Dict + Lock | Redis |
|---|---|---|
| Pros | Zero dependencies, simple, fast for single-process | Survives restarts, works across workers |
| Cons | Lost on restart, single-process only | Extra service to deploy and maintain |
| **Verdict** | Good enough for a 250-student pilot on one FastAPI worker. Move to Redis if we ever run multiple workers. |

### 2. Concurrency control: asyncio.Semaphore vs. Celery

| | Semaphore | Celery + RabbitMQ |
|---|---|---|
| Pros | Built-in, lightweight, gives us queue position | Industry standard, retries, monitoring |
| Cons | In-process only, no persistence | Massive operational overhead |
| **Verdict** | We cap at 10 GPU requests.  Celery is bringing a tank to a knife fight. |

### 3. Admin dashboard: inline HTML vs. React vs. Grafana

| | Inline HTML | React SPA | Grafana + Prometheus |
|---|---|---|---|
| Pros | Self-contained, no build step | Interactive, modern | Beautiful charts, alerting |
| Cons | Limited interactivity | Needs Node, build pipeline | Two more services |
| **Verdict** | One admin checking on a pilot.  An f-string with CSS is the right level of investment. |

### 4. Vision model: LLaVA vs. Qwen-VL vs. GPT-4V

| | LLaVA 7B | Qwen-VL | GPT-4V |
|---|---|---|---|
| Pros | Runs on Ollama (already in stack), 8 GB VRAM | Strong multilingual | Best quality |
| Cons | Weaker than cloud models | Heavier (14B+) | Cost, privacy, cloud dependency |
| **Verdict** | LLaVA fits our existing Ollama stack, fits on one GPU alongside the text LLM, and is good enough for Socratic probing. |

### 5. Image upload: multipart form vs. base64 JSON

| | Multipart | Base64 in JSON |
|---|---|---|
| Pros | Standard, efficient | Simpler API surface |
| Cons | Two content types | 33% larger payload |
| **Verdict** | Multipart is the standard.  For a 5 MB architectural rendering, saving 1.7 MB of transfer matters. |

### 6. Schema extension: optional field vs. new message type

| | Optional `image` field | Separate `image_message` type |
|---|---|---|
| Pros | Backward compatible, zero changes to existing code | Clean type separation |
| Cons | Slightly less explicit | Every consumer needs to handle two types |
| **Verdict** | Optional field.  Existing voice-only conversations work without any changes. |

### 7. Queue position: approximate vs. exact ordering

| | Approximate (total depth) | Exact ordered list |
|---|---|---|
| Pros | Simple, one atomic counter | Perfectly accurate |
| Cons | Two users might see the same position | Extra bookkeeping, another lock |
| **Verdict** | For a pilot with modest concurrency, "you are roughly #3 in line" is honest enough. |

---

## Part 3: What We Would Do with More Time (5 minutes)

Ranked roughly by impact:

### High Priority

1. **Session garbage collection**
   Right now sessions live until explicitly removed.  A background
   asyncio task that reaps sessions inactive for >30 minutes would
   prevent memory leaks during long deployments.  Straightforward to
   implement -- maybe 2 hours of work.

2. **Runtime GPU profiling**
   Our VRAM and latency numbers are based on published specs.  Running
   actual benchmarks on the target HPC hardware with torch.cuda memory
   snapshots would give us ground truth.  This is critical before
   committing to a GPU allocation for the semester.

3. **Conversation-aware vision analysis**
   Right now each `/api/vision/analyze` call is stateless.  Wiring it
   into the SessionManager so the VLM sees the prior conversation
   history would make multi-turn design critique much more coherent.
   "You mentioned circulation in your previous response -- does this
   new section drawing address that?"

### Medium Priority

4. **Multi-image support**
   Let students upload a floor plan AND a section drawing in the same
   turn.  LLaVA supports multiple images in the `images` list.  The
   VLM could then reason across both: "your double-height space in
   the section does not appear in the plan -- can you explain?"

5. **RAG over building codes**
   Augment the vision critique prompt with relevant building
   regulations (e.g. UGC means-of-escape corridor widths) retrieved
   from a vector store.  This grounds the Socratic questions in real
   constraints rather than generic design principles.

6. **Dashboard authentication**
   HTTP Basic Auth or an API-key check on the admin routes.  Trivial
   to implement but important before any real deployment.

7. **WebSocket queue notifications**
   Replace client polling with a lightweight WebSocket that pushes
   queue position updates in real time.

### Lower Priority / Research

8. **Redis session store**
   Only needed if we scale to multiple FastAPI workers behind a load
   balancer.  Not necessary for the pilot but would be the first
   thing to do for production.

9. **Fine-tuning LLaVA on architectural corpora**
   Train on a dataset of annotated architectural images + expert
   design critiques to improve domain vocabulary and spatial reasoning.
   This is a research project in itself but would dramatically improve
   critique quality.

10. **Adaptive concurrency via pynvml**
    Dynamically adjust the semaphore cap based on real-time GPU memory
    pressure.  If VRAM usage spikes above 90%, temporarily reduce the
    cap; if it drops, increase it.

---

## Closing (30 seconds)

The code is commented, the decisions are documented, and someone can
pick this up and run it without asking me questions.  The architecture
is modular -- every new feature is a separate file with a `deliv2_` or
`deliv3_` prefix, wired into `app.py` through FastAPI routers.  Nothing
in the original codebase was broken; we only extended.
