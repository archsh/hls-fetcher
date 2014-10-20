# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Copyright (C) 2009-2010 Fluendo, S.L. (www.fluendo.com).
# Copyright (C) 2009-2010 Marc-Andre Lureau <marcandre.lureau@gmail.com>

# This file may be distributed and/or modified under the terms of
# the GNU General Public License version 2 as published by
# the Free Software Foundation.
# This file is distributed without any warranty; without even the implied
# warranty of merchantability or fitness for a particular purpose.
# See "LICENSE" in the source distribution for more information.

from itertools import ifilter
import logging
import os, os.path
import tempfile
import urlparse

from twisted.python import log
from twisted.web import client
from twisted.internet import defer, reactor, task
from twisted.internet.task import deferLater

import hls_sync
from hls_sync.m3u8 import M3U8

class HLSFetcher(object):

    def __init__(self, url, options=None, program=1):
        self.url = url
        self.program = program
        if options:
            self.path = options.path
            self.referer = options.referer
            self.bitrate = options.bitrate
            self.n_segments_keep = options.keep
            self.nbuffer = options.buffer
        else:
            self.path = None
            self.referer = None
            self.bitrate = 200000
            self.n_segments_keep = 3
            self.nbuffer = 3
        if not self.path:
            self.path = tempfile.mkdtemp()

        self._program_playlist = None
        self._file_playlist = None
        self._cookies = {}
        self._cached_files = {} # sequence n -> path

        self._files = None # the iter of the playlist files download
        self._next_download = None # the delayed download defer, if any
        self._file_playlisted = None # the defer to wait until new files are added to playlist

        self._pl_task = None
        self._seg_task = None

    def _get_page(self, url):
        def got_page(content):
            logging.debug("Cookies: %r" % self._cookies)
            return content
        def got_page_error(e, url):
            logging.error(url)
            log.err(e)
            return e

        url = url.encode("utf-8")
        if 'HLS_RESET_COOKIES' in os.environ.keys():
            self._cookies = {}
        headers = {}
        if self.referer:
            headers['Referer'] = self.referer
        d = client.getPage(url, cookies=self._cookies, headers=headers)
        d.addCallback(got_page)
        d.addErrback(got_page_error, url)
        return d

    def _download_page(self, url, path):
        # client.downloadPage does not support cookies!
        def _check(x):
            logging.debug("Received segment of %r bytes." % len(x))
            return x

        d = self._get_page(url)
        d.addCallback(_check)
        return d

        return d

    def _download_segment(self, f):
        url = HLS.make_url(self._file_playlist.url, f['file'])
        name = urlparse.urlparse(f['file']).path.split('/')[-1]
        path = os.path.join(self.path, name)
        d = self._download_page(url, path)
        if self.n_segments_keep != 0:
            file = open(path, 'w')
            d.addCallback(lambda x: file.write(x))
            d.addBoth(lambda _: file.close())
            d.addCallback(lambda _: path)
            d.addErrback(self._got_file_failed)
            d.addCallback(self._got_file, url, f)
        else:
            d.addCallback(lambda _: (None, path, f))
        return d

    def delete_cache(self, f):
        keys = self._cached_files.keys()
        for i in ifilter(f, keys):
            filename = self._cached_files[i]
            logging.debug("Removing %r" % filename)
            os.remove(filename)
            del self._cached_files[i]
        self._cached_files

    def _got_file_failed(self, e):
        if self._new_filed:
            self._new_filed.errback(e)
            self._new_filed = None

    def _got_file(self, path, url, f):
        logging.debug("Saved " + url + " in " + path)
        self._cached_files[f['sequence']] = path
        if self.n_segments_keep != -1:
            self.delete_cache(lambda x: x <= f['sequence'] - self.n_segments_keep)
        if self._new_filed:
            self._new_filed.callback((path, url, f))
            self._new_filed = None
        return (path, url, f)

    def _get_next_file(self):
        next = self._files.next()
        if next:
            d = self._download_segment(next)
            return d
        elif not self._file_playlist.endlist():
            self._seg_task.stop()
            self._file_playlisted = defer.Deferred()
            self._file_playlisted.addCallback(lambda x: self._get_next_file())
            self._file_playlisted.addCallback(self._next_file_delay)
            self._file_playlisted.addCallback(self._seg_task.start)
            return self._file_playlisted

    def _handle_end(self, failure):
        failure.trap(StopIteration)
        print "End of media"
        reactor.stop()

    def _next_file_delay(self, f):
        delay = f[2]["duration"]
        # FIXME not only the last nbuffer, but the nbuffer -1 ...
        if self.nbuffer > 0 and not self._cached_files.has_key(f[2]['sequence'] - (self.nbuffer - 1)):
            delay = 0
        elif self._file_playlist.endlist():
            delay = 1
        return delay

    def _get_files_loop(self):
        if not self._seg_task:
            self._seg_task = task.LoopingCall(self._get_next_file)
        d = self._get_next_file()
        d.addCallback(self._next_file_delay)
        d.addCallback(self._seg_task.start)
        return d

    def _playlist_updated(self, pl):
        if pl.has_programs():
            # if we got a program playlist, save it and start a program
            self._program_playlist = pl
            (program_url, _) = pl.get_program_playlist(self.program, self.bitrate)
            l = HLS.make_url(self.url, program_url)
            return self._reload_playlist(M3U8(l))
        elif pl.has_files():
            # we got sequence playlist, start reloading it regularly, and get files
            self._file_playlist = pl
            if not self._files:
                self._files = pl.iter_files()
            if not pl.endlist():
                if not self._pl_task:
                    self._pl_task = task.LoopingCall(self._reload_playlist, pl)
                    self._pl_task.start(10, False)
            if self._file_playlisted:
                self._file_playlisted.callback(pl)
                self._file_playlisted = None
        else:
            raise
        return pl

    def _got_playlist_content(self, content, pl):
        if not pl.update(content):
            # if the playlist cannot be loaded, start a reload timer
            self._pl_task.stop()
            self._pl_task.start(pl.reload_delay(), False)
            d = deferLater(reactor, pl.reload_delay(), self._fetch_playlist, pl)
            d.addCallback(self._got_playlist_content, pl)
            return d
        return pl

    def _fetch_playlist(self, pl):
        logging.debug('fetching %r' % pl.url)
        d = self._get_page(pl.url)
        return d

    def _reload_playlist(self, pl):
        d = self._fetch_playlist(pl)
        d.addCallback(self._got_playlist_content, pl)
        d.addCallback(self._playlist_updated)
        return d

    def get_file(self, sequence):
        d = defer.Deferred()
        keys = self._cached_files.keys()
        try:
            sequence = ifilter(lambda x: x >= sequence, keys).next()
            filename = self._cached_files[sequence]
            d.callback(filename)
        except:
            d.addCallback(lambda x: self.get_file(sequence))
            self._new_filed = d
            keys.sort()
            logging.debug('waiting for %r (available: %r)' % (sequence, keys))
        return d

    def _start_get_files(self, x):
        self._new_filed = defer.Deferred()
        self._get_files_loop()
        return self._new_filed

    def start(self):
        self._files = None
        d = self._reload_playlist(M3U8(self.url))
        d.addCallback(self._start_get_files)
        return d

    def stop(self):
        pass

