# badger

**WARNING: This is a prototype, not a tested production service.**

Badger is a prototype service that returns a count of the number of annotations
visible to a given Hypothesis user on a URL. It was created to answer some
engineering questions about replacing the `/api/badge` endpoint in
[h](https://github.com/hypothesis/h) which provides the annotation count badge
on the Chrome and Firefox extensions.

## Goals

- Reduce load on the h service and shared infrastructure (Postgres DB,
  Elasticsearch)
- Scale with the increasing number of users of the Chrome extension without
  substantial cost increases
- Possible future goal: enable the same functionality in a way that doesn't require
  the user's browser to expose their browsing history to us

## Design

For an explanation of how the service works, see [the design
document](docs/design.md).

## Running the service

badger requires Python 3.6+, a running Redis server and an h service to connect
to. It makes requests to the h API and the h service's associated Elasticsearch
service. You can start Redis in a container using:

```
docker create --name redis -p 6379:6379 redis
docker start redis
```

Assuming you are running a local development build of h on localhost, you can
start the dev server using:

```
make dev
```

You can configure the services that badger connects to by setting the
`REDIS_HOST`, `REDIS_PORT`, `ELASTICSEARCH_URL` and `H_API_URL` environment
variables.

## Interacting with the Redis DB

To interact directly with Redis from the Python REPL, run `make redis-py-shell`
and use the `redis` object. For example:

```
make redis-py-shell

# Print memory usage info
> redis.info()

# Empty the cache
> redis.flushdb()
```

See the [Redis command reference](https://redis.io/commands) for documentation
about available commands.
