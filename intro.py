__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from PyQt5.Qt import QWidget, QVBoxLayout, QLabel


class IntroWidget(QWidget):
    def __init__(self, gui):
        QWidget.__init__(self, gui)

        self.l = QVBoxLayout()
        self.l.setContentsMargins(0, 0, 0, 0)
        self.l.addWidget(QLabel('''
            <h2 style="text-align: center">
                Your Own eBooks in the Cloud and on Your Devices<br>
                Anytime, Anywhere &amp; on Any Device
            </h2>
            <p>
                BookFusion is an eBook platform that allows you to manage, upload, read,<br>
                share, organization bookmarks, and sync all your books.
            </p>
            <ul>
                <li>Organize your eBook library</li>
                <li>Sync reading progress, bookmarks, highlights and notes<br>across all devices</li>
                <li>Read both offline and online</li>
                <li>Supports popular eBook formats</li>
                <li>Web and Native Android &amp; iOS apps</li>
                <li>Many more features</li>
            </ul>
            <p></p>
        '''))
        self.setLayout(self.l)
