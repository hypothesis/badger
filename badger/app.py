from asyncio import AbstractEventLoop
import json
from time import sleep

import click
from sanic import Sanic
from sanic import response

from .h_client import HypothesisAPIClient
from .index import AnnotationCountIndex
from .index_fetcher import Annotation, ElasticsearchFetcher, HypothesisAPIFetcher
from .kv_store import KeyValueStore
from .util import error_response, get_logger, optional_env
from .util import run_async_task


app = Sanic()


@app.get('/count')
async def count(request):
    """
    Return the number of annotations on a given URL.
    """
    url = request.args.get('url')
    if url is None:
        return error_response('missing required parameter "url"')

    # Fetch user's username and groups.
    # These are cached in redis for a period of time to reduce the number of
    # requests made to "h".
    access_token = request.headers.get('Authorization')
    count = await request.app.ann_count_index.fetch_count(url, access_token)
    return response.json({'count': count})


@app.post('/delete/<id>')
async def delete(request, id):
    index = request.app.ann_count_index
    found = index.remove_annotation(id)
    return response.json({'removed': found})


@app.listener('before_server_start')
def before_start(app, loop):
    # Instantiate the count index client.
    # This is done as a "before_server_start" listener in order to be able to
    # pass Sanic's event loop to `_get_index`.
    app.ann_count_index = _get_index(loop)


def _get_index(loop: AbstractEventLoop=None):
    settings = {
        'es.url': optional_env('ELASTICSEARCH_URL', str,
                               'http://localhost:9200'),
        'es.fetch_from_es': optional_env('FETCH_FROM_ELASTICSEARCH',
                                         bool, True),
        'redis.host': optional_env('REDIS_HOST', str, '0.0.0.0'),
        'redis.port': optional_env('REDIS_PORT', int, 6379),
        'h.api': optional_env('H_API_URL', str,
                              'http://localhost:5000/api'),
    }

    logger = get_logger(__name__)
    logger.info(f'using Redis server {settings["redis.host"]}:{settings["redis.port"]}')
    logger.info(f'using H service {settings["h.api"]}')

    kv_store = KeyValueStore(redis_host=settings['redis.host'],
                             redis_port=settings['redis.port'])
    h_api_client = HypothesisAPIClient(settings['h.api'], loop=loop)

    if settings['es.fetch_from_es']:
        ann_fetcher = ElasticsearchFetcher(settings['es.url'], loop=loop,
                                           batch_fetch_delay=5.0)
    else:
        ann_fetcher = HypothesisAPIFetcher(h_api_client)
    ann_count_index = AnnotationCountIndex(h_api_client, ann_fetcher, kv_store)
    return ann_count_index


@click.group()
def cli():
    pass


@cli.command(help='Run the web server')
def server():
    app.run(host='0.0.0.0', port=8001)


@cli.command(help='Run the indexing server')
def indexer():
    async def run():
        index = _get_index()
        while True:
            await index.incremental_index()
            sleep(5)

    run_async_task(run())


@cli.command(help='Index annotations from a file')
@click.argument('path')
def index_from_file(path):
    async def run():
        logger = get_logger(__name__)
        index = _get_index()
        buffer = []
        indexed_count = 0

        for line in open(path):
            if '""""' in line:
                search_response = json.loads('\n'.join(buffer))
                anns = [Annotation.from_api_ann(ann) for ann in search_response['rows']]
                buffer = []
                index.index_annotations(anns)
                indexed_count += len(anns)

                logger.info(f'indexed {indexed_count} annotations from {path}')
            else:
                buffer.append(line)

    run_async_task(run())


if __name__ == '__main__':
    cli()
