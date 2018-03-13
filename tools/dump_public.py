#!/usr/bin/env python

"""
Create a JSON dump of all annotations in the Public channel.
"""

from asyncio import get_event_loop
import json
import os
import sys
from typing import Any, AsyncGenerator, Dict

import aiohttp
from async_timeout import timeout


H_API = os.environ.get('H_API_URL', 'https://hypothes.is/api')


async def fetch(session, url, params):
    async with timeout(10):
        async with session.get(url, params=params) as rsp:
            if rsp.status != 200:
                raise Exception(f'Request failed with status {rsp.status}')
            return await rsp.json()


async def search() -> AsyncGenerator[Dict[str, Any], None]:
    """
    Fetch all annotations from the API.

    Due to the way the H search API's paging works, there may be some overlap in
    the responses. ie. it is possible for the same annotation to appear in more
    than one response.

    Return responses from the `/api/search` endpoint.
    """

    async with aiohttp.ClientSession() as session:
        # Current position when iterating over search results
        offset = 0
        limit = 200
        total = None

        # Number of concurrent requests to make to the API
        concurrent_reqs = 10

        while True:
            url = f'{H_API}/search'

            try:
                # Make `concurrent_reqs` concurrent search requests.
                chunks = []
                for i in range(0, concurrent_reqs):
                    params = {'offset': offset + (i * limit),
                              'limit': limit,
                              'sort': 'created',
                              'order': 'desc'}
                    chunks.append(fetch(session, url, params))

                # Wait for responses and increment offset.
                chunks = [await c for c in chunks]
                for chunk in chunks:
                    yield chunk
                    chunk_len = len(chunk['rows'])
                    if chunk_len == 0:
                        break
                    offset += len(chunk['rows'])
                    total = chunk['total']

                    print(f'fetched {offset} of {total} entries', file=sys.stderr)
            except Exception as ex:
                print(f'request failed {ex}', file=sys.stderr)
                continue


async def run():
    async for chunk in search():
        print(json.dumps(chunk, indent=2))
        # Marker to split resulting file on when re-reading, chosen as a string
        # that won't appear in the JSON output.
        print('\n""""\n')

loop = get_event_loop()
loop.run_until_complete(run())
