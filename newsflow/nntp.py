from newsflow.config import logger, conf
from socket import socket
from time import sleep

log = logger('newsflow.nntp')

class NNTPConnection(object):
    def __init__(self, host, port, reconnect_timeout=300):
        self.host = host
        self.port = port
        self.reconnect_timeout = reconnect_timeout
        self.connect()

    def connect(self):
        self.sock = socket()
        self.sock.connect((self.host, self.port))
        self.buf = ''

    def readline(self, strip=True):
        while self.buf.find('\r\n') == -1:
            try:
                chunk = self.sock.recv(4096)
            except:
                chunk = ''
            if not chunk and not self.buf:
                return None
            self.buf += chunk
        line, self.buf = self.buf.split('\r\n', 1)
        if not strip:
            line += '\r\n'
        return line

    def send(self, message):
        log.debug('> %s' % message)
        self.sock.sendall('%s\r\n' % message)

    def handle(self, line):
        pass

    def run(self):
        self.connect()
        while True:
            line = self.readline()
            if line is None:
                log.debug('Connection lost, will reconnect in %i seconds' % self.reconnect_timeout)
                sleep(self.reconnect_timeout)
                self.connect()
                continue
            log.debug('< %s' % line)
            self.handle(line)
