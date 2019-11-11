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
    updated = pyqtSignal(int)
    skipped = pyqtSignal(int)
    failed = pyqtSignal(int, str)
    aborted = pyqtSignal(str)

    def __init__(self, db, logger, book_ids):
        QObject.__init__(self)

        self.db = db
        self.logger = logger
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

        self.logger.info('Upload book: book_id={}; title={}'.format(self.book_id, self.db.get_proxy_metadata(self.book_id).title))

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
        identifiers = self.db.get_proxy_metadata(self.book_id).identifiers
        if identifiers.get('bookfusion'):
            self.is_search_req = False
            self.req = api.build_request('/uploads/' + identifiers['bookfusion'])
            self.logger.info('Upload check: bookfusion={}'.format(identifiers['bookfusion']))
        elif identifiers.get('isbn'):
            self.is_search_req = True
            self.req = api.build_request('/uploads', {'isbn': identifiers['isbn']})
            self.logger.info('Upload check: isbn={}'.format(identifiers['isbn']))
        else:
            h = sha256()
            h.update(str(getsize(self.file_path)))
            h.update('\0')
            with open(self.file_path, 'rb') as file:
                block = file.read(65536)
                while len(block) > 0:
                    h.update(block)
                    block = file.read(65536)
            digest = h.hexdigest()

            self.is_search_req = False
            self.req = api.build_request('/uploads/' + digest)
            self.logger.info('Upload check: digest={}'.format(digest))

        self.reply = self.network.get(self.req)
        self.reply.finished.connect(self.finish_check)

    def finish_check(self):
        abort = False
        skip = False
        update = False

        error = self.reply.error()
        if error == QNetworkReply.AuthenticationRequiredError:
            abort = True
            self.aborted.emit('Invalid API key.')
            self.logger.info('Upload check: AuthenticationRequiredError')
        elif error == QNetworkReply.NoError:
            resp = self.reply.readAll()
            self.logger.info('Upload check response: {}'.format(resp))

            if self.is_search_req:
                results = json.loads(resp.data())
                if len(results) > 0:
                    self.set_bookfusion_id(results[0]['id'])
                    update = True
            else:
                self.set_bookfusion_id(json.loads(resp.data())['id'])
                update = True
        elif error == QNetworkReply.ContentNotFoundError:
            self.logger.info('Upload check: ContentNotFoundError')
        elif error == QNetworkReply.OperationCanceledError:
            abort = True
            self.logger.info('Upload check: OperationCanceledError')
        else:
            abort = True
            self.aborted.emit('Error {}.'.format(error))
            self.logger.info('Upload check error: {}'.format(error))

        self.reply.deleteLater()
        self.reply = None

        if abort:
            self.finished.emit()
        else:
            if skip:
                self.readyForNext.emit()
            elif update:
                self.update()
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

        self.req = api.build_request('/uploads')

        self.req_body = QHttpMultiPart(QHttpMultiPart.FormDataType)
        self.append_metadata_req_parts()
        if self.cover:
            self.req_body.append(self.build_req_part('metadata[cover]', self.cover))

        self.req_body.append(self.build_req_part('file', self.file))

        self.reply = self.network.post(self.req, self.req_body)
        self.reply.finished.connect(self.finish_upload)
        self.reply.uploadProgress.connect(self.upload_progress)

    def finish_upload(self):
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
            self.aborted.emit('Invalid API key.')
            self.logger.info('Upload: AuthenticationRequiredError')
        elif error == QNetworkReply.NoError:
            resp = self.reply.readAll()
            self.logger.info('Upload response: {}'.format(resp))

            self.set_bookfusion_id(json.loads(resp.data())['id'])

            self.uploaded.emit(self.book_id)
        elif error == QNetworkReply.UnknownContentError:
            if self.reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) == 422:
                resp = self.reply.readAll()
                self.logger.info('Upload response: {}'.format(resp))
                msg = json.loads(resp.data())['error']
                self.failed.emit(self.book_id, msg)
            else:
                self.logger.info('Upload: UnknownContentError')
        elif error == QNetworkReply.OperationCanceledError:
            abort = True
            self.logger.info('Upload: OperationCanceledError')
        else:
            abort = True
            self.aborted.emit('Error {}.'.format(error))
            self.logger.info('Upload error: {}'.format(error))

        self.reply.deleteLater()
        self.reply = None

        if abort:
            self.finished.emit()
        else:
            self.readyForNext.emit()

    def update(self):
        if not prefs['update_metadata']:
            self.skipped.emit(self.book_id)
            self.readyForNext.emit()
            return

        identifiers = self.db.get_proxy_metadata(self.book_id).identifiers
        if not identifiers.get('bookfusion'):
            self.skipped.emit(self.book_id)
            self.readyForNext.emit()
            return

        self.req = api.build_request('/uploads/' + identifiers['bookfusion'])
        self.req_body = QHttpMultiPart(QHttpMultiPart.FormDataType)
        self.append_metadata_req_parts()

        self.reply = self.network.put(self.req, self.req_body)
        self.reply.finished.connect(self.finish_update)

    def finish_update(self):
        if self.canceled:
            return

        abort = False

        error = self.reply.error()
        if error == QNetworkReply.AuthenticationRequiredError:
            abort = True
            self.aborted.emit('Invalid API key.')
            self.logger.info('Update: AuthenticationRequiredError')
        elif error == QNetworkReply.NoError:
            resp = self.reply.readAll()
            self.logger.info('Update response: {}'.format(resp))

            self.updated.emit(self.book_id)
        elif error == QNetworkReply.UnknownContentError:
            if self.reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) == 422:
                resp = self.reply.readAll()
                self.logger.info('Update response: {}'.format(resp))
                msg = json.loads(resp.data())['error']
                self.failed.emit(self.book_id, msg)
            else:
                self.logger.info('Update: UnknownContentError')
        elif error == QNetworkReply.OperationCanceledError:
            abort = True
            self.logger.info('Update: OperationCanceledError')
        else:
            abort = True
            self.aborted.emit('Error {}.'.format(error))
            self.logger.info('Update error: {}'.format(error))

        self.reply.deleteLater()
        self.reply = None

        if abort:
            self.finished.emit()
        else:
            self.readyForNext.emit()

    def append_metadata_req_parts(self):
        metadata = self.db.get_proxy_metadata(self.book_id)
        language = next(iter(metadata.languages), None)
        summary = metadata.comments
        isbn = metadata.isbn
        issued_on = metadata.pubdate.date().isoformat()
        series = metadata.series
        series_index = metadata.series_index
        if issued_on == '0101-01-01':
            issued_on = None

        self.req_body.append(self.build_req_part('metadata[title]', metadata.title))
        if summary:
            self.req_body.append(self.build_req_part('metadata[summary]', summary))
        if language:
            self.req_body.append(self.build_req_part('metadata[language]', language))
        if isbn:
            self.req_body.append(self.build_req_part('metadata[isbn]', isbn))
        if issued_on:
            self.req_body.append(self.build_req_part('metadata[issued_on]', issued_on))
        if series:
            self.req_body.append(self.build_req_part('metadata[series][][title]', series))
            if series_index:
                self.req_body.append(self.build_req_part('metadata[series][][index]', series_index))
        for author in metadata.authors:
            self.req_body.append(self.build_req_part('metadata[author_list][]', author))
        for tag in metadata.tags:
            self.req_body.append(self.build_req_part('metadata[tag_list][]', tag))


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

    def set_bookfusion_id(self, bookfusion_id):
        identifiers = self.db.get_proxy_metadata(self.book_id).identifiers
        identifiers['bookfusion'] = str(bookfusion_id)
        self.db.set_field('identifiers', {self.book_id: identifiers})

    def upload_progress(self, sent, total):
        self.uploadProgress.emit(sent, total)
