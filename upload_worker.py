__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from PyQt5.Qt import QObject, pyqtSignal, QThread
import urllib.request
import urllib.error
from os import path
from hashlib import sha256
import json
import time

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

    def __init__(self, index, reupload, db, logger):
        QObject.__init__(self)

        self.index = index
        self.reupload = reupload
        self.db = db
        self.logger = logger
        self.canceled = False

        self.retries = 0

    def start(self):
        self.syncRequested.connect(self.sync)
        self.readyForNext.emit(self.index)

    def cancel(self):
        self.canceled = True

    def sync(self, book_id, file_path):
        self.book_id = book_id
        self.file_path = file_path

        self.check()

    def check(self):
        self.digest = None

        is_search_req = False

        identifiers = self.db.get_proxy_metadata(self.book_id).identifiers
        if identifiers.get('bookfusion'):
            req = api.build_request('/uploads/' + identifiers['bookfusion'])
            self.log_info('Upload check: bookfusion={}'.format(identifiers['bookfusion']))
        elif identifiers.get('isbn'):
            is_search_req = True
            req = api.build_request('/uploads', {'isbn': identifiers['isbn']})
            self.log_info('Upload check: isbn={}'.format(identifiers['isbn']))
        else:
            self.calculate_digest()
            req = api.build_request('/uploads/' + self.digest)
            self.log_info('Upload check: digest={}'.format(self.digest))

        abort = False
        skip = False
        update = False
        result = None

        try:
            with api.build_opener().open(req) as f:
                resp = f.read()
                self.log_info('Upload check response: {}'.format(resp))

                if is_search_req:
                    results = json.loads(resp)
                    if len(results) > 0:
                        result = results[0]
                else:
                    result = json.loads(resp)

                if result is not None:
                    self.set_bookfusion_id(result['id'])
                    update = True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                self.log_info('Upload check: 404')
            else:
                self.log_info('Upload check error: {}'.format(e))

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

        req_body, content_type = api.build_multipart_body([
            {'name': 'filename', 'value': path.basename(self.file_path)},
            {'name': 'digest', 'value': self.digest}
        ])

        req = api.build_request('/uploads/init', data=req_body, headers={'Content-Type': content_type}, method='POST')

        resp, retry, abort = self.complete_req(req, 'Upload init', return_json = True)

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
        req_data_params = []

        for key, value in self.upload_params.items():
            self.log_info('{}={}'.format(key, value))
            req_data_params.append({'name': key, 'value': value})

        req_data_params.append({'name': 'file', 'file': self.file_path})

        req_data, content_type = api.build_multipart_body(req_data_params)
        req = urllib.request.Request(self.upload_url, req_data, {'Content-Type': content_type}, method='POST')

        resp, retry, abort = self.complete_req(req, 'Upload')

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
        req_data_params = [
            {'name': 'key', 'value': self.upload_params['key']},
            {'name': 'digest', 'value': self.digest}
        ]
        self.append_metadata_req_data_params(req_data_params)

        req_body, content_type = api.build_multipart_body(req_data_params)

        req = api.build_request('/uploads/finalize', data=req_body, headers={'Content-Type': content_type}, method='POST')

        resp, retry, abort = self.complete_req(req, 'Upload finalize', return_json = True)

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

        req_data_params = []

        if self.reupload:
            req_data_params.append({'name': 'file', 'file': self.file_path})

        self.append_metadata_req_data_params(req_data_params)

        req_body, content_type = api.build_multipart_body(req_data_params)

        req = api.build_request('/uploads/%s' % identifiers['bookfusion'], data=req_body, headers={'Content-Type': content_type}, method='PATCH')

        resp, retry, abort = self.complete_req(req, 'Update', return_json = True)

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

    def append_metadata_req_data_params(self, req_data_params):
        metadata = self.db.get_proxy_metadata(self.book_id)
        language = next(iter(metadata.languages), None)
        summary = metadata.comments
        isbn = metadata.isbn
        issued_on = metadata.pubdate.date().isoformat()
        if issued_on == '0101-01-01':
            issued_on = None

        req_data_params.append({'name': 'metadata[calibre_metadata_digest]', 'value': self.metadata_digest})
        req_data_params.append({'name': 'metadata[title]', 'value': metadata.title})
        if summary:
            req_data_params.append({'name': 'metadata[summary]', 'value': summary})
        if language:
            req_data_params.append({'name': 'metadata[language]', 'value': language})
        if isbn:
            req_data_params.append({'name': 'metadata[isbn]', 'value': isbn})
        if issued_on:
            req_data_params.append({'name': 'metadata[issued_on]', 'value': issued_on})

        for series_item in self.get_series(metadata):
            req_data_params.append({'name': 'metadata[series][][title]', 'value': series_item['title']})
            if series_item['index'] is not None:
                req_data_params.append({'name': 'metadata[series][][index]', 'value': str(series_item['index'])})

        for author in metadata.authors:
            req_data_params.append({'name': 'metadata[author_list][]', 'value': author})
        for tag in metadata.tags:
            req_data_params.append({'name': 'metadata[tag_list][]', 'value': tag})

        bookshelves = self.get_bookshelves(metadata)
        if bookshelves is not None:
            req_data_params.append({'name': 'metadata[bookshelves][]', 'value': ''})
            for bookshelf in bookshelves:
                req_data_params.append({'name': 'metadata[bookshelves][]', 'value': bookshelf})

        cover_path = self.db.cover(self.book_id, as_path=True)
        if cover_path:
            req_data_params.append({'name': 'metadata[cover]', 'file': cover_path})

    def complete_req(self, req, tag, return_json = False):
        retry = False
        abort = False

        if self.canceled:
            abort = True

        resp = None

        try:
            with api.build_opener().open(req) as f:
                resp = f.read()
                self.log_info('{} response: {}'.format(tag, resp))
                if return_json:
                    try:
                        resp = json.loads(resp)
                    except ValueError as e:
                        resp = None
                        self.log_info('{}: {}'.format(tag, e))
                        self.failed.emit(self.book_id, 'Cannot parse the server response')
        except urllib.error.HTTPError as e:
            if e.code == 422:
                err_resp = e.read()
                self.log_info('{} response: {}'.format(tag, err_resp))
                msg = json.loads(err_resp)['error']
                self.failed.emit(self.book_id, msg)
            else:
                self.log_info('{}: Error {}'.format(tag, e.code))

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
