__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from PyQt5.Qt import QNetworkRequest, QUrl, QUrlQuery

from calibre_plugins.bookfusion.config import prefs
from calibre_plugins.bookfusion import BookFusionPlugin


def build_request(path, params={}):
    url = QUrl(prefs['api_base'] + path)

    query = QUrlQuery()
    for key in params:
        query.addQueryItem(key, params[key])
    url.setQuery(query)

    req = QNetworkRequest(url)
    req.setRawHeader(
        'User-Agent',
        'BookFusion Calibre Plugin {0}'.format(
            '.'.join(str(x) for x in BookFusionPlugin.version)
        )
    )
    return req
