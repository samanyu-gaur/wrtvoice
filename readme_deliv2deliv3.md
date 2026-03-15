# Deliverables 2 & 3 -- README

This document covers everything added for Deliverables 2 and 3 of the
Socratic Oracle paid work trial.  It is written for someone picking up
the codebase cold -- if you can read this file and run the server without
asking me any questions, I have done my job.

---

## Table of Contents

1. [What We Built](#what-we-built)
2. [New Files](#new-files)
3. [Modified Files](#modified-files)
4. [New API Endpoints](#new-api-endpoints)
5. [Design Decisions and Alternatives](#design-decisions-and-alternatives)
6. [What I Learned](#what-i-learned)
7. [Future Work](#future-work)

---

## What We Built

### Deliverable 2: Session Management & Capacity Dashboard

The original codebase supported exactly one user at a time -- a single
global Python dict held the session state.  We replaced that with:

- **SessionManager** (`deliv2_session_manager.py`): a multi-user session
  store that assigns each user a UUID-based session ID.  Sessions are
  stored in an in-memory dict guarded by asyncio.Lock.

- **Inference concurrency control**: an asyncio.Semaphore caps
  simultaneous GPU inference requests at a configurable limit (default: 10).
  Requests that exceed the cap are held in a FIFO queue.  Users receive a
  status update with their approximate queue position and estimated wait
  time, rather than a timeout or crash.

- **Admin Dashboard** (`deliv2_admin_dashboard.py`): a single-page HTML
  dashboard served at `/admin/dashboard` that auto-refreshes every 5
  seconds and displays active sessions, inference slot usage, queue depth,
  and estimated wait time.  A JSON API at `/admin/api/stats` is also
  available for programmatic access.

- **Resource Estimation** (`deliv2_resource_estimation.py`): a standalone
  module that models realistic peak concurrency for 250 HKU students and
  calculates GPU requirements across four hardware scenarios (single A100
  80 GB, single A100 80 GB with vision, 2x A100 40 GB, RTX 4090 for dev).

### Deliverable 3: Visual Design Critique Extension

Architecture students can now upload images of their design work (floor
plans, sections, renderings, model photos) and receive Socratic critique:

- **VisionClient** (`deliv3_vision_client.py`): a client for LLaVA (served
  via Ollama) that accepts a base64-encoded image plus text and returns a
  Socratic response about the design.  The system prompt is specifically
  tuned for architectural design critique -- it asks about spatial
  organization, circulation, structural logic, and material choices.

- **Vision API Routes** (`deliv3_vision_routes.py`): two endpoints:
  - `POST /api/vision/analyze` -- synchronous critique
  - `POST /api/vision/analyze-stream` -- streaming via Server-Sent Events

- **Schema Extension**: the conversation JSON schema now supports an
  optional `image` field on any message.  Voice-only conversations are
  completely unchanged.

- **Compute Assessment** (`deliv3_compute_assessment.py`): documents the
  VRAM, latency, and concurrency impact of adding LLaVA alongside the
  existing Whisper + LLaMA stack.

---

## New Files

All new files are prefixed with `deliv2_` or `deliv3_` for clarity.

| File | Deliverable | Purpose |
|------|-------------|---------|
| `modules/deliv2_session_manager.py` | 2 | Multi-user session store + concurrency semaphore |
| `modules/deliv2_admin_dashboard.py` | 2 | Admin HTML page + JSON stats API |
| `modules/deliv2_resource_estimation.py` | 2 | GPU allocation calculator for 250-student pilot |
| `modules/deliv3_vision_client.py` | 3 | LLaVA client for image + text critique |
| `modules/deliv3_vision_routes.py` | 3 | FastAPI routes for image upload and analysis |
| `modules/deliv3_compute_assessment.py` | 3 | VLM memory/latency/concurrency impact analysis |

---

## Modified Files

| File | What Changed |
|------|-------------|
| `app.py` | Added imports for all new modules; instantiated SessionManager, admin dashboard, and vision routes; added `/api/resource-estimate`, `/api/compute-assessment`, and multi-user session CRUD routes |
| `modules/conversation_manager.py` | Extended `add_message()` with optional `image` parameter for the vision extension |
| `modules/__init__.py` | Added exports for new modules |

---

## New API Endpoints

### Deliverable 2

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/dashboard` | HTML admin monitoring page |
| GET | `/admin/api/stats` | System metrics as JSON |
| POST | `/api/sessions` | Create a new multi-user session |
| GET | `/api/sessions/{id}` | Get session state |
| DELETE | `/api/sessions/{id}` | End and remove a session |
| GET | `/api/sessions/{id}/queue-position` | Check queue position |
| GET | `/api/resource-estimate` | GPU allocation report |

### Deliverable 3

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/vision/analyze` | Image + text design critique |
| POST | `/api/vision/analyze-stream` | Streaming design critique (SSE) |
| GET | `/api/compute-assessment` | VLM compute impact report |

---

## Design Decisions and Alternatives

Every new file contains detailed inline comments explaining what alternative
approaches existed and why we chose the path we did.  Here is a summary:

### Session storage: in-memory dict vs. Redis vs. database
We chose a plain dict with asyncio.Lock.  Redis would be needed if we ran
multiple FastAPI workers behind a load balancer, but for a single-process
pilot serving 250 students, the extra infrastructure is not justified.

### Concurrency control: asyncio.Semaphore vs. Celery vs. thread pool
Semaphore gives us rate limiting with queue-position feedback entirely
within the async event loop.  Celery + RabbitMQ would be massive
operational overhead for a pilot that caps at 10 concurrent GPU requests.

### Admin dashboard: inline HTML vs. Jinja2 vs. React
A single f-string HTML page with inline CSS and a meta-refresh tag. No
build step, no client-side JS framework.  For one admin checking on a
pilot, this is the right level of investment.

### Vision model: LLaVA vs. Qwen-VL vs. InternVL vs. cloud API (GPT-4V)
LLaVA 1.5 7B via Ollama.  It runs on hardware we already have, integrates
with the Ollama-based stack, and fits in ~8 GB VRAM.  GPT-4V is better
but introduces cost, privacy, and cloud dependency concerns.

### Image upload: multipart form vs. base64 JSON vs. presigned URL
Multipart form upload is the standard approach for file uploads and avoids
the 33% payload inflation of base64 encoding.

### Conversation schema: optional field vs. separate message type
An optional `image` dict on the existing message format.  This is fully
backward-compatible -- voice-only conversations do not change at all.

---

## What I Learned

As a first-year CompEng student who has worked with Flask and ML before,
the main things I took away from this work:

1. **asyncio is underrated for concurrency control.**  I expected to need
   Celery or Redis for queue management, but asyncio.Semaphore handles
   the pilot's scale cleanly and the code stays in one process.

2. **Capacity planning for GPU workloads is a different discipline** from
   web app scaling.  VRAM is the bottleneck, not CPU or network.  "250
   students" does not mean 250 simultaneous users -- realistic peak
   concurrency modeling matters.

3. **FastAPI's router system is excellent for modular extensions.**  I
   bolted on the admin dashboard and vision endpoints without touching the
   original routes.  The `include_router` pattern is similar to Flask
   blueprints but with better typing.

4. **Prompt engineering is the highest-leverage time investment for VLMs.**
   A generic "describe this image" prompt produces useless output.  The
   domain-specific Socratic design critique prompt took several iterations
   to get right.

5. **Backward compatibility should be a design constraint, not an
   afterthought.**  Making the image field optional (rather than creating
   a new message type) meant zero changes to existing conversation
   parsing code.

---

## Future Work

If we had more time, here is what we would do next (roughly in order of
impact):

1. **Session garbage collection**: a background task that reaps sessions
   inactive for >30 minutes to prevent memory leaks.

2. **Redis session store**: needed if we scale to multiple FastAPI workers
   behind a load balancer.

3. **Runtime GPU profiling**: replace our static VRAM estimates with
   actual torch.cuda measurements on the target HPC hardware.

4. **Multi-image support**: let students upload a floor plan and a section
   drawing in the same turn so the VLM can reason across both.

5. **RAG over building codes**: augment the vision critique prompt with
   relevant building regulations (e.g. UGC means-of-escape widths) so
   questions are grounded in real constraints.

6. **Dashboard authentication**: HTTP Basic Auth or API-key protection on
   the admin page before any real deployment.

7. **WebSocket queue notifications**: push real-time queue position
   updates to the client instead of having them poll.

8. **Per-user rate limiting**: prevent a single student from monopolizing
   inference slots under high load.

9. **Fine-tuning LLaVA on architectural corpora**: improve domain-specific
   vocabulary and spatial reasoning for architectural images.

10. **Adaptive concurrency**: dynamically adjust the semaphore cap based
    on real-time GPU memory pressure via pynvml.
