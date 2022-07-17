__copyright__ = '2018, BookFusion <legal@bookfusion.com>'
__license__ = 'GPL v3'

import urllib.request
import urllib.parse
import io
import uuid
from os import path

from calibre_plugins.bookfusion.config import prefs
from calibre_plugins.bookfusion import BookFusionPlugin

def build_opener():
    auth_handler = urllib.request.HTTPBasicAuthHandler()
    auth_handler.add_password(realm='BookFusion Calibre API', uri=prefs['api_base'], user=prefs['api_key'], passwd='')
    opener = urllib.request.build_opener(auth_handler)

    return opener

def build_request(path, params={}, data=None, headers={}, method=None):
    query = urllib.parse.urlencode(params)

    url = "%s%s?%s" % (prefs['api_base'], path, query)
    req = urllib.request.Request(url, data, headers, method=method)
    req.add_header(
        'User-Agent',
        'BookFusion Calibre Plugin {0}'.format(
            str('.'.join(str(x) for x in BookFusionPlugin.version))
        )
    )

    return req

def build_multipart_body(params):
    output = io.BytesIO()
    crlf = b'\r\n'
    read_chunk_size = 8 * 1024 * 1024
    boundary = b'--%s' % str(uuid.uuid4()).encode()

    for param in params:
        output.write(b'--%s' % boundary)
        output.write(crlf)
        if 'value' in param:
            output.write(b'Content-Disposition: form-data; name="%s"' % param['name'].encode())
            output.write(crlf)
            output.write(crlf)
            output.write(param['value'].encode())
        elif 'file' in param:
            filename = path.basename(param['file'])
            output.write(b'Content-Disposition: form-data; name="%s"; filename="%s"' % (param['name'].encode(), filename.encode()))
            output.write(crlf)
            output.write(b'Content-Type: application/octet-stream')
            output.write(crlf)
            output.write(crlf)
            with open(param['file'], 'rb') as f:
                buf = f.read(read_chunk_size)
                while buf:
                    output.write(buf)
                    buf = f.read(read_chunk_size)

        output.write(crlf)

    output.write(b'--%s--' % boundary)
    output.write(crlf)

    content_type = 'multipart/form-data; boundary=%s' % boundary.decode()

    return (output.getvalue(), content_type)
