__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from calibre.customize import InterfaceActionBase


class BookFusionPlugin(InterfaceActionBase):
    name = 'BookFusion Plugin'
    description = 'Provides synchronization of your eBooks and metadata from Calibre to your devices via the BookFusion iOS, Android & Web reader.'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'BookFusion'
    version = (0, 6, 0)
    minimum_calibre_version = (3, 16, 0)

    actual_plugin = 'calibre_plugins.bookfusion.ui:InterfacePlugin'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.bookfusion.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()

        ac = self.actual_plugin_
        if ac is not None:
            ac.apply_settings()
