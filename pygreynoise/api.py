from box import Box
from configparser import ConfigParser
import itertools
import json
from os import path
import requests


class GreyNoiseError(Exception):
    """Exception for GreyNoise API"""
    def __init__(self, message):
        self.message = message
        Exception.__init__(self, message)


class GreyNoiseNotFound(GreyNoiseError):
    def __init__(self):
        self.message = "No results for this query"
        GreyNoiseError.__init__(self, self.message)


class GreyNoise(object):
    # gn = GreyNoise()
    # gn.research.ja3.fingerprint(...)
    # gn.research.ja3.ip(...)
    # gn.research.combination(...)
    # gn.noise.context(...)

    _BASE_URL = 'https://research.api.greynoise.io/v2/'

    def __init__(self, key=None, enterprise=False, store_key=False):
        self._ua = 'PyGreyNoise/2'
        # self._base = 'https://{0}api.greynoise.io/v2'.format('enterprise.' if enterprise else '')
        # Set the API key, if no API key was specified - try to load it from the configuration file
        config_file = path.join(path.expanduser('~'), '.greynoise')
        config = ConfigParser(default_section='GreyNoise', defaults={'key': key})
        config.read(config_file)
        self.key = config['GreyNoise']['key']
        if store_key:
            with open(config_file, 'w') as fp:
                config.write(fp)

        # TODO: Add "magic" to refresh the supported magic (after Andrew adds WSDL or someother API description)
        self._methods = Box({
            'research': {
                'ja3': {
                    'fingerprint': lambda query: self._query('research/ja3/fingerprint', query),
                    'ip': lambda query: self._query('research/ja3/ip', query)
                },
                'tag': {
                    'combination': self._combination,
                    'list': lambda: self._query('research/tag/list')
                }
            },
            'enterprise': {
                'noise': {
                    'context': lambda query: self._query('enterprise/noise/context', query)
                }
            }
        })



    def _query(self, endpoint, query='', data={}, method='GET'):
        return requests.request(method, 
                '{0}/{1}{2}'.format(self._BASE_URL, endpoint, '/{0}'.format(query) if query else ''), 
                headers={
                    'key': self.key,
                    'User-Agent': self._ua
                },
                data=data).json()


    def _combination(self, *query, start=0, iterable=True):
        for i in itertools.count():
            r = self._query('research/combination', data=json.dumps({'query': query, 'offset': (start + i) * 100}))
            if not iterable or r.get('complete', True):
                return r['ips']
            else:
                yield r['ips']

    
    def __getattr__(self, name):
        return self._methods[name]
    
