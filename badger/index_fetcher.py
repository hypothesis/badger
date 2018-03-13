from asyncio import AbstractEventLoop, sleep

import aiohttp

from .h_client import HypothesisAPIClient
from .util import get_logger

logger = get_logger(__name__)


class Annotation:
    """
    An annotation fetched from h.

    This representation contains only the fields that are needed by the
    badger service.
    """

    def __init__(self, id, uri, groupid, userid, is_shared, created):
        self.id = id

        self.created = created
        self.groupid = groupid
        self.is_shared = is_shared
        self.uri = uri
        self.userid = userid

    @classmethod
    def from_api_ann(cls, api_ann):
        """
        Decode an annotation from the H API into an `Annotation`.
        """
        is_shared = bool([item for item in api_ann['permissions']['read'] if
                         item.startswith('group')])
        uri = api_ann['target'][0]['source']
        return cls(api_ann['id'], uri=uri, userid=api_ann['user'], groupid=api_ann['group'],
                   is_shared=is_shared, created=api_ann['created'])

    @classmethod
    def from_es_ann(cls, es_ann):
        """
        Decode an annotation from an Elasticsearch hit into an `Annotation`.
        """
        content = es_ann['_source']
        return cls(es_ann['_id'], uri=content['uri'], userid=content['user'],
                   groupid=content['group'], is_shared=content['shared'],
                   created=content['created'])


class AnnotationFetcher:
    """
    Interface for fetching annotations from h.
    """

    async def fetch_added_since(self, date):
        """
        Fetch annotations added since `date`.

        Annotations are sorted in ascending order of creation date.

        Returns iterable of `Annotation`.
        """
        ...

    async def fetch_deleted_since(self, date):
        """
        Fetch annotations deleted since `date`.

        Returns iterable of annotation ID.
        """
        ...


class HypothesisAPIFetcher(AnnotationFetcher):
    """
    Fetch annotations from the h API.
    """
    def __init__(self, h_api: HypothesisAPIClient) -> None:
        self.h_api = h_api

    async def fetch_added_since(self, date):
        """
        Fetch recently added annotations.

        The `date` parameter is ignored by `HypothesisAPIClient` as the h API
        does not supported it.
        """
        limit = 200
        offset = 0
        params = {'offset': offset,
                  'limit': limit,
                  'sort': 'created',
                  'order': 'desc'}

        retry_count = 3
        api_anns = []
        while retry_count > 0:
            try:
                search_rsp = await self.h_api.search(params)
                api_anns = search_rsp['rows']
                break
            except Exception as ex:
                logger.warn(f'search failed: {ex}')
                retry_count = retry_count - 1
        anns = [Annotation.from_api_ann(ann) for ann in api_anns]

        anns = sorted(anns, key=lambda ann: ann.created)
        for ann in anns:
            yield ann

    async def fetch_deleted_since(self, date):
        return
        yield  # Make this method a generator


class ElasticsearchFetcher(AnnotationFetcher):
    """
    Fetch annotations directly from the Elasticsearch index maintained by h.
    """
    def __init__(self, es_url, loop: AbstractEventLoop=None,
                 batch_fetch_delay=None):
        """
        :param es_url: Root URL of Elasticsearch server
        :param loop: Event loop to use with `aiohttp`
        :param batch_fetch_delay: Amount of time to sleep between fetching
                                  result batches. Use to reduce load on
                                  Elasticsearch service.
        """
        self._session = aiohttp.ClientSession(loop=loop)
        self._batch_fetch_delay = batch_fetch_delay

        # Number of hits to fetch from ES at once.
        self._batch_size = 1000

        self.es_url = es_url

    async def fetch_added_since(self, date):
        while True:
            params = {'sort': [{'created': {'order': 'asc'}}],
                      'size': self._batch_size}
            if date:
                params['query'] = {'range': {'created': {'gt': date}}}

            es_hits = await self._es_query(params)
            if len(es_hits) == 0:
                return

            if date:
                logger.info(f'fetched {len(es_hits)} annotations from ES added since {date}')
            else:
                logger.info(f'fetched {len(es_hits)} annotations from ES')

            def is_deleted(hit):
                return hit['_source'].get('deleted') is True

            anns = [Annotation.from_es_ann(hit) for hit in es_hits
                    if not is_deleted(hit)]
            date = sorted([ann.created for ann in anns])[-1]
            for ann in anns:
                yield ann

            if self._batch_fetch_delay:
                await sleep(self._batch_fetch_delay)

    async def fetch_deleted_since(self, date):
        # Not supported
        yield []

    async def _es_query(self, params):
        es_index = 'hypothesis'
        url = f'{self.es_url}/{es_index}/_search'
        rsp = await self._session.post(url, json=params)

        if rsp.status >= 400:
            details = await rsp.text()
            raise Exception(f'POST {url} with {params} failed: {rsp.status}, {details}')

        result = await rsp.json()
        return result['hits']['hits']
