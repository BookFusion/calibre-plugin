__copyright__ = '2020, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from PyQt5.Qt import QObject, pyqtSignal, QThread, QNetworkAccessManager

from calibre_plugins.bookfusion.config import prefs
from calibre_plugins.bookfusion.book_format import BookFormat
from calibre_plugins.bookfusion.upload_worker import UploadWorker


class UploadManager(QObject):
    finished = pyqtSignal()
    readyForNext = pyqtSignal()
    progress = pyqtSignal(int)
    uploadProgress = pyqtSignal(int, int, int)
    started = pyqtSignal(int)
    uploaded = pyqtSignal(int)
    updated = pyqtSignal(int)
    skipped = pyqtSignal(int)
    failed = pyqtSignal(int, str)
    aborted = pyqtSignal(str)

    def __init__(self, db, logger, book_ids, reupload):
        QObject.__init__(self)

        self.db = db
        self.logger = logger
        self.pending_book_ids = book_ids
        self.reupload = reupload
        self.canceled = False
        self.api_key = prefs['api_key']

        self.finished_count = 0
        self.workers = []

    def start(self):
        self.readyForNext.connect(self.sync)

        self.network = QNetworkAccessManager(self)
        self.count = 0

        for index in range(prefs['threads']):
            worker = UploadWorker(index, self.reupload, self.db, self.logger, self.network)
            worker.readyForNext.connect(self.sync)
            worker.uploadProgress.connect(self.uploadProgress)
            worker.uploaded.connect(self.uploaded)
            worker.updated.connect(self.updated)
            worker.skipped.connect(self.skipped)
            worker.failed.connect(self.failed)
            worker.aborted.connect(self.abort)
            self.workers.append(worker)
            self.logger.info('starting worker %s' % index)
            worker.start()

    def cancel(self):
        self.canceled = True
        for worker in self.workers:
            worker.cancel()
        self.finished.emit()

    def sync(self, index):
        if len(self.pending_book_ids) == 0:
            self.finished_count += 1
            if self.finished_count == len(self.workers):
                self.finished.emit()
            return

        self.progress.emit(self.count)
        self.count += 1

        book_id = self.pending_book_ids.pop()
        self.logger.info('Upload book: book_id={}; title={}'.format(book_id, self.db.get_proxy_metadata(book_id).title))

        book_format = BookFormat(self.db, book_id)

        if book_format.file_path:
            self.started.emit(book_id)
            worker = self.workers[index]
            worker.syncRequested.emit(book_id, book_format.file_path)
        else:
            self.failed.emit(book_id, 'unsupported format')
            self.readyForNext.emit(index)

    def abort(self, msg):
        self.cancel()
        self.aborted.emit(msg)
