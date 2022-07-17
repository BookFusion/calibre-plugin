__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from PyQt5.Qt import QObject, pyqtSignal
from os.path import getsize
import json
import urllib.error

from calibre_plugins.bookfusion import api
from calibre_plugins.bookfusion.book_format import BookFormat


class CheckWorker(QObject):
    finished = pyqtSignal()
    aborted = pyqtSignal(str)
    readyToRunCheck = pyqtSignal()
    progress = pyqtSignal(int)
    limitsAvailable = pyqtSignal(dict)
    resultsAvailable = pyqtSignal(int, list)

    def __init__(self, db, logger, book_ids):
        QObject.__init__(self)

        self.db = db
        self.logger = logger
        self.book_ids = book_ids
        self.reply = None
        self.canceled = False

    def start(self):
        self.readyToRunCheck.connect(self.run_check)

        self.pending_book_ids = self.book_ids
        self.count = 0
        self.books_count = 0
        self.valid_ids = []

        self.fetch_limits()

    def cancel(self):
        self.canceled = True
        if self.reply:
            self.reply.abort()
        self.finished.emit()

    def fetch_limits(self):
        req = api.build_request('/limits')

        abort = False

        try:
            with api.build_opener().open(req) as f:
                resp = f.read()
                self.logger.info('Fetch limits response: {}'.format(resp))
                self.limits = json.loads(resp)
                self.limitsAvailable.emit(self.limits)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                abort = True
                self.aborted.emit('Invalid API key.')
                self.logger.info('Fetch limits: 401')
            else:
                abort = True
                self.aborted.emit('Error {}.'.format(e.code))
                self.logger.info('Fetch limits error: {}'.format(e.code))

        if abort:
            self.finished.emit()
        else:
            self.readyToRunCheck.emit()

    def run_check(self):
        for book_id in self.pending_book_ids:
            if self.canceled:
                return

            self.progress.emit(self.count)
            self.count += 1

            self.logger.info('File: book_id={}'.format(book_id))

            book_format = BookFormat(self.db, book_id)

            if book_format.file_path:
                self.books_count += 1

                if getsize(book_format.file_path) <= self.limits['filesize']:
                    self.valid_ids.append(book_id)
                    self.logger.info('File ok: book_id={}'.format(book_id))
                else:
                    self.logger.info('Filesize exceeded: book_id={}'.format(book_id))
            else:
                self.logger.info('Unsupported format: book_id={}'.format(book_id))

        self.resultsAvailable.emit(self.books_count, self.valid_ids)
        self.finished.emit()
