__copyright__ = '2020, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'


class BookFormat:
    SUPPORTED_FMTS = [
        'AZW', 'AZW3', 'AZW4', 'CBZ', 'CBR', 'CBC', 'CHM', 'DJVU', 'DOCX', 'EPUB', 'FB2', 'FBZ', 'HTML', 'HTMLZ',
        'LIT', 'LRF', 'MOBI', 'ODT', 'PDF', 'PRC', 'PDB', 'PML', 'RB', 'RTF', 'SNB', 'TCR', 'TXT', 'TXTZ'
    ]
    PREFERRED_FMTS = ['EPUB', 'MOBI']

    def __init__(self, db, book_id):
        self.file_path = None
        self.fmt = None

        fmts = db.formats(book_id)
        if len(fmts) > 0:
            fmt = fmts[0]
            for preferred_fmt in self.PREFERRED_FMTS:
                if preferred_fmt in fmts:
                    fmt = preferred_fmt
                    break

            if fmt in self.SUPPORTED_FMTS:
                self.fmt = fmt
                self.file_path = db.format_abspath(book_id, fmt)
