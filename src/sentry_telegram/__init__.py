try:
    VERSION = __import__('pkg_resources') \
        .get_distribution('sentry-telegram').version
except Exception, e:
    VERSION = 'unknown'
