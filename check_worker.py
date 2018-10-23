__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from PyQt5.Qt import QObject, pyqtSignal, QNetworkAccessManager, QNetworkReply
from os.path import getsize
import json

from calibre_plugins.bookfusion.config import prefs
from calibre_plugins.bookfusion import api


class CheckWorker(QObject):
    finished = pyqtSignal()
    aborted = pyqtSignal(str)
    readyForNext = pyqtSignal()
    progress = pyqtSignal(int)
    limitsAvailable = pyqtSignal(dict)
    resultsAvailable = pyqtSignal(int, list)

    def __init__(self, db, logger, book_ids):
        QObject.__init__(self)

        self.db = db
        self.logger = logger
        self.book_ids = book_ids
        self.api_key = prefs['api_key']
        self.reply = None
        self.canceled = False

    def start(self):
        self.network = QNetworkAccessManager()
        self.network.authenticationRequired.connect(self.auth)
        self.readyForNext.connect(self.check_next)

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

    def auth(self, reply, authenticator):
        if not authenticator.user():
            authenticator.setUser(self.api_key)
            authenticator.setPassword('')

    def fetch_limits(self):
        self.req = api.build_request('/limits')
        self.reply = self.network.get(self.req)
        self.reply.finished.connect(self.finish_fetch_limits)

    def finish_fetch_limits(self):
        if self.canceled:
            return

        abort = False

        error = self.reply.error()
        if error == QNetworkReply.AuthenticationRequiredError:
            abort = True
            self.aborted.emit('Invalid API key.')
            self.logger.info('Fetch limits: AuthenticationRequiredError')
        elif error == QNetworkReply.NoError:
            resp = self.reply.readAll()
            self.logger.info('Fetch limits response: {}'.format(resp))
            self.limits = json.loads(resp.data())
            self.limitsAvailable.emit(self.limits)
        elif error == QNetworkReply.OperationCanceledError:
            abort = True
            self.logger.info('Fetch limits: OperationCanceledError')
        else:
            abort = True
            self.aborted.emit('Error {}.'.format(error))
            self.logger.info('Fetch limits error: {}'.format(error))

        self.reply.deleteLater()
        self.reply = None

        if abort:
            self.finished.emit()
        else:
            self.readyForNext.emit()

    def check_next(self):
        if self.canceled:
            return

        if len(self.pending_book_ids) == 0:
            self.resultsAvailable.emit(self.books_count, self.valid_ids)
            self.finished.emit()
            return

        self.progress.emit(self.count)
        self.count += 1

        book_id = self.pending_book_ids.pop()

        fmts = self.db.formats(book_id)
        if len(fmts) > 0:
            fmt = fmts[0]
            if 'EPUB' in fmts:
                fmt = 'EPUB'
            file_path = self.db.format_abspath(book_id, fmt)

            self.books_count += 1

            if getsize(file_path) <= self.limits['filesize']:
                self.valid_ids.append(book_id)
                self.logger.info('File ok: book_id={}'.format(book_id))
            else:
                self.logger.info('Filesize exceeded: book_id={}'.format(book_id))
        else:
            self.logger.info('Missing file: book_id={}'.format(book_id))

        self.readyForNext.emit()
