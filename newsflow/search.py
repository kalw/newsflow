from newsflow.config import conf

from time import strftime, gmtime, time
from urllib import quote_plus
from random import randint
import mimetypes
import os.path
import gzip

import simplejson as json
import bottle
import jinja2
import redis

bottle.debug(True)

db = redis.Redis(conf('redis.server'), db=conf('redis.db'))
templates = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.join(conf('http.static_path'), 'templates/')))

def rfc822(ts):
    return strftime('%a, %d %b %Y %H:%M:%S GMT', gmtime(ts))
templates.filters['rfc822'] = rfc822
templates.filters['quote_plus'] = quote_plus

@bottle.get('/api/1/:group/recent.:fmt#(json|rss)#')
def recent_files(group, fmt):
    results = db.zrange('%s/recent' % group, 0, 100, desc=True)
    results = [json.loads(x) for x in results]

    if fmt == 'rss':
        bottle.response.content_type = 'application/rss+xml'
        template = templates.get_template('search.rss')
        return template.render(query='Recent posts', group=group, now=time(), results=results, baseurl=conf('http.baseurl'))
    else:
        bottle.response.content_type = 'text/javascript'
        return json.dumps(results, indent=2)

@bottle.get('/api/1/:group/search.:fmt#(json|rss)#')
def search_files(group, fmt):
    t = db.pipeline()
    q = bottle.request.params['q']
    query = q.replace('-', ' ').replace('_', ' ')
    keywords = query.split(' ')
    keywords = ['%s/zindex/%s' % (group, x) for x in keywords if x]
    for k in keywords:
        t.exists(k)
    for i, exists in enumerate(t.execute()):
        if not exists:
            keywords.remove(keywords[i])

    t.reset()
    tmpkey = 'zinter-%.02f+%i' % (time(), randint(1, 9999))
    if keywords:
        db.zinterstore(tmpkey, keywords, 'MAX')
        matches = db.zrange(tmpkey, 0, 500, desc=True)
        if matches:
            results = [json.loads(x) for x in db.hmget('%s/metadata' % group, matches) if x]
        else:
            results = []
        db.delete(tmpkey)
    else:
        results = []

    if fmt == 'rss':
        bottle.response.content_type = 'application/rss+xml'
        template = templates.get_template('search.rss')
        return template.render(query=q, group=group, now=time(), results=results, baseurl=conf('http.baseurl'))
    else:
        bottle.response.content_type = 'text/javascript'
        return json.dumps(results, indent=2)

@bottle.get('/api/1/')
def get_groups():
    return json.dumps(conf('scraper.groups'), indent=2)

@bottle.get('/api/1/:group/nzb/:filename')
def get_nzb(group, filename):
    path = os.path.join(conf('scraper.nzb_path'), group, filename)
    path = os.path.normpath(path)
    if not path.startswith(conf('scraper.nzb_path')):
        bottle.abort(404)

    bottle.response.content_type = 'application/x-nzb'
    if os.path.exists(path):
        return file(path, 'rb').read()
    if os.path.exists(path + '.gz'):
        return gzip.open(path + '.gz', 'rb').read()
    bottle.abort(404)

@bottle.get('/recent')
def recent():
    return file(os.path.join(conf('http.static_path'), 'html/recent.html')).read()

@bottle.get('/')
def search():
    return file(os.path.join(conf('http.static_path'), 'html/search.html')).read()

@bottle.get('/:filename#.*#')
def static(filename):
    bottle.response.content_type = mimetypes.guess_type(filename)[0]
    filename = os.path.normpath(os.path.join(conf('http.static_path'), 'html/', filename))
    if not filename.startswith(os.path.join(conf('http.static_path'), 'html/')):
        bottle.abort(404)
    if not os.path.exists(filename):
        bottle.abort(404)
    return file(filename).read()
    
application = bottle.default_app()
