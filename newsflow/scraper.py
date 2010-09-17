from newsflow.config import conf, logger
from newsflow.nntp import NNTPConnection

import simplejson as json
import yenc

from os import unlink, makedirs, stat
from traceback import format_exc
from time import time
import os.path
import sys
import re

log = logger('newsflow.scraper')

class Scraper(NNTPConnection):
    def __init__(self, host, username, password, database, group, port=119):
        NNTPConnection.__init__(self, host, port, reconnect_timeout=conf('scraper.reconnect_timeout'))
        self.username = username
        self.password = password
        self.db = database
        self.group = group

        self.prefix = '%s/%s/' % (conf('redis.keyprefix'), group)
        self.tmpdir = '%s/%s/' % (conf('scraper.tmp_path'), group)
        self.nzbdir = '%s/%s/' % (conf('scraper.nzb_path'), group)
        try:
            makedirs(self.tmpdir)
            makedirs(self.nzbdir)
        except:
            log.warning('Unable to create scraper directories: %s' % sys.exc_info()[1])

        if not self.db.exists(self.prefix + 'nextid'):
            self.db.set(self.prefix + 'nextid', 0)

    def search_subjects(self):
        postcount = self.db.hgetall(self.prefix + 'postcount')
        if not postcount:
            return
        for filename, maxcount in postcount.items():
            maxcount = int(maxcount)
            count = self.db.hget(self.prefix + 'files', filename)
            if not count:
                continue
            count = int(count)
            if count >= maxcount:
                log.info('Have %i/%i posts for %s, downloading' % (count, maxcount, filename))
                posts = [x.split(' ', 2)[:2] for x in self.db.lrange(self.prefix + 'posts/' + filename, 0, -1)]
                if not posts:
                    log.warning('No postids for %s, assume something went wrong, cleaning up' % filename)
                    t = self.db.pipeline()
                    t.hdel(self.prefix + 'postcount', filename)
                    t.hdel(self.prefix + 'files', filename)
                    t.delete(self.prefix + 'posts/' + filename)
                    t.execute()
                    continue

                posts.sort(key=lambda x: x[0])
                tmpfile = self.tmpdir + filename
                for count, postid in posts:
                    self.download_post(postid, tmpfile=tmpfile)
                log.debug('Downloaded all parts, assembling and decoding')

                failed = False
                try:
                    outfile = self.nzbdir + filename
                    log.debug('yenc.decode("%s", "%s")' % (tmpfile, outfile))
                    yenc.decode(tmpfile, outfile)
                    unlink(tmpfile)

                    log.debug('Download successful, removing %s from the db' % filename)
                except:
                    log.error(format_exc())
                    log.error('Marking %s as a failure' % filename)
                    failed = True

                t = self.db.pipeline()
                t.hdel(self.prefix + 'postcount', filename)
                t.hdel(self.prefix + 'files', filename)
                t.delete(self.prefix + 'posts/' + filename)
                t.execute()
                if not failed:
                    self.db.sadd(self.prefix + 'downloaded', filename)
                    self.index_file(filename)
        return

    def get_subjects(self):
        lastid = self.db.get(self.prefix + 'lastid')
        if not lastid:
            lastid = conf('scraper.firstid')
        if not lastid:
            log.warning('lastid not found in db and firstid missing from config file, starting at post id 0')
            lastid = '0'
        self.send('XHDR Subject %s-' % lastid)

        line = self.readline()
        if not line.startswith('221'):
            log.error(line)

        log.info('Started downloading headers for ' + self.group)
        while True:
            line = self.readline()
            #log.debug('< %s' % line)
            if line == '.':
                break
            yield line
            #postid, subject = line.split(' ', 1)
            #yield (postid, subject)
        log.info('Finished downloading headers for ' + self.group)
        return

    def download_post(self, postid, tmpfile=None):
        self.send('BODY %s' % postid)
        line = self.readline()
        if not line.startswith('222'):
            log.error(line)
            return

        data = ''
        if not tmpfile:
            tmpfile = '%s%s.bin' % (self.tmpdir, postid)
        try:
            fd = file(tmpfile, 'a+')
        except:
            log.error('Unable to open %s for append: %s' % (tmpfile, sys.exc_info()[1]))
            line = None
            while line != '.\r\n':
                line = self.readline(strip=False)
            return None

        while True:
            line = self.readline(strip=False)
            if line == '.\r\n':
                break
            if line.startswith('=ybegin'):
                line = line.rstrip('\r\n')
                filename = line[line.rfind('=') + 1:]
                continue
            if (line.startswith('=yend') or line.startswith('=ypart')):
                continue
            fd.write(line)
        fd.close()
        return tmpfile

    def index_file(self, filename):
        indexname = filename.lower().replace('-', '.').replace('_', '.').replace(' ', '.')
        keywords = indexname.split('.')[:-1]

        ts = int(time())
        postid = self.db.incr(self.prefix + 'nextid')
        nzbsize = stat(os.path.join(self.nzbdir, filename)).st_size,

        metadata = json.dumps({
            'ts': ts,
            'name': filename,
            'size': nzbsize
        }, ensure_ascii=False)

        t = self.db.pipeline()
        t.hset(self.prefix + 'metadata', postid, metadata)
        t.zadd(self.prefix + 'recent', metadata, ts)
        for word in keywords:
            t.zadd(self.prefix + 'zindex/' + word, postid, ts)
            t.sadd(self.prefix + 'index_allwords', word)
        t.execute()
        log.info('Indexed %s with keywords %s' % (filename, repr(keywords)))

    def handle_200(self, message):
        self.send('AUTHINFO USER %s' % self.username)

    def handle_381(self, message):
        self.send('AUTHINFO PASS %s' % self.password)

    # Auth successful
    def handle_281(self, message):
        self.send('GROUP %s' % self.group)

    def handle_211(self, message):
        log.debug('handle_211 %s' % repr(message))
        count, first, last, group = message.split(' ', 3)

        nzbpattern = re.compile('^.* "(.*\.nzb)" yEnc \(([0-9]+)/([0-9]+)\)')

        files = []
        for post in self.get_subjects():
            postid, subject = post.split(' ', 1)
            match = nzbpattern.match(subject)
            if not match:
                continue
            filename, filenum, end = match.groups()

            t = self.db.pipeline()
            t.hincrby(self.prefix + 'files', filename, 1)
            t.hset(self.prefix + 'postcount', filename, int(end))
            t.lpush(self.prefix + 'posts/' + filename, '%s %s' % (filenum, post))
            t.set(self.prefix + 'lastid', postid)
            t.execute()

        self.db.set(self.prefix + 'lastid', postid)

        self.search_subjects()

        self.send('QUIT')
        self.sock.close()
