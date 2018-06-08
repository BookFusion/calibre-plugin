__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from PyQt5.Qt import QMenu

from calibre.gui2.actions import InterfaceAction
from calibre_plugins.bookfusion.main import MainDialog


class InterfacePlugin(InterfaceAction):
    name = 'BookFusion Plugin'

    action_spec = ('BookFusion', None,
                   'Sync your books to the BookFusion platform', None)

    def genesis(self):
        self.sync_selected_action = self.create_action(
            spec=('Sync selected books', None, None, None),
            attr='Sync selected books'
        )
        self.sync_selected_action.triggered.connect(self.sync_selected)

        self.sync_all_action = self.create_action(
            spec=('Sync all books', None, None, None),
            attr='Sync all books'
        )
        self.sync_all_action.triggered.connect(self.sync_all)

        self.menu = QMenu(self.gui)
        self.menu.addAction(self.sync_selected_action)
        self.menu.addAction(self.sync_all_action)
        self.menu.aboutToShow.connect(self.update_menu)

        self.qaction.setMenu(self.menu)
        self.qaction.setIcon(get_icons('images/icon.png'))
        self.qaction.triggered.connect(self.sync_selected)

    def sync_all(self):
        self.show_dialog(is_sync_selected=False)

    def sync_selected(self):
        self.show_dialog()

    def show_dialog(self, is_sync_selected=True):
        base_plugin_object = self.interface_action_base_plugin
        do_user_config = base_plugin_object.do_user_config

        rows = self.gui.library_view.selectionModel().selectedRows()
        selected_book_ids = []
        for row in rows:
            selected_book_ids.append(self.gui.library_view.model().db.id(row.row()))

        MainDialog(self.gui, do_user_config, selected_book_ids, is_sync_selected).show()

    def update_menu(self):
        rows = self.gui.library_view.selectionModel().selectedRows()
        self.sync_selected_action.setEnabled(len(rows) > 0)

    def apply_settings(self):
        None
