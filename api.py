__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

from PyQt5.Qt import QNetworkRequest, QUrl, QUrlQuery
import base64

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
        u'User-Agent'.encode('utf-8'),
        u'BookFusion Calibre Plugin {0}'.format(
            str('.'.join(str(x) for x in BookFusionPlugin.version))
        ).encode('utf-8')
    )
    req.setRawHeader(
        u'Authorization'.encode('utf-8'),
	u'Basic {}'.format(
            base64.b64encode(u'{}:'.format(prefs['api_key']).encode('utf-8')).decode('ascii')
        ).encode('utf-8')
    )
    return req
