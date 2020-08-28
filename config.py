__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from PyQt5.Qt import QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QCheckBox, QComboBox
from calibre.utils.config import JSONConfig

import sys
if sys.version_info[0] >= 3:
    unicode = str

prefs = JSONConfig('plugins/bookfusion')

prefs.defaults['api_key'] = ''
prefs.defaults['api_base'] = 'https://www.bookfusion.com/calibre-api/v1'
prefs.defaults['debug'] = True
prefs.defaults['update_metadata'] = False
prefs.defaults['threads'] = 2


class ConfigWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.l = QVBoxLayout()
        self.l.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.l)

        self.help_msg = QLabel('''
            <h2 style="text-align: center">Get Started</h2>
            <p>
                To start syncing your library you will need to create an account to retrieve<br>
                your API key.
            </p>
        ''')
        self.l.addWidget(self.help_msg)

        self.form = QFormLayout()
        self.form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.l.addLayout(self.form)

        self.link = QLabel('<a href="{0}">{0}</a>'.format(prefs['api_base'] + '/api-key'))
        self.link.setOpenExternalLinks(True)
        self.form.addRow('Visit:', self.link)

        self.api_key = QLineEdit(self)
        self.api_key.setText(prefs['api_key'])
        self.form.addRow('API Key:', self.api_key)

        self.debug = QCheckBox(self)
        self.debug.setChecked(prefs['debug'])
        self.form.addRow('Debug Logging:', self.debug)

        self.update_metadata_layout = QHBoxLayout()
        self.update_metadata_layout.setContentsMargins(0, 0, 0, 0)

        self.update_metadata = QCheckBox(self)
        self.update_metadata.setChecked(prefs['update_metadata'])
        self.update_metadata_layout.addWidget(self.update_metadata)

        self.update_metadata_hint = QLabel('(sync all metadata changes made)')
        self.update_metadata_layout.addWidget(self.update_metadata_hint)

        self.form.addRow('Update Metadata:', self.update_metadata_layout)

        self.threads = QComboBox(self)
        for n in range(3):
            self.threads.addItem(str(pow(2, n)))
        self.threads.setCurrentText(str(prefs['threads']))
        self.form.addRow('Sync Threads:', self.threads)

    def save_settings(self):
        prefs['api_key'] = unicode(self.api_key.text())
        prefs['debug'] = self.debug.isChecked()
        prefs['update_metadata'] = self.update_metadata.isChecked()
        prefs['threads'] = int(self.threads.currentText())
