#!/usr/bin/env python
# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Copyright (C) 2009-2010 Fluendo, S.L. (www.fluendo.com).
# Copyright (C) 2009-2010 Marc-Andre Lureau <marcandre.lureau@gmail.com>
# Copyright (C) 2010 Zaheer Abbas Merali  <zaheerabbas at merali dot org>
# Copyright (C) 2010 Andoni Morales Alastruey <ylatuya@gmail.com>

# This file may be distributed and/or modified under the terms of
# the GNU General Public License version 2 as published by
# the Free Software Foundation.
# This file is distributed without any warranty; without even the implied
# warranty of merchantability or fitness for a particular purpose.
# See "LICENSE" in the source distribution for more information.

import sys
import urlparse
import optparse
import logging
import os

# from twisted.internet import reactor
# reactor.install()
from twisted.internet import reactor
from twisted.python import log

from hlsfethcer import __version__
from hlsfethcer.fetcher import HLSFetcher
from hlsfethcer.m3u8 import M3U8

if sys.version_info < (2, 4):
    raise ImportError("Cannot run with Python version < 2.4")


class HLSControler:

    def __init__(self, fetcher=None):
        self.fetcher = fetcher
        self.player = None

        self._player_sequence = None
        self._n_segments_keep = None

    def set_player(self, player):
        self.player = player
        if player:
            self.player.connect_about_to_finish(self.on_player_about_to_finish)
            self._n_segments_keep = self.fetcher.n_segments_keep
            self.fetcher.n_segments_keep = -1

    def _start(self, first_file):
        (path, l, f) = first_file
        self._player_sequence = f['sequence']
        if self.player:
            self.player.set_uri(path)
            self.player.play()

    def start(self):
        d = self.fetcher.start()
        d.addCallback(self._start)

    def _set_next_uri(self):
        # keep only the past three segments
        if self._n_segments_keep != -1:
            self.fetcher.delete_cache(lambda x:
                x <= self._player_sequence - self._n_segments_keep)
        self._player_sequence += 1
        d = self.fetcher.get_file(self._player_sequence)
        d.addCallback(self.player.set_uri)

    def on_player_about_to_finish(self):
        reactor.callFromThread(self._set_next_uri)


def main():

    parser = optparse.OptionParser(usage='%prog [options] url...',
                                   version="%prog " + __version__)

    parser.add_option('-v', '--verbose', action="store_true",
                      dest='verbose', default=False,
                      help='print some debugging (default: %default)')
    parser.add_option('-b', '--bitrate', action="store",
                      dest='bitrate', default=200000, type="int",
                      help='desired bitrate (default: %default)')
    parser.add_option('-u', '--buffer', action="store", metavar="N",
                      dest='buffer', default=3, type="int",
                      help='pre-buffer N segments at start')
    parser.add_option('-k', '--keep', action="store",
                      dest='keep', default=3, type="int",
                      help='number of segments ot keep (default: %default, -1: unlimited)')
    parser.add_option('-r', '--referer', action="store", metavar="URL",
                      dest='referer', default=None,
                      help='Sends the "Referer Page" information with URL')
    parser.add_option('-D', '--no-display', action="store_true",
                      dest='nodisplay', default=False,
                      help='display no video (default: %default)')
    parser.add_option('-s', '--save', action="store_true",
                      dest='save', default=False,
                      help='save instead of watch (saves to /tmp/hls-player.ts)')
    parser.add_option('-p', '--path', action="store", metavar="PATH",
                      dest='path', default=None,
                      help='download files to PATH')
    parser.add_option('-n', '--number', action="store",
                      dest='n', default=1, type="int",
                      help='number of player to start (default: %default)')

    options, args = parser.parse_args()

    if len(args) == 0:
        parser.print_help()
        sys.exit(1)

    log.PythonLoggingObserver().start()
    if options.verbose:
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s %(levelname)-8s %(message)s',
                            datefmt='%d %b %Y %H:%M:%S')

    n = 0
    for url in args:
        for l in range(options.n):

            if urlparse.urlsplit(url).scheme == '':
                url = "http://" + url

            c = HLSControler(HLSFetcher(url, options))
            delay = 10.0 / options.n * n
            n += 1
            reactor.callLater(delay, c.start)

    reactor.run()


if __name__ == '__main__':
    sys.exit(main())
