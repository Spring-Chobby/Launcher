import re
from subprocess import Popen, PIPE, STDOUT
import sys
import os
import logging

from PyQt5.QtCore import QObject, pyqtSignal

from spring_platform import SpringPlatform
import auto_update

class SpringDownloader(QObject):
    downloadStarted = pyqtSignal(str, str, name='downloadStarted')
    downloadFinished = pyqtSignal(name='downloadFinished')
    downloadFailed = pyqtSignal(str, name='downloadFailed')
    downloadProgress = pyqtSignal(int, int, name='downloadProgress')
    FOLDER = "data"

    def __init__(self):
        super(QObject, self).__init__()

        self._InitializePatterns()

    def _InitializePatterns(self):
        self.progressPattern = re.compile("[0-9]+/[0-9]+")
        self.missingPattern = re.compile(".*no engine.*|.*no mirrors.*|.*no game found.*|.*no map found.*|.*error occured while downloading.*")

    # takes line from pr-downloader
    # returns lineType, data
    # lineType is one of "info", "progress", "failed", "extract", "done"
    # data depends on lineType;
    # info-> data is a string
    # progress-> data is a tuple of (current, max)
    # extract-> data is a tuple of (dstFolder, path)
    # done-> data is None
    def _ProcessLine(self, line):
        lineType = None
        data = None

        if line.startswith("[Progress]"):
            lineType = "progress"

            progressStr = self.progressPattern.search(line).group()
            current, total = progressStr.split("/")
            current = int(current)
            total = int(total)
            data = (current, total)
        elif line.startswith("[Error]"):
            if self.missingPattern.match(line.lower()):
                lineType = "failed"
                data = "Problem downloading: {}".format(line)
        elif line.startswith("[Info]"):
            if line == "[Info] Download complete!":
                lineType = "info"
                pass
            else:
                lineType = "info"

        return lineType, data

    def _Download(self, args):
        logging.info(" ".join(args))
        p = Popen(args, stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        for line in iter(p.stdout.readline, ""):
            logging.info(line[:-1])
            lineType, data = self._ProcessLine(line)
            if lineType == "progress":
                current, total = data[0], data[1]
                if total > 0:
                    self.downloadProgress.emit(current, total)
            elif lineType == "failed":
                self.downloadFailed.emit(data)
                p.wait()
                return
        self.downloadFinished.emit()

    def _MaybeMakeFolder(self):
        if not os.path.exists(self.FOLDER):
            os.makedirs(self.FOLDER)

    def DownloadEngine(self, ver_string):
        self._MaybeMakeFolder()
        self.downloadStarted.emit(ver_string, "Engine")
        self._Download([SpringPlatform.PR_DOWNLOADER_PATH, '--filesystem-writepath', self.FOLDER, '--download-engine', ver_string])

    def DownloadGame(self, name):
        self._MaybeMakeFolder()
        self.downloadStarted.emit(name, "Game")
        self._Download([SpringPlatform.PR_DOWNLOADER_PATH, '--filesystem-writepath', self.FOLDER, '--download-game', name])

    def DownloadMap(self, name):
        self._MaybeMakeFolder()
        self.downloadStarted.emit(name, "Map")
        self._Download([SpringPlatform.PR_DOWNLOADER_PATH, '--filesystem-writepath', self.FOLDER, '--download-map', name])

    def SelfUpdate(self):
        import sys

        config_name = 'myapp.cfg'

        # determine if application is a script file or frozen exe
        if not getattr(sys, 'frozen', False):
            logging.info("Self-update only done for frozen apps.")
            self.downloadFinished.emit()
            return

        update_list = auto_update.get_update_list()

        if len(update_list) == 0:
            logging.info("No-self update necessary.")
            return
        self.dl_so_far = 0
        self.dl_total = sum([up["size"] for up in update_list])

        def callback(chunk_size):
            self.dl_so_far += chunk_size
            self.downloadProgress.emit(self.dl_so_far, self.dl_total)

        logging.info("Starting self-update...")
        self.downloadStarted.emit("Updating: ", "self")
        auto_update.download_files(update_list, callback)
        logging.info("Self-update completed.")

        self.downloadFinished.emit()
