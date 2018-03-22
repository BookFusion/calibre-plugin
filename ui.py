__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from calibre.gui2.actions import InterfaceAction
from calibre_plugins.bookfusion.main import MainDialog


class InterfacePlugin(InterfaceAction):
    name = 'BookFusion Plugin'

    action_spec = ('BookFusion Sync', None,
                   'Sync your books to the BookFusion platform', None)

    def genesis(self):
        icon = get_icons('images/icon.png')
        self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.show_dialog)

    def show_dialog(self):
        base_plugin_object = self.interface_action_base_plugin
        do_user_config = base_plugin_object.do_user_config

        MainDialog(self.gui, self.qaction.icon(), do_user_config).show()

    def apply_settings(self):
        None
