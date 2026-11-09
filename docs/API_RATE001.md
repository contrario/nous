# RATE001: the per-minute limits' 429

The NOUS API limits each route per client key per minute (slowapi
0.1.9 over limits, fixed window, in memory). When a route's limit
refuses a request, the reply is 429 RATE001. Since S472 it says when
to come back.

## The reply

    HTTP/1.1 429 Too Many Requests
    Retry-After: 37
    RateLimit-Policy: "route";q=200;w=60
    RateLimit: "route";r=0;t=37
    Content-Type: application/json

    {"error": "Rate limit exceeded", "code": "RATE001",
     "error_id": "<32 hex>", "retry_after": 37,
     "limit": "200 per 1 minute", "scope": "route",
     "work_started": false}

- "error" and "code" are where they were before S472, at the top
  level, unchanged; the other members are added. Every other refusal
  of the API (CAPn, BUSYn, TIMEOUTn, AUTH001) is {"detail": {...}};
  RATE001 keeps its envelope so that no client that reads it breaks.
- Retry-After is in seconds: the time until the limiter's window for
  this key and route resets, rounded up, at least 1 and at most the
  limit's window. If the window cannot be read, it is the whole
  window. A client that waits Retry-After seconds finds its next
  request admitted by this limit; the tests evidence this for the
  fixed and the moving window.
- retry_after in the body equals the header.
- RateLimit-Policy and RateLimit are the fields of
  draft-ietf-httpapi-ratelimit-headers-11, an Internet-Draft, not an
  RFC; their syntax may change. q is the limit's amount, w its window
  in seconds, r the requests left (0), t equals Retry-After.
- The work never started.

## The key

A limit is keyed by the client key and the route (the Limiter's
key_style "endpoint"). Before S472 it was keyed by the URL, so a route
with a path parameter (GET and PUT /v1/templates/{name}, POST
/v1/webhook/{channel}) kept one bucket per value.

## The log

One warning line per route per 60 s at most, on the "nous_api"
logger:

    rate_limit scope=<route> code=RATE001 limit=<limit>
    client=<8 hex> refused=<n> error_id=<32 hex>

client is a salted hash of the key (as the client cap's), never the
address; refused counts the refusals of that route since its last
line. slowapi's own warning, which names the key, is written nowhere.

## What it does not do

- No RateLimit fields on replies that are not refused.
- A request FastAPI refuses on its body (422) does not count against
  the limit; unchanged.
- No X-RateLimit- fields.
