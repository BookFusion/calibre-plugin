__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from PyQt5.Qt import QDialog, QLayout, QVBoxLayout

from calibre_plugins.bookfusion.sync import SyncWidget
from calibre_plugins.bookfusion.intro import IntroWidget


class MainDialog(QDialog):
    def __init__(self, gui, do_user_config, selected_book_ids, is_sync_selected):
        QDialog.__init__(self, gui)

        self.gui = gui

        self.setWindowTitle('BookFusion Sync')

        self.l = QVBoxLayout()
        self.l.setSizeConstraint(QLayout.SetFixedSize)
        self.setLayout(self.l)

        self.intro = IntroWidget(gui)
        self.l.addWidget(self.intro)

        self.sync = SyncWidget(gui, do_user_config, selected_book_ids, is_sync_selected)
        self.l.addWidget(self.sync)

        self.adjustSize()

    def reject(self):
        if self.sync.maybe_cancel():
            QDialog.reject(self)
