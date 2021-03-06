# -*- coding: utf-8 -*-
# @author: jeix

from __future__ import absolute_import, unicode_literals
from future import standard_library

import io
import os
import socket
import struct
from builtins import object
from contextlib import closing
from select import select
from time import time

from pyload.core.plugin import Abort
from pyload.utils.path import remove

standard_library.install_aliases()


# TODO: This must be adapted to the new request interfaces
class XDCCRequest(object):

    def __init__(self, timeout=30, proxies={}):

        self.proxies = proxies
        self.timeout = timeout

        self.filesize = 0
        self.recv = 0
        self.speed = 0

        self.abort = False

    def create_socket(self):
        # proxytype = None
        # proxy = None
        # if self.proxies.has_key("socks5"):
            # proxytype = socks.PROXY_TYPE_SOCKS5
            # proxy = self.proxies['socks5']
        # elif self.proxies.has_key("socks4"):
            # proxytype = socks.PROXY_TYPE_SOCKS4
            # proxy = self.proxies['socks4']
        # if proxytype:
            # sock = socks.socksocket()
            # t = _parse_proxy(proxy)
            # sock.setproxy(proxytype, addr=t[3].split(":")[0], port=int(t[3].split(":")[1]), username=t[1], password=t[2])
        # else:
            # sock = socket.socket()
        # return sock

        return socket.socket()

    def download(self, ip, port, fname, irc, progress_notify=None):

        ircbuffer = ""
        last_update = time()
        cum_recv_len = 0

        with closing(self.create_socket()) as dccsock:
            dccsock.settimeout(self.timeout)
            dccsock.connect((ip, port))

            if os.path.exists(fname):
                i = 0
                name_parts = fname.rpartition(".")
                while True:
                    newfilename = "{0}-{1:d}{2}{3}".format(
                        name_parts[0], i, name_parts[1], name_parts[2])
                    i += 1

                    if not os.path.exists(newfilename):
                        fname = newfilename
                        break

            with io.open(fname, mode='wb') as fp:
                # recv loop for dcc socket
                while True:
                    if self.abort:
                        # dccsock.close()
                        remove(fname, trash=True)
                        raise Abort

                    self._keep_alive(irc, ircbuffer)

                    data = dccsock.recv(4096)
                    data_len = len(data)
                    self.recv += data_len

                    cum_recv_len += data_len

                    now = time()
                    timespan = now - last_update
                    if timespan > 1:
                        self.speed = cum_recv_len // timespan
                        cum_recv_len = 0
                        last_update = now

                        if progress_notify:
                            progress_notify(self.percent)

                    if not data:
                        break

                    fp.write(data)

                    # acknowledge data by sending number of received bytes
                    dccsock.send(struct.pack('!I', self.recv))

        return fname

    def _keep_alive(self, sock, readbuffer):
        fdset = select([sock], [], [], 0)
        if sock not in fdset[0]:
            return None

        readbuffer += sock.recv(1024)
        temp = readbuffer.split("\n")
        readbuffer = temp.pop()

        for line in temp:
            line = line.rstrip()
            first = line.split()
            if first[0] == "PING":
                sock.send("PONG {0}\r\n".format(first[1]))

    def abort_downloads(self):
        self.abort = True

    @property
    def size(self):
        return self.filesize

    @property
    def arrived(self):
        return self.recv

    @property
    def percent(self):
        if not self.filesize:
            return 0
        return (self.recv * 100) // self.filesize

    def close(self):
        raise NotImplementedError
