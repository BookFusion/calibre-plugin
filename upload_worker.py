__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from PyQt5.Qt import QObject, pyqtSignal, QNetworkAccessManager, QNetworkRequest, QNetworkReply, \
    QHttpMultiPart, QHttpPart, QFile, QFileInfo, QIODevice
from os.path import getsize
from hashlib import sha256
import json

from calibre_plugins.bookfusion.config import prefs
from calibre_plugins.bookfusion import api


class UploadWorker(QObject):
    finished = pyqtSignal()
    readyForNext = pyqtSignal()
    progress = pyqtSignal(int)
    uploadProgress = pyqtSignal(int, int)
    uploaded = pyqtSignal(int)
    skipped = pyqtSignal(int)
    failed = pyqtSignal(int, str)
    aborted = pyqtSignal(str)

    def __init__(self, db, book_ids):
        QObject.__init__(self)

        self.db = db
        self.pending_book_ids = book_ids
        self.api_key = prefs['api_key']
        self.reply = None
        self.canceled = False

    def start(self):
        self.network = QNetworkAccessManager()
        self.network.authenticationRequired.connect(self.auth)
        self.readyForNext.connect(self.sync)

        self.count = 0
        self.readyForNext.emit()

    def cancel(self):
        self.canceled = True
        if self.reply:
            self.reply.abort()
        self.finished.emit()

    def auth(self, reply, authenticator):
        if not authenticator.user():
            authenticator.setUser(self.api_key)
            authenticator.setPassword('')

    def sync(self):
        if len(self.pending_book_ids) == 0:
            self.finished.emit()
            return

        self.progress.emit(self.count)
        self.count += 1

        self.book_id = self.pending_book_ids.pop()
        print 'book_id: ', self.book_id

        fmts = self.db.formats(self.book_id)
        if len(fmts) > 0:
            fmt = fmts[0]
            if 'EPUB' in fmts:
                fmt = 'EPUB'
            self.file_path = self.db.format_abspath(self.book_id, fmt)

            self.check()
        else:
            self.failed.emit(self.book_id, 'file is missing')
            self.readyForNext.emit()

    def check(self):
        h = sha256()
        h.update(str(getsize(self.file_path)))
        h.update('\0')
        with open(self.file_path, 'rb') as file:
            block = file.read(65536)
            while len(block) > 0:
                h.update(block)
                block = file.read(65536)
        digest = h.hexdigest()

        self.req = api.build_request('/uploads/' + digest)

        self.reply = self.network.get(self.req)
        self.reply.finished.connect(self.finish_check)

    def finish_check(self):
        abort = False
        skip = False

        error = self.reply.error()
        if error == QNetworkReply.AuthenticationRequiredError:
            abort = True
            self.aborted.emit('Invalid API key.'.format(self.reply.error()))
        elif error == QNetworkReply.NoError:
            skip = True
            self.skipped.emit(self.book_id)
        elif error == QNetworkReply.ContentNotFoundError:
            None
        elif error == QNetworkReply.OperationCanceledError:
            abort = True
        else:
            abort = True
            self.aborted.emit('Error {}.'.format(error))

        self.reply.deleteLater()
        self.reply = None

        if abort:
            self.finished.emit()
        else:
            if skip:
                self.readyForNext.emit()
            else:
                self.upload()

    def upload(self):
        self.file = QFile(self.file_path)
        self.file.open(QIODevice.ReadOnly)

        cover_path = self.db.cover(self.book_id, as_path=True)
        if cover_path:
            self.cover = QFile(cover_path)
            self.cover.open(QIODevice.ReadOnly)
        else:
            self.cover = None

        metadata = self.db.get_proxy_metadata(self.book_id)
        language = next(iter(metadata.languages), None)
        isbn = metadata.isbn
        issued_on = metadata.pubdate.date().isoformat()
        if issued_on == '0101-01-01':
            issued_on = None

        self.req = api.build_request('/uploads')

        self.req_body = QHttpMultiPart(QHttpMultiPart.FormDataType)
        self.req_body.append(self.build_req_part('metadata[title]', metadata.title))
        if language:
            self.req_body.append(self.build_req_part('metadata[language]', language))
        if isbn:
            self.req_body.append(self.build_req_part('metadata[isbn]', isbn))
        if issued_on:
            self.req_body.append(self.build_req_part('metadata[issued_on]', issued_on))
        for author in metadata.authors:
            self.req_body.append(self.build_req_part('metadata[author_list][]', author))
        for tag in metadata.tags:
            self.req_body.append(self.build_req_part('metadata[tag_list][]', tag))
        if self.cover:
            self.req_body.append(self.build_req_part('metadata[cover]', self.cover))

        self.req_body.append(self.build_req_part('file', self.file))

        self.reply = self.network.post(self.req, self.req_body)
        self.reply.finished.connect(self.finish)
        self.reply.uploadProgress.connect(self.upload_progress)

    def finish(self):
        if self.file:
            self.file.close()

        if self.cover:
            self.cover.remove()

        if self.canceled:
            return

        abort = False

        error = self.reply.error()
        if error == QNetworkReply.AuthenticationRequiredError:
            abort = True
            self.aborted.emit('Invalid API key.'.format(error))
        elif error == QNetworkReply.NoError:
            self.uploaded.emit(self.book_id)
        elif error == QNetworkReply.UnknownContentError:
            if self.reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) == 422:
                resp = self.reply.readAll()
                print 'Response: ', resp
                msg = json.loads(resp.data())['error']
                self.failed.emit(self.book_id, msg)
        elif error == QNetworkReply.OperationCanceledError:
            abort = True
        else:
            abort = True
            self.aborted.emit('Error {}.'.format(error))

        self.reply.deleteLater()
        self.reply = None

        if abort:
            self.finished.emit()
        else:
            self.readyForNext.emit()

    def build_req_part(self, name, value):
        part = QHttpPart()
        part.setHeader(QNetworkRequest.ContentTypeHeader, None)
        if isinstance(value, QFile):
            filename = QFileInfo(value).fileName()
            part.setHeader(
                QNetworkRequest.ContentDispositionHeader,
                'form-data; name="{}"; filename="{}"'.format(self.escape_quotes(name), self.escape_quotes(filename))
            )
            part.setBodyDevice(value)
        else:
            part.setHeader(
                QNetworkRequest.ContentDispositionHeader,
                'form-data; name="{}"'.format(self.escape_quotes(name))
            )
            part.setBody(bytes(value))
        return part

    def escape_quotes(self, value):
        return value.replace('"', '\\"')

    def upload_progress(self, sent, total):
        self.uploadProgress.emit(sent, total)
