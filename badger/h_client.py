from asyncio import AbstractEventLoop
import aiohttp
import requests


class HypothesisAPIClient:
    """
    API client for the "h" service.
    """

    def __init__(self, url, loop: AbstractEventLoop=None):
        self._routes = requests.get(url).json()['links']
        self._session = aiohttp.ClientSession(loop=loop)

    async def search(self, params={}):
        return await self._request('search', params=params)

    async def profile(self):
        return await self._request('profile.read')

    async def groups(self):
        return await self._request('groups.read')

    async def _request(self, route, params=None):
        path = route.split('.')
        entry = self._routes
        for p in path:
            entry = entry[p]
        url = entry['url']
        rsp = await self._session.get(url, params=params)

        if rsp.status >= 400:
            raise Exception(f'GET {url} failed: {rsp.status}')

        return await rsp.json()
