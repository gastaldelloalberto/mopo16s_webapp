from redis import Redis
from json import dumps, loads


cache_celery = Redis(db=0, decode_responses=True)
cache = Redis(db=1, decode_responses=True)


def bool_encoder(value):
    if value:
        return '1'
    return ''


def cached_string(key_prefix, ttl, key_pos=0, key_suffix_pos=None, encoder=dumps, decoder=loads, get_from_cache=True):
    """
    Returns a decorator function.
    
    The function retrieves the value from the selected hash field in cache.
    If it doesn't exist call the decorated function, then store in cache the retrieved value.
    Returns the value.
    
    @param key_prefix:			Cache key suffix.
    @param key_pos:	        	[Optional] Position of the obj_id in args (args[key_suffix_pos]). Integer. Default: 1.
    @param key_suffix_pos:  	[Optional] None: obj2_id not present,	Integer: obj2_id in args[key_suffix_pos]. Default: None.
    @param encoder:				[Optional] Coding function to store the value as a string. Default: "json.dumps".
    @param decoder:				[Optional] Decoding function to retrieve the value from a string. Default: "json.loads".
    @param ttl:					[Optional] Time to live. Default: c.CACHE_TIME_GROUP_CFG.
    @param get_from_cache:		[Optional] If False perform only cache update, the value is retrieved from the function even if the value exists in cache. Default: True.
    
    Key is composed in this way:	args[key_suffix_pos] + "." + key_suffix  [ + "." + args[key_suffix_pos] ]
    """
    
    # define the decorator for this field
    def decorator(get_from_db_func):
        def wrapper(*args, **kwargs):
            key = key_prefix + ':' + args[key_pos]
            if key_suffix_pos is not None:
                key += ":" + args[key_suffix_pos]
            # skip if only cache update is needed
            if get_from_cache:
                # get from cache
                cache_value = cache.get(key)
                # if exists in cache
                if cache_value is not None:
                    # return the value decoded (or not)
                    if decoder:
                        return decoder(cache_value)
                    return cache_value
            # get value from decorated function
            value = get_from_db_func(*args, **kwargs)
            # store in cache coded (or not) value
            if encoder:
                cache.set(key, encoder(value), ttl)
            else:
                cache.set(key, value, ttl)
            # return the value
            return value
        
        return wrapper
    
    return decorator
