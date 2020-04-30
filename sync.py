__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from PyQt5.Qt import QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QMessageBox, QLabel, QProgressBar, QThread, \
    QTableWidget, QTableWidgetItem, QRadioButton
from os import path

from calibre_plugins.bookfusion.config import prefs
from calibre_plugins.bookfusion.logger import Logger
from calibre_plugins.bookfusion.check_worker import CheckWorker
from calibre_plugins.bookfusion.upload_worker import UploadWorker


class SyncWidget(QWidget):
    def __init__(self, gui, do_user_config, selected_book_ids, is_sync_selected):
        QWidget.__init__(self, gui)

        self.logger = Logger(path.join(gui.current_db.library_path, 'bookfusion_sync.log'))
        self.logger.info('Open sync dialog: selected_book_ids={}; is_sync_selected={}'.format(selected_book_ids, is_sync_selected))

        if len(selected_book_ids) == 0:
            is_sync_selected = False

        self.worker_thread = None

        self.do_user_config = do_user_config
        self.db = gui.current_db.new_api

        self.selected_book_ids = selected_book_ids

        self.l = QVBoxLayout()
        self.l.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.l)

        self.radio_layout = QVBoxLayout()
        self.l.addLayout(self.radio_layout)

        self.sync_all_radio = QRadioButton('Sync all books')
        self.sync_all_radio.setChecked(not is_sync_selected)
        self.radio_layout.addWidget(self.sync_all_radio)

        sync_selected_radio_label = 'Sync selected books'
        if len(selected_book_ids) > 0:
            sync_selected_radio_label = 'Sync {} selected {}'.format(
                len(selected_book_ids),
                'book' if len(selected_book_ids) == 1 else 'books'
            )
        self.sync_selected_radio = QRadioButton(sync_selected_radio_label)
        self.sync_selected_radio.setChecked(is_sync_selected)
        self.sync_selected_radio.setEnabled(len(selected_book_ids) > 0)
        self.radio_layout.addWidget(self.sync_selected_radio)

        self.btn_layout = QHBoxLayout()
        self.l.addLayout(self.btn_layout)

        self.config_btn = QPushButton('Configure')
        self.config_btn.clicked.connect(self.config)
        self.btn_layout.addWidget(self.config_btn)

        self.btn_layout.addStretch()

        self.start_btn = QPushButton('Start')
        self.start_btn.clicked.connect(self.start)
        self.btn_layout.addWidget(self.start_btn)

        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.clicked.connect(self.cancel)
        self.cancel_btn.hide()
        self.btn_layout.addWidget(self.cancel_btn)

        self.progress = QProgressBar()
        self.progress.hide()
        self.l.addWidget(self.progress)

        self.info = QHBoxLayout()
        self.info.setContentsMargins(0, 0, 0, 0)
        self.l.addLayout(self.info)
        self.msg = QLabel()
        self.info.addWidget(self.msg)
        self.info.addStretch()
        self.log_btn = QLabel('<a href="#">Log</a>')
        self.log_btn.linkActivated.connect(self.toggle_log)
        self.log_btn.hide()
        self.info.addWidget(self.log_btn)

        self.log = QTableWidget(0, 2)
        self.log.setHorizontalHeaderLabels(['Book', 'Message'])
        self.log.horizontalHeader().setStretchLastSection(True)
        self.log.hide()
        self.l.addWidget(self.log)

        self.apply_config()

    def __del__(self):
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.terminate()

    def config(self):
        self.do_user_config(parent=self)
        self.apply_config()

    def apply_config(self):
        configured = bool(prefs['api_key'])
        self.start_btn.setEnabled(configured)

    def start(self):
        self.worker = None
        self.valid_book_ids = None

        if self.sync_selected_radio.isChecked():
            book_ids = list(self.selected_book_ids)
        else:
            book_ids = list(self.db.all_book_ids())

        self.logger.info('Start sync: sync_selected={}; book_ids={}'.format(self.sync_selected_radio.isChecked(), book_ids))

        self.in_progress = True
        self.total = len(book_ids)
        self.update_progress(None)
        self.start_btn.hide()
        self.cancel_btn.show()
        self.config_btn.setEnabled(False)
        self.sync_all_radio.setEnabled(False)
        self.sync_selected_radio.setEnabled(False)
        self.progress.setMaximum(0)
        self.progress.show()

        self.worker_thread = QThread(self)

        self.worker = CheckWorker(self.db, self.logger, book_ids)
        self.worker.finished.connect(self.finish_check)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.progress.connect(self.update_progress)
        self.worker.limitsAvailable.connect(self.apply_limits)
        self.worker.resultsAvailable.connect(self.apply_results)
        self.worker.aborted.connect(self.abort)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.start)
        self.worker_thread.start()

    def apply_limits(self, limits):
        self.logger.info('Limits: {}'.format(limits))
        self.limits = limits

    def apply_results(self, books_count, valid_ids):
        self.logger.info('Check results: books_count={}; valid_ids={}'.format(books_count, valid_ids))
        self.valid_book_ids = valid_ids
        self.books_count = books_count

    def finish_check(self):
        if self.valid_book_ids:
            is_filesize_exceeded = len(self.valid_book_ids) < self.books_count
            is_total_books_exceeded = self.limits['total_books'] and self.books_count > self.limits['total_books']

            if is_filesize_exceeded or is_total_books_exceeded:
                if self.limits['message']:
                    msg_box = QMessageBox(self)
                    msg_box.setWindowTitle('BookFusion Sync')
                    msg_box.addButton(QMessageBox.No)
                    msg_box.addButton(QMessageBox.Yes)
                    msg_box.setText(self.limits['message'])
                    msg_box.setDefaultButton(QMessageBox.Yes)
                    reply = msg_box.exec_()
                    if reply == QMessageBox.Yes:
                        self.start_sync()
                    else:
                        self.in_progress = False
                        self.msg.setText('Canceled.')
                        self.finish_sync()
                else:
                    self.start_sync()
            else:
                self.start_sync()
        else:
            self.in_progress = False
            self.msg.setText('No supported books selected.')
            self.finish_sync()

    def start_sync(self):
        self.log_btn.show()
        self.log.setRowCount(0)

        self.worker_thread = QThread(self)

        book_ids = self.valid_book_ids
        if self.limits['total_books']:
            book_ids = book_ids[:self.limits['total_books']]

        self.total = len(book_ids)

        self.worker = UploadWorker(self.db, self.logger, book_ids)
        self.worker.finished.connect(self.finish_sync)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.progress.connect(self.update_progress)
        self.worker.uploadProgress.connect(self.update_upload_progress)
        self.worker.skipped.connect(self.log_skip)
        self.worker.failed.connect(self.log_fail)
        self.worker.uploaded.connect(self.log_upload)
        self.worker.updated.connect(self.log_update)
        self.worker.aborted.connect(self.abort)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.start)
        self.worker_thread.start()

    def finish_sync(self):
        if self.in_progress:
            self.msg.setText('Done.')
        self.cancel_btn.hide()
        self.cancel_btn.setEnabled(True)
        self.progress.hide()
        self.start_btn.show()
        self.config_btn.setEnabled(True)
        self.sync_all_radio.setEnabled(True)
        self.sync_selected_radio.setEnabled(len(self.selected_book_ids) > 0)

    def abort(self, error):
        self.in_progress = False
        self.msg.setText(error)

    def cancel(self):
        self.in_progress = False
        self.msg.setText('Canceled.')
        self.cancel_btn.setEnabled(False)
        self.worker.cancel()

    def update_progress(self, progress):
        if self.in_progress:
            if isinstance(self.worker, UploadWorker):
                msg = 'Synchronizing...'
            else:
                msg = 'Preparing...'
            if progress:
                msg += ' {} of {}'.format(progress + 1, self.total)
            self.msg.setText(msg)

    def update_upload_progress(self, sent, total):
        if sent < total:
            self.progress.setValue(sent)
            self.progress.setMaximum(total)
        else:
            self.progress.setMaximum(0)

    def log_fail(self, book_id, msg):
        title = self.db.get_proxy_metadata(book_id).title

        self.log.insertRow(self.log.rowCount())
        self.log.setItem(self.log.rowCount() - 1, 0, QTableWidgetItem(title))
        self.log.setItem(self.log.rowCount() - 1, 1, QTableWidgetItem(msg))

    def log_skip(self, book_id):
        title = self.db.get_proxy_metadata(book_id).title

        self.log.insertRow(self.log.rowCount())
        self.log.setItem(self.log.rowCount() - 1, 0, QTableWidgetItem(title))
        self.log.setItem(self.log.rowCount() - 1, 1, QTableWidgetItem('skipped'))

    def log_upload(self, book_id):
        title = self.db.get_proxy_metadata(book_id).title

        self.log.insertRow(self.log.rowCount())
        self.log.setItem(self.log.rowCount() - 1, 0, QTableWidgetItem(title))
        self.log.setItem(self.log.rowCount() - 1, 1, QTableWidgetItem('uploaded'))

    def log_update(self, book_id):
        title = self.db.get_proxy_metadata(book_id).title

        self.log.insertRow(self.log.rowCount())
        self.log.setItem(self.log.rowCount() - 1, 0, QTableWidgetItem(title))
        self.log.setItem(self.log.rowCount() - 1, 1, QTableWidgetItem('updated'))

    def toggle_log(self, _):
        self.log.setVisible(not self.log.isVisible())

    def maybe_cancel(self):
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self,
                'BookFusion Sync',
                'Are you sure you want to cancel the currently running process?',
                QMessageBox.No | QMessageBox.Yes,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                self.cancel()
            else:
                return False
        return True
