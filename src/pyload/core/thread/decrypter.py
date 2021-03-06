# -*- coding: utf-8 -*-

from __future__ import absolute_import, unicode_literals
from future import standard_library

import time
from builtins import str
from itertools import chain

from ..plugin import Abort, Fail, Retry
from ..plugin.crypter import Package
from pyload.utils.convert import accumulate
from pyload.utils.purge import uniqify

from ..datatype.init import (DownloadStatus, LinkStatus, ProgressInfo,
                             ProgressType)
from .plugin import PluginThread

standard_library.install_aliases()


class DecrypterThread(PluginThread):
    """
    Thread for decrypting.
    """
    __slots__ = ['_progress', 'data', 'error', 'fid', 'pid']

    def __init__(self, manager, data, fid, pid, owner):
        PluginThread.__init__(self, manager, owner)
        # [...(url, plugin)...]
        self.data = data
        self.fid = fid
        self.pid = pid
        # holds the progress, while running
        self._progress = None
        # holds if an error happened
        self.error = False

    def get_progress(self):
        return self._progress

    def run(self):
        pack = self.pyload.files.get_package(self.pid)
        api = self.pyload.api.with_user_context(self.owner)
        links, packages = self.decrypt(accumulate(self.data), pack.password)

        # if there is only one package links will be added to current one
        if len(packages) == 1:
            # TODO: also rename the package (optionally)
            links.extend(packages[0].links)
            del packages[0]

        if links:
            self.pyload.log.info(
                _("Decrypted {0:d} links into package {1}").format(len(links), pack.name))
            api.add_links(self.pid, [l.url for l in links])

        for pack_ in packages:
            api.add_package(pack_.name, pack_.get_urls(), pack.password)

        self.pyload.files.set_download_status(
            self.fid,
            DownloadStatus.Finished if not self.error else DownloadStatus.Failed
        )
        self.manager.done(self)

    def _decrypt(self, name, urls):
        klass = self.pyload.pgm.load_class("crypter", name)
        plugin = None
        result = []

        # updating progress
        self._progress.plugin = name
        self._progress.name = _("Decrypting {0} links").format(
            len(urls) if len(urls) > 1 else urls[0])

        # TODO: dependency check, there is a new error code for this
        # TODO: decrypting with result yielding
        if not klass:
            self.error = True
            if err:
                result.extend(LinkStatus(
                    url, url, -1, DownloadStatus.NotPossible, name) for url in urls)
            self.pyload.log.debug(
                "Plugin '{0}' for decrypting was not loaded".format(name))
        else:
            try:
                plugin = klass(self.pyload, password)

                try:
                    result = plugin._decrypt(urls)
                except Retry:
                    time.sleep(1)
                    result = plugin._decrypt(urls)

                plugin.log_debug("Decrypted", result)

            except Abort:
                plugin.log_info(_("Decrypting aborted"))
            except Exception as e:
                plugin.log_error(_("Decrypting failed"), str(e))

                self.error = True
                # generate error linkStatus
                if err:
                    result.extend(LinkStatus(
                        url, url, -1, DownloadStatus.Failed, name) for url in urls)

                # no debug for intentional errors
                # if self.pyload.debug and not isinstance(e, Fail):
                    # self.pyload.print_exc()
                    # self.debug_report(plugin.__name__, plugin=plugin)
            finally:
                if plugin:
                    plugin.clean()
                self._progress.done += len(urls)
                
        return result
                        
    def decrypt(self, plugin_map, password=None, err=False):
        result = []
        self._progress = ProgressInfo(
            "BasePlugin", "", _("decrypting"), 0, 0, len(self.data), self.owner,
            ProgressType.Decrypting
        )
        # TODO: QUEUE_DECRYPT
        result = self._pack_result(
            chain.from_iterable(
                self._decrypt(name, urls) for name, urls in plugin_map.items()))
        # clear the progress
        self._progress = None
        return result
        
    def _pack_result(self, packages):    
        # generated packages
        packs = {}
        # urls without package
        urls = []
        # merge urls and packages
        for pack in packages:
            if isinstance(pack, Package):
                if pack.name in packs:
                    packs[pack.name].urls.extend(pack.urls)
                elif not pack.name:
                    urls.extend(pack.links)
                else:
                    packs[pack.name] = pack
            else:
                urls.append(pack)        
        return uniqify(urls), list(packs.values())
