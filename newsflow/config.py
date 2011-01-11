#!/usr/bin/env python
import simplejson as json

import logging
import os.path
import sys
import os

config = None
files = [
    'newsflow.conf',
    '%s/.newsflow/newsflow.conf' % os.environ.get('HOME', '/tmp'),
    '/etc/newsflow/newsflow.conf',
]

def load_config():
    global config
    for filename in files:
        if os.path.exists(filename):
            try:
                config = json.load(file(filename, 'r'))
                break
            except:
                sys.stderr.write('Unable to parse config file %s: %s\n' % (filename, sys.exc_info()[1]))

    if not config:
        sys.stderr.write('Unable to find newsflow.conf!\n')

def logger(category):
    log = logging.getLogger(category)
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s', '%Y-%m-%d %H:%M:%S')
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    handler.setLevel(logging.DEBUG)
    log.addHandler(handler)

    log.debug('Logging configured')
    return log

def conf(key):
    obj = config
    for k in key.split('.'):
        obj = obj[k]
    log.debug('conf(%s) = %r' % (key, obj))
    return obj

load_config()
log = logger('newsflow.config')
