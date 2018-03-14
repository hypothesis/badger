## Overview

badger is a service that provides fast answers to the query "how many
annotations are there on this URL visible to me?"

It consists of an indexing process and a web server. The indexing process
creates a `(URL, scope) => annotation count` mapping from the annotations in an h
service's database. Each annotation is associated with a single _scope_ that identifies
who it is visible to. This is either the pubid of the annotation's group if it is shared, or the
username if the annotation is private.

The web server's lookup endpoint computes the set of _scopes_ visible to the
requester and fetches the count associated with each (URL, _scope_) tuple from
the key-value store.  The results are summed and returned.

## Architecture

The service consists of several pieces:

 - A **key-value store** that maps (URL, _scope_) keys to annotation counts.
   This uses [Redis](https://redis.io), an in-memory key-value store.
 - The **web service** that handles requests for annotation counts.
   This uses [Sanic](https://github.com/channelcat/sanic) [1]
 - The **indexing service** that fetches annotations from
   [h](https://github.com/hypothesis/h) and indexes them in the key-value store.

[1] Sanic is a Python HTTP server with support for async request handlers built
    on top of [asyncio](https://docs.python.org/3/library/asyncio.html).

## Authorization

In order to return counts that are appropriate for a given user, the service
needs to:

 1. Index all annotations, including those which are private and those in groups.
 2. Know what scopes (groups) are visible to a user making a request to the web
    service.

Since h does not provide a way for a trusted service to get all annotations, or
efficiently page over them, badger fetches data directly from Elasticsearch.

The client's authorization to badger's web service uses the same access tokens
that are used for the Hypothesis service. The service uses these access tokens
to make `/api/profile` and `/api/groups` requests to h in order to get the
scopes visible to the user. The profile + groups lookup results for a given
access token are cached for a short period to reduce load on h.

## Indexing service

The indexing service incrementally fetches and indexes annotations from h using
the following steps:

1. A batch of annotations are fetched, ordered by creation date ascending,
   starting from the last-indexed annotation.

2. Each annotation is mapped to a lookup key containing the normalized URI and
   current scope for the annotation.

3. The count associated with the lookup key in the key-value store is
   incremented, or set to 1 if no such key exists.

4. When all annotations in the batch are processed, the offset of the
   last-indexed annotation is recorded in the store.

### Caveats

There are significant caveats with the indexing in the current prototype which
will need addressing:

1. Counts are not updated when annotations are deleted.
2. Counts are not updated when annotations are moved from one URL to another.
3. Counts are not updated if an annotation is moved from one group to another.
   Note that this isn't currently possible to do in h.

See the "Addressing h limitations" section below for some ideas on resolving
these.

## Web service

The web service exposes a single endpoint to clients:

`/count?url={url}`

This returns the number of annotations visible to the current user on the given URL.

The `/count` endpoint computes counts as follows:

1. Fetch the user's profile and group list, either from h directly or from
   a time-limited cached copy in the key-value store
2. Generate a set of lookup keys based on the supplied URL and scopes visible
   to the user.
3. Fetch and sum the values associated with the lookup keys in the KV-store

The use of profile + group list caching in step (1) is essential since the whole
point of this service is to reduce load on h and its supporting infrastructure
(Postgres, Elasticsearch). If the user joins or leaves a group the cached copy
will have the wrong information for a short period of time, until the cache
entry expires. This means that the user may see incorrect counts for a URL
annotated in a group they just joined or left for a short period. I think this
is an acceptable limitation. We could reduce this delay by implementing explicit
invalidation somehow.

## Design alternatives

This section discusses some technical design alternatives.

### Caching only definitely-zero responses

The service described here serves all lookups from its cache. An alternative
that would be simpler to implement would be one that only serves requests with
definite zero responses from the cache, ie. returning zero when the URL has
never been annotated by anyone. For URLs that have been annotated at least once,
the request would proxy though to the `/api/badge` service.

This would alleviate most of the load from badge lookups on H, since the
majority of URLs that users visit have never been annotated.

It would be simpler to implement since there is no need to deal with user
permissions or deleted annotations. The service would only need to maintain the
set of normalized URIs that have ever been annotated in the key-value store.

### Access via h API vs direct to Postgres / Elasticsearch

The indexing and web serving processes could make requests via the H API
or go to the underlying datastores (Postgres, Elasticsearch) directly.

Access via the H API has the advantage of not requiring changes to badger if the
Postgres or Elasticsearch schemas change. It also enables H to handle
authorization. Finally dogfooding our own APIs helps surface limitations that
might be applicable to other use cases. However, it has the downside that any
requests to h increase load on h in addition to ES/PG.

Profile + groups lookups are currently done via requests to h and then cached,
but indexing is currently done via direct requests to Elasticsearch. This is
primarily because of limitations in the `/api/search` endpoint, which does not
provide:

1. An efficient way to query for annotations created since a given timestamp.
   Elasticsearch does support this operation itself via range queries on the
   `created` field and this is what badger uses internally.

2. A way for a trusted service to use priviledged credentials to enable it to
   fetch all annotations, including those which are private to users or in
   private groups.

We should definitely consider changing the paging API to make (1) more
efficient.

### Push vs pull updates

The indexing service currently _pulls_ annotation updates from Elasticsearch by
polling every few seconds, rather than having updates _pushed_ to it. This was
largely done for ease of implementation and building the initial index.

### Recording deletions

One way that the badger service could update counts when annotations are deleted
would be for the h service to record information about deleted annotations for a
period of time, consisting of an `(id, target_uri, userid, group_id,
deletion_date)` tuple, and exposing that information via an API, say
`/api/annotations/deleted?since={since}`.

## Implementation notes

The prototype uses the Sanic web server which allows the web service to leverage
Python 3's native async IO/coroutine support to serve new requests while other
in-flight ones are blocked making HTTP requests to H or Elasticsearch. No actual
benchmarking has yet been done to compare it to our typical Flask or Pyramid
setup.
