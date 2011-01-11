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

log = logger('newsflow.consumer')


class Consumer(NNTPConnection):
    def __init__(self, host, username, password, database, port=119):
        NNTPConnection.__init__(self, host, port, reconnect_timeout=conf('scraper.reconnect_timeout'))
        self.username = username
        self.password = password
        self.db = database

    def consume(self):
        pass

    def get_tmpdir(self, group):
        tmpdir = '%s/%s/' % (conf('scraper.tmp_path'), group)
        try:
            makedirs(tmpdir)
        except:
            pass
        return tmpdir

    def get_nzbdir(self, group):
        nzbdir = '%s/%s/' % (conf('scraper.nzb_path'), group)
        try:
            makedirs(nzbdir)
        except:
            pass
        return nzbdir

    def handle(self, line):
        try:
            code, message = line.split(' ', 1)
        except:
            log.warning('Unparsable response: %s' % line)
            return

        code = int(code)
        if hasattr(self, 'handle_%i' % code):
            method = getattr(self, 'handle_%i' % code)
            method(message)

    def handle_200(self, message):
        self.send('AUTHINFO USER %s' % self.username)

    def handle_381(self, message):
        self.send('AUTHINFO PASS %s' % self.password)

    # Auth successful
    def handle_281(self, message):
        while True:
            self.consume()


class DownloadConsumer(Consumer):
    def __init__(self, host, username, password, database, port=119):
        Consumer.__init__(self, host, username, password, database, port)

    def consume(self):
        key, msg = self.db.brpop('queue/new_parts')
        group, filename = msg.split('/', 1)

        file_posts = self.db.hgetall('%s/posts/%s' % (group, filename))
        if not file_posts:
            return

        total = int(file_posts['total'])
        have_posts = [file_posts.get(str(i), None) for i in range(1, total + 1)]

        if not all(have_posts):
            # Still don't have all the parts for this file, skip it
            log.info('Skipping %s, not enough parts (%i/%i)' % (filename, len(have_posts), total))
            return
        else:
            log.info('Have %i/%i parts for %s, downloading' % (len(have_posts), total, filename))

        tmpdir = self.get_tmpdir(group)
        nzbdir = self.get_nzbdir(group)

        tmpfile = tmpdir + filename

        self.send('GROUP %s' % group)
        groupinfo = self.readline()

        for postid in have_posts:
            self.download_post(postid, tmpfile)

        try:
            outfile = nzbdir + filename
            log.debug('yenc.decode("%s", "%s")' % (tmpfile, outfile))
            yenc.decode(tmpfile, outfile)
        except:
            log.error(format_exc())
            log.error('yEnc decode failed, cleaning up and bailing out')
            unlink(tmpfile)
            return

        log.info('Successfully processed %s, cleaning up' % filename)
        t = self.db.pipeline()
        t.delete('%s/posts/%s' % (group, filename))
        t.srem('%s/incomplete_files', filename)
        t.lpush('queue/index_nzb', '%s/%s' % (group, filename))
        t.execute()
        unlink(tmpfile)

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


class IndexConsumer(Consumer):
    def consume(self):
        key, msg = self.db.brpop('queue/index_nzb')
        group, filename = msg.split('/', 1)

        indexname = filename.lower()

        replace = '._-&'
        for c in replace:
            indexname = indexname.replace(c, ' ')
        keywords = [x for x in indexname.split(' ')[:-1] if x]

        nzbdir = self.get_nzbdir(group)
        st = stat(os.path.join(nzbdir, filename))
        ts = st.st_mtime

        metadata = json.dumps({
            'ts': ts,
            'name': filename.decode('utf-8', 'backslashreplace'),
            'size': st.st_size,
        }, ensure_ascii=False)

        id = self.db.incr('nextid')
        t = self.db.pipeline()
        t.hset(group + '/metadata', id, metadata)
        t.zadd(group + '/recent', metadata, ts)
        for word in keywords:
            t.zadd(group + '/zindex/' + word, id, ts)
            t.sadd(group + '/index_allwords', word)
        t.execute()
        log.info('Indexed %s with keywords %s' % (filename, repr(keywords)))
