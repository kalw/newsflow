from newsflow.config import conf, logger
from newsflow.nntp import NNTPConnection
import re

log = logger('newsflow.scraper')


class Scraper(NNTPConnection):
    def __init__(self, host, username, password, database, group, port=119):
        NNTPConnection.__init__(self, host, port, reconnect_timeout=conf('scraper.reconnect_timeout'))
        self.username = username
        self.password = password
        self.db = database
        self.group = group

    def get_subjects(self):
        lastid = self.db.hget('lastid', self.group)
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
        self.send('GROUP %s' % self.group)

    def handle_211(self, message):
        log.debug('handle_211 %s' % repr(message))
        count, first, last, group = message.split(' ', 3)

        nzbpattern = re.compile('^.* "(.*\.nzb)" yEnc \(([0-9]+)/([0-9]+)\)')

        for post in self.get_subjects():
            postid, subject = post.split(' ', 1)
            match = nzbpattern.match(subject)
            if not match:
                continue
            filename, filenum, end = match.groups()

            t = self.db.pipeline()
            t.hmset('%s/posts/%s' % (self.group, filename), {
                filenum: postid,
                'total': end,
            })
            t.hset('lastid', self.group, postid)
            t.sadd('%s/incomplete_files' % self.group, filename)
            t.lpush('queue/new_parts', '%s/%s' % (self.group, filename))
            t.execute()

        self.send('QUIT')
        self.sock.close()
