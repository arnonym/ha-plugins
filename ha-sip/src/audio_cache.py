from typing import Union, Literal, Optional
import hashlib
import os
import shutil

from log import log

cache_type = Union[Literal['audio_file'], Literal['message']]


def get_cached_file(should_cache: bool, cache_dir: Optional[str], file_or_message: cache_type, file_name_or_message: str) -> Optional[str]:
    if not should_cache:
        return None
    if not cache_dir:
        log(None, 'Warning: Caching enabled but no cache directory configured.')
        return None
    file_name = get_cache_file_name(cache_dir, file_or_message, file_name_or_message)
    if not os.path.isfile(file_name):
        log(None, 'Cache file not found: %s' % file_name)
        return None
    log(None, 'Using cache from file: %s' % file_name)
    return file_name


def cache_file(should_cache: bool, cache_dir: Optional[str], file_or_message: cache_type, file_name_or_message: str, file_to_cache: str) -> None:
    if not should_cache:
        return
    if not cache_dir:
        log(None, 'Warning: Caching enabled but no cache directory configured.')
        return
    file_name = get_cache_file_name(cache_dir, file_or_message, file_name_or_message)
    try:
        shutil.copyfile(file_to_cache, file_name)
    except Exception as e:
        log(None, 'Could not create cache file: %s' % e)
        return
    log(None, 'Created cache file: %s' % file_name)


def get_cache_file_name(cache_dir: str, file_or_message: cache_type, file_name_or_message: str) -> str:
    cache_key_content = file_or_message + '|' + file_name_or_message
    cache_key = hashlib.sha1(cache_key_content.encode()).hexdigest()[:10]
    file_name = cache_key + '.wav'
    return os.path.join(cache_dir, file_name)
