__copyright__ = '2020, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'


class BookFormat:
    SUPPORTED_FMTS = [
        'AZW', 'AZW3', 'AZW4', 'CBZ', 'CBR', 'CBC', 'CHM', 'DJVU', 'DOCX', 'EPUB', 'FB2', 'FBZ', 'HTML', 'HTMLZ',
        'LIT', 'LRF', 'MOBI', 'ODT', 'PDF', 'PRC', 'PDB', 'PML', 'RB', 'RTF', 'SNB', 'TCR', 'TXT', 'TXTZ'
    ]
    PREFERRED_FMTS = ['EPUB', 'MOBI']

    def __init__(self, db, book_id, preferred_fmt=None):
        self.file_path = None
        self.fmt = None

        fmts = db.formats(book_id)
        if len(fmts) > 0:
            fmt = fmts[0]

            preference_list = []
            if preferred_fmt:
                preference_list.append(preferred_fmt)
            for f in self.PREFERRED_FMTS:
                if f not in preference_list:
                    preference_list.append(f)

            for pref in preference_list:
                if pref in fmts:
                    fmt = pref
                    break

            if fmt in self.SUPPORTED_FMTS:
                self.fmt = fmt
                self.file_path = db.format_abspath(book_id, fmt)
