# Input validation & payload limits

Roadmap **E23-06**, MASTER_PROMPT §22. `bbz_core.api.schema` + `bbz_core.api.body_limit`.

The review report the acceptance criteria ask for: how every `/api/v1` write
endpoint constrains what a client may send.

## Strict request bodies

Every write body is a Pydantic model with `extra="forbid"` — an unknown field is
a **422**, not a silently-ignored value. That closes over-posting: a client
cannot set `is_admin`, `owner_id`, `version`, … just by adding it to the JSON,
even if a future handler starts reading that key.

New models subclass `bbz_core.api.schema.StrictModel`:

```python
from bbz_core.api.schema import StrictModel


class CreateFooIn(StrictModel):
    name: str = Field(min_length=1, max_length=200)
```

The older `model_config = ConfigDict(extra="forbid")` on a plain `BaseModel` is
equivalent and still in use across the codebase.

`tests/test_input_validation.py::test_every_api_v1_write_body_forbids_unknown_fields`
walks the live route table (`app.openapi()` / the router tree) and fails the
build if any `/api/v1` write body — direct, `list[...]`, or `... | None` — is not
strict.

### The one exception

`POST /api/v1/telephony/events` takes a raw `dict` — the inbound provider webhook
payload, whatever shape the switch sends. It is normalised downstream by
`bbz_core.infra.telephony_ingest`, is authenticated with a service-account
bearer token, and is body-size-capped like everything else. It is the single
entry in the contract test's `_RAW_BODY` allow-list.

## Field-level constraints

Beyond "no unknown fields", the models carry the obvious bounds — `min_length` /
`max_length` on strings, enums for closed vocabularies, `UUID` types for ids,
numeric ranges where relevant. Business validation (does this role exist, may
this user be assigned here) stays in the service layer and is **not** part of
this audit.

## Body size cap

`BodyLimitMiddleware` (outermost middleware) rejects any `POST` / `PUT` /
`PATCH` / `DELETE` whose body exceeds `BBZ_MAX_REQUEST_BODY_BYTES`
(**default 1 MiB**) with **413** and the uniform error envelope
(`code: "payload_too_large"`). It is checked before auth, CSRF, or routing, so a
hostile client cannot pin memory or CPU with a huge upload.

- A declared `Content-Length` over the cap is rejected immediately.
- A body with no / an understated length is counted as it streams and cut off at
  the same limit.
- `0` disables the cap.

This is also the guard that will cover file uploads once the platform grows any
(there are none today — every write body is JSON).

## Not in scope

- Reshaping the `422` body. FastAPI's default `{"detail": [...]}` is unchanged;
  callers already branch on the status code, not the envelope.
- Per-endpoint size limits. The global cap is generous enough that no endpoint
  needs a tighter one yet; `BodyLimitMiddleware` takes a single limit today.
- Rate/complexity limits on validated-but-expensive payloads — that is
  E23-04's and the service layer's concern.
