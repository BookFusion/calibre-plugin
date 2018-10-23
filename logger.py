from __future__ import print_function

__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from datetime import datetime

from calibre_plugins.bookfusion.config import prefs


class Logger:
    def __init__(self, path):
        self.path = path

    def info(self, msg):
        if prefs['debug']:
            line = '%s %s\n' % (datetime.now(), msg)
            print(line, end='')
            with open(self.path, 'a') as f:
                f.write(line)
