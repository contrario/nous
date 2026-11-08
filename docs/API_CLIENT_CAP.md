# API client cap

Seat S466. Marker in nous_api_server.py: `__s466_client_cap_v1__`.

## What it does

nous-api runs five routes on one bounded pool of worker threads
(option T, S465): POST /v1/compile, /v1/verify, /v1/skill/export,
/v1/run and /v1/diff. The client cap limits how many of that pool's
slots one client key may hold at the same time.

A request whose key already holds its cap is answered at once with
HTTP 429. Its work is not started and it does not wait for a slot.

## The client key

The key is slowapi's get_remote_address, the address uvicorn's
proxy-headers middleware leaves in the request, then:

- an IPv4 address is its own key;
- an IPv4-mapped IPv6 address (::ffff:a.b.c.d) is keyed as a.b.c.d;
- any other IPv6 address is keyed by its /64 network, so the
  addresses of one /64 share one cap;
- a loopback address (127.0.0.1, ::1) is exempt: it has no key and
  no cap, and stays under the pool and its 503 BUSY reply only;
- a value that is not an IP address is its own key.

The loopback exemption is there for a collapse of the key path: were
every visitor to arrive as a loopback address, one cap would throttle
the whole service. With the exemption the service falls back to the
behaviour of option T alone. A loopback request that carries
X-Forwarded-For logs one WARNING, at most once a minute, naming no
address: the sign that keys may have collapsed.

## The cap

The default is max(2, POOL // 4), where POOL is option T's pool size,
min(32, CPUs + 4). A host with 8 CPUs has a pool of 12 and a cap of 3.

NOUS_CLIENT_CAP in nous-api's environment sets it, read at import:

- unset: the default;
- 0: the cap is off;
- an integer n of 1 or more: a cap of n;
- anything else: the default, and one WARNING at import.

A change takes a restart of nous-api.

## The 429 reply

    HTTP/1.1 429 Too Many Requests
    Retry-After: 5
    RateLimit-Policy: "client";q=3;qu="concurrent-requests"
    RateLimit: "client";r=0

    {"detail": {"error": "compile not started: this client already
     has 3 requests in flight", "code": "CAP001",
     "error_id": "<32 hex>", "work_started": false,
     "scope": "client"}}

The codes, one per route:

| route            | code   |
|------------------|--------|
| /v1/compile      | CAP001 |
| /v1/verify       | CAP002 |
| /v1/skill/export | CAP003 |
| /v1/run          | CAP004 |
| /v1/diff         | CAP005 |

q is the cap; r=0 says none is left. RateLimit-Policy and RateLimit
are the fields of draft-ietf-httpapi-ratelimit-headers-11, an
Internet-Draft, not an RFC; their form may change. No partition key
is sent. Replies that are not a 429 of the cap do not carry them.

The server logs one WARNING per 429 with the route, the code, the
cap, the error_id and an 8-hex keyed hash of the key (a random salt
per process). The address itself is not logged.

## When a slot and a count are given back

A key's count is taken before the admission wait and given back
where the slot is: when the worker's thread ends (not when the reply
is sent), on a cancel of work that had not started, on a submit
failure, on the 503 BUSY reply, and on any exception during the
admission wait, a cancelled request included. A 503 TIMEOUT reply
does not give the count back: the thread may still run, and the
count stays until it ends.

## What it does not do

- It is not a rate over time. The per-minute limits (429 RATE001)
  are slowapi's and are not changed here.
- It does not tell clients apart behind one address: a NAT, an
  office or one /64 share one cap.
- It does not stop one party that sends from many addresses.
- It does not cover routes outside the five above.
