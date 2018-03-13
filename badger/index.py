from asyncio import gather

from .util import get_logger, username_from_userid
from .uri import normalize_uri

logger = get_logger(__name__)


def uri_scope_key(uri, userid=None, group=None):
    """
    Return the (URI, scope) key associated with a given URI and scope.
    """

    normalized_uri = normalize_uri(uri)

    if userid:
        username = username_from_userid(userid)
        return f'{normalized_uri}|u:{username}'
    elif group:
        return f'{normalized_uri}|g:{group}'
    else:
        raise Exception('Group or userid must be set')


def uri_scope_key_for_ann(ann):
    """
    Return the (URI, scope) key associated with `ann`.
    """

    if ann.is_shared:
        key = uri_scope_key(ann.uri, group=ann.groupid)
    else:
        key = uri_scope_key(ann.uri, userid=ann.userid)

    return key


def count_key(uri_scope_key):
    return f'count|{uri_scope_key}'


class AnnotationCountIndex:
    """
    Index of annotation counts made on URLs.

    The index has the following schema:

      # Record of which URL scope an annotation has been indexed under.
      "ann|{ID}" => "{url_scope}"

      # Time-limited cache of profile + group info for a given API authorization
      # token.
      "profile|{token}" => "{'profile': {user profile},
                             'groups': {groups}"

      # Count of the number of annotations indexed under a given URL and scope.
      "count|{url_scope}" => "{annotation count}"

      # Book-keeping keys used by the indexer.
      "indexer|{name}" => "{value}"
    """

    def __init__(self, h_api_client, ann_fetcher, kv_store):
        self.ann_fetcher = ann_fetcher
        self.h_api = h_api_client
        self.kv_store = kv_store

    async def fetch_count(self, url, auth):
        """
        Retrieve a count of annotations made on `url`.

        Query the count index for the number of annotations made against `url`
        which are visible to a user identified by an authorization token `auth`.
        """
        principals_key = f'profile|{auth}'
        principals_val = self.kv_store.get_dict(principals_key)
        if not principals_val:
            [profile, groups] = await gather(self.h_api.profile(), self.h_api.groups())
            principals = {'profile': profile, 'groups': groups}
            self.kv_store.put_dict(principals_key, principals, expiry=10)
        else:
            profile = principals_val['profile']
            groups = principals_val['groups']

        keys = []
        userid = profile['userid']
        if userid:
            keys.append(count_key(uri_scope_key(url, userid=userid)))
        for g in groups:
            pubid = g['id']
            keys.append(count_key(uri_scope_key(url, group=pubid)))

        return self.kv_store.sum_counters(keys)

    async def incremental_index(self):
        last_indexed_key = 'indexer|last_indexed_date'
        last_indexed_date = self.kv_store.get(last_indexed_key)

        async for ann in self.ann_fetcher.fetch_added_since(last_indexed_date):
            self.index_annotations([ann])
            if last_indexed_date is None or ann.created > last_indexed_date:
                self.kv_store.put(last_indexed_key, ann.created)

        async for id_ in self.ann_fetcher.fetch_deleted_since(last_indexed_date):
            self.remove_annotation(id_)

    def index_annotations(self, anns):
        new_anns = 0

        for ann in anns:
            # Check if annotation is already indexed.
            ann_key = f'ann|{ann.id}'
            indexed_uri = self.kv_store.get(ann_key)
            if indexed_uri:
                continue

            # Index annotation.
            # TODO - Make the `inc_counter` and `put` commands below an atomic
            # op.
            new_anns += 1
            uri_scope_key = uri_scope_key_for_ann(ann)
            new_count = self.kv_store.inc_counter(count_key(uri_scope_key))
            self.kv_store.put(ann_key, uri_scope_key)
            logger.debug(f'incremented {uri_scope_key} to {new_count}')

        return new_anns

    def remove_annotation(self, id_):
        ann_key = f'ann|{id_}'
        uri_scope_key = self.kv_store.get(ann_key)
        if not uri_scope_key:
            return False

        # TODO - Make the `delete` and `dec_counter` commands below an atomic
        # op.
        self.kv_store.delete(ann_key)
        new_count = self.kv_store.dec_counter(count_key(uri_scope_key))
        logger.debug(f'incremented {uri_scope_key} to {new_count}')
        return True
