__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from PyQt5.Qt import QObject, pyqtSignal, QNetworkRequest, QUrl, QNetworkReply, \
    QHttpMultiPart, QHttpPart, QFile, QFileInfo, QIODeviceBase
from os import path
from hashlib import sha256
import json

from calibre_plugins.bookfusion.config import prefs
from calibre_plugins.bookfusion import api


class UploadWorker(QObject):
    syncRequested = pyqtSignal(int, str)
    readyForNext = pyqtSignal(int)
    uploadProgress = pyqtSignal(int, int, int)
    uploaded = pyqtSignal(int)
    updated = pyqtSignal(int)
    skipped = pyqtSignal(int)
    failed = pyqtSignal(int, str)
    aborted = pyqtSignal(str)

    def __init__(self, index, reupload, db, logger, network):
        QObject.__init__(self)

        self.index = index
        self.reupload = reupload
        self.db = db
        self.logger = logger
        self.network = network
        self.reply = None
        self.canceled = False

        self.retries = 0

    def start(self):
        self.syncRequested.connect(self.sync)
        self.readyForNext.emit(self.index)

    def cancel(self):
        self.canceled = True
        if self.reply:
            self.reply.abort()

    def sync(self, book_id, file_path):
        self.log_info('Sync: book_id={}'.format(book_id))

        self.book_id = book_id
        self.file_path = file_path

        self.check()

    def check(self):
        self.digest = None

        identifiers = self.db.get_proxy_metadata(self.book_id).identifiers
        if identifiers.get('bookfusion'):
            self.is_search_req = False
            self.req = api.build_request('/uploads/' + identifiers['bookfusion'])
            self.log_info('Upload check: bookfusion={}'.format(identifiers['bookfusion']))
        elif identifiers.get('isbn'):
            self.is_search_req = True
            self.req = api.build_request('/uploads', {'isbn': identifiers['isbn']})
            self.log_info('Upload check: isbn={}'.format(identifiers['isbn']))
        else:
            self.calculate_digest()

            self.is_search_req = False
            self.req = api.build_request('/uploads/' + self.digest)
            self.log_info('Upload check: digest={}'.format(self.digest))

        self.reply = self.network.get(self.req)
        self.reply.finished.connect(self.complete_check)

    def complete_check(self):
        abort = False
        skip = False
        update = False
        result = None

        error = self.reply.error()
        if error == QNetworkReply.NetworkError.AuthenticationRequiredError:
            abort = True
            self.aborted.emit('Invalid API key.')
            self.log_info('Upload check: AuthenticationRequiredError')
        elif error == QNetworkReply.NetworkError.NoError:
            resp = self.reply.readAll()
            self.log_info('Upload check response: {}'.format(resp))

            if self.is_search_req:
                results = json.loads(resp.data())
                if len(results) > 0:
                    result = results[0]
            else:
                result = json.loads(resp.data())

            if result is not None:
                self.set_bookfusion_id(result['id'])
                update = True
        elif error == QNetworkReply.NetworkError.ContentNotFoundError:
            self.log_info('Upload check: ContentNotFoundError')
        elif error == QNetworkReply.NetworkError.InternalServerError:
            self.log_info('Upload check: InternalServerError')
            resp = self.reply.readAll()
            self.log_info('Upload check response: {}'.format(resp))
        elif error == QNetworkReply.NetworkError.UnknownServerError:
            self.log_info('Upload check: UnknownServerError')
            resp = self.reply.readAll()
            self.log_info('Upload check response: {}'.format(resp))
        elif error == QNetworkReply.NetworkError.OperationCanceledError:
            abort = True
            self.log_info('Upload check: OperationCanceledError')
        else:
            abort = True
            self.aborted.emit('Error {}.'.format(error))
            self.log_info('Upload check error: {}'.format(error))

        self.reply.deleteLater()
        self.reply = None

        if not abort:
            if skip:
                self.readyForNext.emit(self.index)
            else:
                self.metadata_digest = self.get_metadata_digest()
                if not result is None and self.metadata_digest == result['calibre_metadata_digest'] and not self.reupload:
                    self.skipped.emit(self.book_id)
                    self.readyForNext.emit(self.index)
                else:
                    if update:
                        self.update()
                    else:
                        self.init_upload()

    def init_upload(self):
        self.calculate_digest()

        self.req = api.build_request('/uploads/init')
        self.req_body = QHttpMultiPart(QHttpMultiPart.ContentType.FormDataType)
        self.req_body.append(self.build_req_part('filename', path.basename(self.file_path)))
        self.req_body.append(self.build_req_part('digest', self.digest))

        self.reply = self.network.post(self.req, self.req_body)
        self.reply.finished.connect(self.complete_init_upload)

    def complete_init_upload(self):
        resp, retry, abort = self.complete_req('Upload init', return_json = True)

        if retry:
            self.init_upload()
            return

        if abort:
            return

        if resp is not None:
            self.upload_url = resp['url']
            self.upload_params = resp['params']
            self.upload()
        else:
            self.readyForNext.emit(self.index)

    def upload(self):
        self.file = QFile(self.file_path)
        self.file.open(QIODeviceBase.OpenModeFlag.ReadOnly)

        self.req = QNetworkRequest(QUrl(self.upload_url))

        self.req_body = QHttpMultiPart(QHttpMultiPart.ContentType.FormDataType)
        for key, value in self.upload_params.items():
            self.log_info('{}={}'.format(key, value))
            self.req_body.append(self.build_req_part(key, value))
        self.req_body.append(self.build_req_part('file', self.file))

        self.reply = self.network.post(self.req, self.req_body)
        self.reply.finished.connect(self.complete_upload)
        self.reply.uploadProgress.connect(self.upload_progress)

    def complete_upload(self):
        if self.file:
            self.file.close()

        resp, retry, abort = self.complete_req('Upload')

        if retry:
            self.upload()
            return

        if abort:
            return

        if resp is not None:
            self.finalize_upload()
        else:
            self.readyForNext.emit(self.index)

    def finalize_upload(self):
        self.req = api.build_request('/uploads/finalize')

        self.req_body = QHttpMultiPart(QHttpMultiPart.ContentType.FormDataType)
        self.req_body.append(self.build_req_part('key', self.upload_params['key']))
        self.req_body.append(self.build_req_part('digest', self.digest))
        self.append_metadata_req_parts()

        self.reply = self.network.post(self.req, self.req_body)
        self.reply.finished.connect(self.complete_finalize_upload)

    def complete_finalize_upload(self):
        self.clean_metadata_req()

        resp, retry, abort = self.complete_req('Upload finalize', return_json = True)

        if retry:
            self.finalize_upload()
            return

        if abort:
            return

        if resp is not None:
            self.set_bookfusion_id(resp['id'])
            self.uploaded.emit(self.book_id)

        self.readyForNext.emit(self.index)

    def update(self):
        if not prefs['update_metadata'] and not self.reupload:
            self.skipped.emit(self.book_id)
            self.readyForNext.emit(self.index)
            return

        identifiers = self.db.get_proxy_metadata(self.book_id).identifiers
        if not identifiers.get('bookfusion') and not self.reupload:
            self.skipped.emit(self.book_id)
            self.readyForNext.emit(self.index)
            return

        self.req = api.build_request('/uploads/' + identifiers['bookfusion'])
        self.req_body = QHttpMultiPart(QHttpMultiPart.ContentType.FormDataType)

        if self.reupload:
            self.file = QFile(self.file_path)
            self.file.open(QIODeviceBase.OpenModeFlag.ReadOnly)
            self.req_body.append(self.build_req_part('file', self.file))

        self.append_metadata_req_parts()

        self.reply = self.network.put(self.req, self.req_body)
        self.reply.finished.connect(self.complete_update)

    def complete_update(self):
        self.clean_metadata_req()

        resp, retry, abort = self.complete_req('Update')

        if retry:
            self.update()
            return

        if abort:
            return

        if resp is not None:
            self.updated.emit(self.book_id)

        self.readyForNext.emit(self.index)

    def upload_progress(self, sent, total):
        self.uploadProgress.emit(self.book_id, sent, total)

    def log_info(self, msg):
        self.logger.info('[worker-{}] {}'.format(self.index, msg))

    def get_metadata_digest(self):
        metadata = self.db.get_proxy_metadata(self.book_id)

        h = sha256()

        language = next(iter(metadata.languages), None)
        summary = metadata.comments
        isbn = metadata.isbn
        issued_on = metadata.pubdate.date().isoformat()
        if issued_on == '0101-01-01':
            issued_on = None

        h.update(metadata.title.encode('utf-8'))
        if summary:
            h.update(summary.encode('utf-8'))
        if language:
            h.update(language.encode('utf-8'))
        if isbn:
            h.update(isbn.encode('utf-8'))
        if issued_on:
            h.update(issued_on.encode('utf-8'))

        for series_item in self.get_series(metadata):
            h.update(series_item['title'].encode('utf-8'))
            if series_item['index'] is not None:
                h.update(str(series_item['index']).encode('utf-8'))

        for author in metadata.authors:
            h.update(author.encode('utf-8'))
        for tag in metadata.tags:
            h.update(tag.encode('utf-8'))

        bookshelves = self.get_bookshelves(metadata)
        if bookshelves is not None:
            for bookshelf in bookshelves:
                h.update(bookshelf.encode('utf-8'))

        cover_path = self.db.cover(self.book_id, as_path=True)
        if cover_path:
            h.update(bytes(path.getsize(cover_path)))
            h.update(b'\0')
            with open(cover_path, 'rb') as file:
                block = file.read(65536)
                while len(block) > 0:
                    h.update(block)
                    block = file.read(65536)

        return h.hexdigest()

    def append_metadata_req_parts(self):
        metadata = self.db.get_proxy_metadata(self.book_id)
        language = next(iter(metadata.languages), None)
        summary = metadata.comments
        isbn = metadata.isbn
        issued_on = metadata.pubdate.date().isoformat()
        if issued_on == '0101-01-01':
            issued_on = None

        self.req_body.append(self.build_req_part('metadata[calibre_metadata_digest]', self.metadata_digest))
        self.req_body.append(self.build_req_part('metadata[title]', metadata.title))
        if summary:
            self.req_body.append(self.build_req_part('metadata[summary]', summary))
        if language:
            self.req_body.append(self.build_req_part('metadata[language]', language))
        if isbn:
            self.req_body.append(self.build_req_part('metadata[isbn]', isbn))
        if issued_on:
            self.req_body.append(self.build_req_part('metadata[issued_on]', issued_on))

        for series_item in self.get_series(metadata):
            self.req_body.append(self.build_req_part('metadata[series][][title]', series_item['title']))
            if series_item['index'] is not None:
                self.req_body.append(self.build_req_part('metadata[series][][index]', str(series_item['index'])))

        for author in metadata.authors:
            self.req_body.append(self.build_req_part('metadata[author_list][]', author))
        for tag in metadata.tags:
            self.req_body.append(self.build_req_part('metadata[tag_list][]', tag))

        bookshelves = self.get_bookshelves(metadata)
        if bookshelves is not None:
            self.req_body.append(self.build_req_part('metadata[bookshelves][]', ''))
            for bookshelf in bookshelves:
                self.req_body.append(self.build_req_part('metadata[bookshelves][]', bookshelf))

        cover_path = self.db.cover(self.book_id, as_path=True)
        if cover_path:
            self.cover = QFile(cover_path)
            self.cover.open(QIODeviceBase.OpenModeFlag.ReadOnly)
            self.req_body.append(self.build_req_part('metadata[cover]', self.cover))
        else:
            self.cover = None

    def clean_metadata_req(self):
        if self.cover:
            self.cover.remove()

    def build_req_part(self, name, value):
        part = QHttpPart()
        part.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, None)
        if isinstance(value, QFile):
            filename = QFileInfo(value).fileName()
            part.setHeader(
                QNetworkRequest.KnownHeaders.ContentDispositionHeader,
                'form-data; name="{}"; filename="{}"'.format(self.escape_quotes(name), self.escape_quotes(filename))
            )
            part.setBodyDevice(value)
        else:
            part.setHeader(
                QNetworkRequest.KnownHeaders.ContentDispositionHeader,
                'form-data; name="{}"'.format(self.escape_quotes(name))
            )
            part.setBody(value.encode('utf-8'))
        return part

    def complete_req(self, tag, return_json = False):
        retry = False
        abort = False

        if self.canceled:
            abort = True

        error = self.reply.error()
        resp = None
        if error == QNetworkReply.NetworkError.AuthenticationRequiredError:
            abort = True
            self.aborted.emit('Invalid API key.')
            self.log_info('{}: AuthenticationRequiredError'.format(tag))
        elif error == QNetworkReply.NetworkError.NoError:
            resp = self.reply.readAll()
            self.log_info('{} response: {}'.format(tag, resp))
            if return_json:
                try:
                    resp = json.loads(resp.data())
                except ValueError as e:
                    resp = None
                    self.log_info('{}: {}'.format(tag, e))
                    self.failed.emit(self.book_id, 'Cannot parse the server response')
        elif error == QNetworkReply.NetworkError.UnknownContentError:
            if self.reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) == 422:
                err_resp = self.reply.readAll()
                self.log_info('{} response: {}'.format(tag, err_resp))
                msg = json.loads(err_resp.data())['error']
                self.failed.emit(self.book_id, msg)
            else:
                self.log_info('{}: UnknownContentError'.format(tag))
        elif error == QNetworkReply.NetworkError.InternalServerError:
            self.log_info('{}: InternalServerError'.format(tag))
            err_resp = self.reply.readAll()
            self.log_info('{} response: {}'.format(tag, err_resp))
        elif error == QNetworkReply.NetworkError.UnknownServerError:
            self.log_info('{}: UnknownServerError'.format(tag))
            err_resp = self.reply.readAll()
            self.log_info('{} response: {}'.format(tag, err_resp))
        elif error == QNetworkReply.NetworkError.ConnectionRefusedError or \
             error == QNetworkReply.NetworkError.RemoteHostClosedError or \
             error == QNetworkReply.NetworkError.HostNotFoundError or \
             error == QNetworkReply.NetworkError.TimeoutError or \
             error == QNetworkReply.NetworkError.TemporaryNetworkFailureError:
            retry = True
            self.log_info('{}: {}'.format(tag, error))
        elif error == QNetworkReply.NetworkError.OperationCanceledError:
            abort = True
            self.log_info('{}: OperationCanceledError'.format(tag))
        else:
            abort = True
            self.aborted.emit('Error {}.'.format(error))
            self.log_info('{} error: {}'.format(tag, error))

        self.reply.deleteLater()
        self.reply = None

        if retry:
            self.retries += 1

            if self.retries > 2:
                self.retries = 0
                self.aborted.emit('Error {}.'.format(error))
                retry = False
            else:
                abort = False
        else:
            self.retries = 0

        return (resp, retry, abort)

    def calculate_digest(self):
        if self.digest is not None:
            return

        h = sha256()
        h.update(bytes(path.getsize(self.file_path)))
        h.update(b'\0')
        with open(self.file_path, 'rb') as file:
            block = file.read(65536)
            while len(block) > 0:
                h.update(block)
                block = file.read(65536)
        self.digest = h.hexdigest()

    def escape_quotes(self, value):
        return value.replace('"', '\\"')

    def set_bookfusion_id(self, bookfusion_id):
        identifiers = self.db.get_proxy_metadata(self.book_id).identifiers
        identifiers['bookfusion'] = str(bookfusion_id)
        self.db.set_field('identifiers', {self.book_id: identifiers})

    def get_bookshelves(self, metadata):
        bookshelves_custom_column = prefs['bookshelves_custom_column']
        if bookshelves_custom_column:
            try:
                bookshelves = getattr(metadata, bookshelves_custom_column)
            except AttributeError:
                return None
            if bookshelves is None:
                return []
            if isinstance(bookshelves, list):
                return bookshelves
            else:
                return [bookshelves]
        else:
            return None

    def get_series(self, metadata):
        series_items = []
        if metadata.series:
            series_items.append({'title': metadata.series, 'index': metadata.series_index})

        for key, meta in self.db.field_metadata.custom_iteritems():
            if meta['datatype'] == 'series':
                title = getattr(metadata, key)
                if title:
                    found = False
                    for series_item in series_items:
                        if series_item['title'].lower() == title.lower():
                            found = True
                    if not found:
                        index = getattr(metadata, key + '_index')
                        series_items.append({'title': title, 'index': index})

        return series_items
