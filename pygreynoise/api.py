from box import Box
from configparser import ConfigParser
import itertools
import json
from os import path
import requests
import logging
import sys


class GreyNoiseError(Exception):
    """Exception for GreyNoise API"""
    def __init__(self, message):
        self.message = message
        Exception.__init__(self, message)


class GreyNoiseNotFound(GreyNoiseError):
    def __init__(self):
        self.message = "No results for this query"
        GreyNoiseError.__init__(self, self.message)


def validate_date(date):
    import datetime
    try:
        datetime.datetime.strptime(date, '%Y-%m-%d')
        return date
    except ValueError:
        raise ValueError('Incorrect data format, should be YYYY-MM-DD')


def validate_ip(ip_address, strict=True):
    import socket
    try:
        socket.inet_aton(ip_address)
        return ip_address
    except socket.error:
        if strict:
            raise ValueError('Invalid IP address')

        return None


class GreyNoise(object):
    # gn = GreyNoise()
    # gn.research.ja3.fingerprint(...)
    # gn.research.ja3.ip(...)
    # gn.research.combination(...)
    # gn.noise.context(...)

    _BASE_URL = 'https://research.api.greynoise.io/v2'
    _LOG_NAME = 'GreyNoise'
    _OK = 'ok'

    def __init__(self, key=None, store_key=False):
        self._ua = 'PyGreyNoise/2'
        self._log = self._logger(logging.DEBUG)
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
                'ip': lambda ip: self._query('research/ip', validate_ip(ip)),
                'ja3': {
                    'fingerprint': lambda fingerprint: self._query('research/ja3/fingerprint', fingerprint),
                    'ip': lambda ip: self._query('research/ja3/ip', validate_ip(ip))
                },
                'raw': {
                    'ip': lambda ip: self._query('research/raw/ip', validate_ip(ip)),
                    'scan': lambda protocol, port: self._query('research/raw/scan', '/'.join([protocol, str(port)]))
                },
                'tag': {
                    'combination': lambda *query: self._query('research/tag/combination', data=json.dumps({'query': query})),
                    'list': lambda: self._query('research/tag/list'),
                    'single': lambda tag: self._query('research/tag/single', data=json.dumps({'tag': tag})),
                },
            },
            'enterprise': {
                'noise': {
                    'bulk': lambda date='': self._query('enterprise/noise/bulk', '' if not date else validate_date(date)),
                    'context': lambda ip: self._query('enterprise/noise/context', validate_ip(ip)),
                    'multi': lambda *ips: self._query('enterprise/noise/multi/quick', data=json.dumps({'ips': validate_ip(ip) for ip in ips})),
                    'quick': lambda ip: self._query('enterprise/noise/quick', validate_ip(ip))
                }
            }
        })


    def _logger(self, level=logging.INFO):
        """Create a logger to be used between processes.
        :returns: Logging instance.
        """

        logger = logging.getLogger(self._LOG_NAME)
        logger.setLevel(level)
        shandler = logging.StreamHandler()
        fmt = '\033[1;32m%(levelname)-5s %(module)s:%(funcName)s():%(lineno)d %(asctime)s\033[0m| %(message)s'
        shandler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(shandler)
        return logger

        
    def _query(self, endpoint, query='', params={}, data={}, method='GET'):
        uri = '/'.join([self._BASE_URL, endpoint, query]).strip('/')
        self._log.debug('Trying to query %s%s%s', uri,
                '' if not params else params,
                '' if not data else ' with {0} as body'.format(data)
            )
        try:
            res = requests.request(method, uri, headers={
                    'key': self.key,
                    'User-Agent': self._ua
                },
                params=params, data=data)

            self._log.debug('Request to %s, returned %s\n%s', res.url, res.headers, res.content)  # TODO: Log the full response
            res.raise_for_status()  # Make sure no HTTPError occured
            loaded = res.json()
            if {'error', 'status'} & loaded.keys() and not loaded.get('status') == self._OK:  # Handle API errors
                raise GreyNoiseError(loaded.get('error', loaded.get('status')))
        except requests.HTTPError as error:
            loaded = res.json()  # For client errors (4xx) we have an JSON body
            raise GreyNoiseError('{msg} ({endpoint}{data})'.format(
                msg=loaded.get('error', loaded.get('status', str(error))),
                endpoint=error.response.url,
                data='' if not data else '[{0}]'.format(data)
            ))
        except Exception as error:  # Wrap & re-raise exceptions
            # TODO: Do we need this?
            raise error

        return loaded


    def _combination(self, *query, start=0, iterable=True):
        for i in itertools.count():
            r = self._query('research/combination', data=json.dumps({'query': query, 'offset': (start + i) * 100}))
            if not iterable or r.get('complete', True):
                return r['ips']
            else:
                yield r['ips']

    
    def __getattr__(self, name):
        self._log.debug(name)
        return self._methods[name]
    
