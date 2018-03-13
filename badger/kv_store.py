import json
from redis import StrictRedis


def tostr(bytes):
    return bytes.decode()


class KeyValueStore:
    """
    Interface to the Redis store used by the annotation count index.

    This provides an abstraction over the Redis store to facilitate testing etc.
    """

    def __init__(self, redis_host, redis_port):
        self.redis = StrictRedis(redis_host, redis_port, db=0)

    def inc_counter(self, key):
        return self.redis.incr(key)

    def dec_counter(self, key):
        return self.redis.decr(key)

    def sum_counters(self, keys):
        counts = [int(count) for count in self.redis.mget(keys) if count]
        return sum(counts)

    def put_dict(self, key, value, expiry=None):
        if expiry is None:
            self.redis.set(key, expiry, json.dumps(value))
        else:
            self.redis.setex(key, expiry, json.dumps(value))

    def get_dict(self, key):
        return json.loads(self.redis.get(key) or 'null')

    def get(self, key, typ=tostr):
        val = self.redis.get(key)
        if val is None:
            return None
        return typ(val)

    def put(self, key, value):
        self.redis.set(key, value)

    def delete(self, key):
        self.redis.delete(key)
