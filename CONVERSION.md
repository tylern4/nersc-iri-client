# Converting `sfapi_client` to an IRI client

This document captures the decisions made while turning
[NERSC/sfapi_client](https://github.com/NERSC/sfapi_client) — a Python client
for the long-lived Superfacility API (`api.nersc.gov`) — into **`iri_client`**,
a client for the new IRI API (`api.iri.nersc.gov`). It is the "how to convert"
guide and design record in one: each section names a difference between the two
APIs, says what `sfapi_client` did, and what `iri_client` does instead.

IRI = *Integrated Research Infrastructure* API, versioned at
`https://api.iri.nersc.gov/api/v1`. Where a port keeps behavior or naming
identical, the code comments say so with a "mirrors ``sfapi_client``" note.

---

## 1. Authentication: drop authlib, use a static bearer token

| | sfapi_client | iri_client |
|---|---|---|
| Flow | Private-key JWT, client-credentials, OAuth2 token endpoint | Static bearer token |
| Discovery | `client_id`/`secret`/`key` args, `~/.superfacility/*` files | `access_token` arg → `IRI_API_TOKEN` env → `~/.ssh/nersc-token` |

The Superfacility API has a real OAuth2 token endpoint
(`https://oidc.nersc.gov/c2id/token`) that mints short-lived access tokens, so
`sfapi_client` shells out to `authlib` to fetch and refresh them. IRI has **no
token endpoint**: credentials are issued out-of-band and sent as
`Authorization: Bearer <token>` on every request. `authlib` and the whole
`_read_client_secret_from_file` machinery are therefore dropped; token
resolution is a plain priority list in `AsyncClient._get_token`.

### Design decision

Wire up a `machine`-style *services* slot so a token-issuing service can be
queried later without changing the client surface.

- Vastly simpler: the constructor takes one optional string, not client
  credentials plus a file protocol for them.
- Resolution is **lazy**. Public endpoints (`facility`, `status/*`,
  `compute/resources`, `filesystem/resources`) work with no token at all, and a
  descriptive `AuthError` is raised only when a privileged call needs
  credentials. This mirrors how `sfapi_client` treats public status endpoints.

---

## 2. Machine enum → resource discovery by UUID

`sfapi_client` knows one machine per environment: `Machine.perlmutter` maps to a
stable resource *name* (`"perlmutter"`), and the compute/storage routes are
`status/perlmutter`, `computes/...`, etc.

IRI **does not model a fixed set of machines**. Resources are dynamic UUIDs
exposed by two public discovery endpoints:

- `GET /compute/resources` → e.g. `jobs=3cf3c048-…`, `compute=94351904-…`
- `GET /filesystem/resources` → e.g. `scratch=43d8f6c0-…`, `common=7e07a611-…`

`iri_client` therefore replaces the `Machine` enum with resource lookup:

```python
await client.compute_resources()      # List[Resource]
await client.filesystem_resources()
await client.compute("jobs")          # bind by name, group, or id
await client.filesystem("scratch")
```

`AsyncClient._match_resource` resolves by `id`, `group`, or `name`, and raises
`ResourceLookupError` with the available resources when the match is
ambiguous. The default names (`"jobs"` for compute, `"scratch"` for
filesystem) are what the current IRI deployment expects for job submission and
home scratch space; they are overridable.

The well-known names are also available as `str`-based enums, exported from the
package root, so callers can refer to them without string literals:

```python
from iri_client import (
    Client,
    ComputeResourceName,
    FilesystemResourceName,
)

with Client() as client:
    compute = client.compute(ComputeResourceName.jobs)
    fs = client.filesystem(FilesystemResourceName.scratch)
```

- `ComputeResourceName` → `jobs`, `compute`
- `FilesystemResourceName` → `scratch`, `homes`, `common`, `cfs`, `dtns`,
  `jobs`, `compute`, `login`

`client.compute()`/`client.filesystem()` accept an enum member or a plain
string (or a resource `id`). Implementation note: a `str`-based enum's
`str(member)` yields `"EnumName.member"`, not the value, so `_match_resource`
unwraps via `.value` when given an enum. Because the `_async` and `_sync`
variants define their own enum classes, an enum from either module is accepted
by both clients (matching happens on `.value`).

> Note: the object model is still machine-centric — `site`/`resource`/`facility`
> is how IRI describes Perlmutter. We kept the *concept* (a compute site you
> submit jobs to), but it is indexed by UUID, not a hard-coded name.

---

## 3. Router renames

The sfapi property names are inherited by user code everywhere, so where the IRI
router is conceptually the same we kept the property and changed the URL; where
it is different we renamed the property.

| sfapi_client property/router | iri_client property/router | Why |
|---|---|---|
| `client.api` (`meta/changelog`, `meta/config`) | `client.facility` (`facility`, `facility/sites`) | IRI has no `meta` router; the facility model is the top object |
| `client.resources` (`status/outages`, `status/notes`, `status/...`) | `client.status` (`status/resources`, `status/events`, `status/incidents`) | IRI replaces outages/notes with a resource event/incident model |
| `client.storage` | `client.filesystem` | IRI calls the router `filesystem`; operations no longer go through Globus |
| `client.projects()` | `client.account.projects()` | IRI calls the router `account`; project + layered allocations live there |

### Survival

- **Outages/notes → incidents/events.** `sfapi` exposed `outages`,
  `planned_outages`, and `notes` scoped by resource name. IRI models status
  differently: `status/resources` gives resources + `current_status`,
  `status/events` gives status changes, `status/incidents` gives the incidents
  that cause them. `AsyncStatus.statuses()` reproduces the "name → status" map
  that made `sfapi`'s `resources.status()` convenient.

- **`user()` / `group()` are dropped.** The Superfacility API has `user` and
  `group` routers. IRI has no equivalent, so `client.user()`/`client.group()`
  are gone. Your identity is discoverable indirectly via
  `account/projects` (only the projects you belong to are returned).

---

## 4. Job model: one `Job`, not squeue/sacct split

`sfapi_client` models the two views the Superfacility backend exposes as
separate types: `AsyncJobSqueue` (live scheduler view) and `AsyncJobSacct`
(accounting view), so a job you find in the queue has different fields than one
you query from accounting.

IRI collapses that: `POST /compute/job/{resource_id}` returns
`{"id": "…", "status": {"state": "queued"}}`, and
`GET /compute/status/{resource_id}/{job_id}` returns a single `Job` whose
`status` carries the backend details:

```json
{
  "id": "57749788",
  "status": {
    "state": "completed",
    "exit_code": 0,
    "message": "...",
    "meta_data": { "...full squeue/sacct dict..." }
  }
}
```

`iri_client` uses one `AsyncJob` type with a `JobStatus` (`state`, `time`,
`message`, `exit_code`, `meta_data`). The `meta_data` clause is the backend
(scheduler *or* accounting) — exactly the fields you previously split across
`JobSqueue`/`JobSacct`.

### State values

Both APIs expose the same scheduler states, but IRI spells one differently:

| State | sfapi | IRI |
|---|---|---|
| cancelled | `"pending"`/`"running"`/`"done"` (derived) | `queued`, `held`, `active`, `completed`, `failed`, `canceled` |
| spelling | — | IRI uses **`canceled`** (single L) throughout |

The `JobState`/`TaskStatus` enums follow the IRI OpenAPI spec, so cancellation
is `JobState.canceled` — a very common porting gotcha.

### `compute.run()` has no command runner

`sfapi`'s `Compute.run(name, command)` can literally run a shell command on the
login node via the `utilities` endpoint. IRI has **no command/utility
endpoint**, so that convenience cannot exist. The closest equivalent is a job
that writes stdout to a file:

```python
spec = JobSpec(
    name="hello",
    executable="/usr/bin/cat",
    arguments=["/etc/os-release"],
    stdout_path="/pscratch/sd/t/tylern/tmp/out.txt",
    attributes={"queue_name": "debug", "account": "m3792", "duration": 60},
    resources={"node_count": 1, "processes_per_node": 1},
)
job = await client.compute().submit(spec)
await job.wait()          # poll until completed / failed / canceled
```
Because `JobSpec` has `stdout_path`/`stderr_path`, you can tail the output file
afterwards with `filesystem.tail(out, lines=last)`. `iri_client` documents this
pattern rather than half-emulating a login-node shell.

---

## 5. Filesystem: synchronous ops → async task queue

This is the biggest behavioural difference.

- `sfapi_client.storage` talks directly to storage systems; list/stat/copy
  calls return results inline. `put` also proxies uploads to Globus.
- IRI routes **every** filesystem operation through an internal task queue.
  A request returns `TaskSubmitResponse` (`{"task_id", "task_uri"}`)
  immediately; the caller polls `GET /task/{task_id}` until the state is
  `completed`, `failed`, or `canceled`, then reads `result.output`.

`iri_client` models this with a first-class awaitable `AsyncTask` (mirroring
the `AsyncCommandTask` pattern in `sfapi`):

```python
task = fs.submit_mkdir(my_dir)   # submit and go
task2 = fs.submit_copy(a, b)     # enqueue another operation
await task                       # block on the first
```

Every operation ships in two flavours:

- `submit_*` → returns the `AsyncTask` so callers can poll, cancel, or batch it
- blocking form (e.g. `fs.mkdir(...)`) → awaits the task and returns
  `result.output` (or raises `IriError` on `failed`/`canceled`)

### `Storage.path()` / globus

`sfapi`'s `AsyncStorage` is built around Globus (path transfers, globbing,
`AsyncGlobusTransfer`). None of that exists in IRI — transfers are plain
`cp`/`mv` tasks on the filesystem resource — so everything Globus-shaped is
dropped. Path handles survive as `AsyncPath` / `RemotePath` (sync), wrapping the
same filesystem operations with a friendlier `path / "subdir"` API.

Upload is limited to 5 MB per the IRI API; anything larger belongs in the
filesystem (`cp`/`mkdir`/`rm` are still async tasks and work fine at scale).

---

## 6. codegen: one OpenAPI spec, no runtime job models

`sfapi_client` generates pydantic models from
`api.nersc.gov/api/v1.2/openapi.json` **and** hand-curated sample JSON responses
for of the job status (`scripts/run.py datacodegen`) because the Superfacility
API's enums carry no literal values and job output schemas are unstable.

IRI's `https://api.iri.nersc.gov/openapi.json` is self-contained: one generation
pass (`uv run python scripts/run.py models`) produces `_models/__init__.py`.
The only witness of the old pain is the same `_to_str_enum` docstring patch:
the IRI spec *also* omits literal values for its string enums, so generated
`Enum` classes are rewritten to `(str, Enum)`.

---

## 7. sync / async duality: unasync, unchanged

Both projects keep a single source of truth in `_async/` and generate `_sync/`
with `unasync` (`uv run python scripts/run.py unasync`). The token budget for
this is tiny (unlink `asyncio`, rewire `_ASYNC_SLEEP` → `_SLEEP`), and it is
why every model above has both an `AsyncX` and an `X` spelling — same as
`sfapi_client`.

Deliberate codegen-property notes:

- `AsyncPath` → `RemotePath` (matches sfapi naming); `AsyncTask` → `Task`
- `await job` works in async; in sync, `job.wait()` is the public API (the
  bare `await x` idiom is stripped by unasync and was therefore never relied
  upon for blocking).
- LSP "module xxx could not be resolved" warnings for `httpx`/`pydantic`/
  `typer` are false positives: the editor isn’t using the `uv`-managed venv.
  `uv run` is the single source of truth for dependency resolution.

---

## 8. Retry, polling, and error handling: same bones

- **Retry**: tenacity wrapper identical to sfapi — exponential backoff capped
  at `MAX_RETRY = 10` attempts on `429/502/503/504`, `TimeoutException`, and
  `ConnectError`.
- **Auth guard**: `check_auth` still exists in `_utils.py` and is used by the
  privileged conventions. Because token resolution is lazy, the guard raises
  `AuthError` (subclass of `IriError`, the renamed `SfApiError`) at call time,
  not construction time.
- **`wait_interval`**: the same polling knob as sfapi (`client.wait_interval`,
  default 10 s). IRI tasks usually complete in < 2 s, so filesystem-heavy
  callers may lower it.
- **Error payloads**: IRI task failures carry `{"error": "..."}`;
  `AsyncTask._wait` (and `AsyncJob._wait`) convert `failed`/`canceled`
  terminal states into `IriError` with the backend message.

---

## Migration cheat-sheet

| Old (sfapi_client) | New (iri_client) |
|---|---|
| `AsyncClient(client_id, secret, key=...)` | `AsyncClient(access_token=...)` (or `IRI_API_TOKEN` / `~/.ssh/nersc-token`) |
| `client.compute(Machine.perlmutter)` | `client.compute("jobs")` |
| `client.storage` | `client.filesystem()` |
| `client.projects()` | `client.account.projects()` |
| `client.resources.status(name)` | `client.status.statuses(name)` |
| `client.resources.outages()/notes()` | `client.status.incidents()/events()` |
| `client.api.changelog()/config()` | `client.facility.info()/sites()` |
| `Compute.submit(...)` | `Compute.submit(JobSpec(...))` (identical name, richer spec) |
| `job.status -> sacct/squeue` | `job.status.meta_data` (one dict) |
| `job.cancel()` | `job.cancel()` (identical) |
| `job.wait(timeout)` | `job.wait(timeout)` (identical) |
| `storage.ls/sat/cp/mkdir/...` | `filesystem.list/stat/copy/mkdir/...` |
| `compute.run(name, command)` | *not available* — submit + tail `stdout_path` instead |
| `SfApiError` | `IriError` (plus `AuthError`, `ResourceLookupError`) |