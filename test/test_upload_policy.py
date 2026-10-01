# -*- coding: utf-8 -*-
""" Tests for per-route :class:`bottle.UploadPolicy` upload limits. """

import unittest
import wsgiref.util
from io import BytesIO

import bottle
from bottle import tob

from .tools import ServerTestBase


BOUNDARY = 'lowerUPPER-boundary-1234'


def encode_multipart(fields=(), files=(), boundary=BOUNDARY):
    """ Build a multipart/form-data body. ``fields`` is a list of
        (name, value) tuples, ``files`` a list of (name, filename, data). """
    lines = []
    for name, value in fields:
        lines.append('--' + boundary)
        lines.append('Content-Disposition: form-data; name="%s"' % name)
        lines.append('')
        lines.append(value)
    for name, filename, data in files:
        lines.append('--' + boundary)
        lines.append('Content-Disposition: form-data; name="%s"; filename="%s"'
                     % (name, filename))
        lines.append('Content-Type: application/octet-stream')
        lines.append('')
        lines.append(data)
    lines.append('--' + boundary + '--')
    lines.append('')
    return tob('\r\n'.join(lines))


def encode_chunked(data, chunk_size=7):
    """ Wrap raw bytes into an HTTP/1.1 chunked transfer-coding. """
    out = b''
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        out += ('%x\r\n' % len(chunk)).encode('ascii') + chunk + b'\r\n'
    out += b'0\r\n\r\n'
    return out


def multipart_environ(body, content_length=None, chunked=False):
    env = {}
    wsgiref.util.setup_testing_defaults(env)
    env['QUERY_STRING'] = ''
    env['REQUEST_METHOD'] = 'POST'
    env['PATH_INFO'] = '/'
    env['CONTENT_TYPE'] = 'multipart/form-data; boundary=' + BOUNDARY
    if chunked:
        env['HTTP_TRANSFER_ENCODING'] = 'chunked'
        env['wsgi.input'] = BytesIO(encode_chunked(tob(body)))
    else:
        env['CONTENT_LENGTH'] = str(
            len(body) if content_length is None else content_length)
        env['wsgi.input'] = BytesIO(tob(body))
    return env


def parse_parts(body, policy=None, **kwargs):
    stream = BytesIO(tob(body))
    parser = bottle._MultipartParser(
        stream, boundary=BOUNDARY, content_length=len(body),
        charset='utf8', policy=policy, **kwargs)
    return list(parser.parse())


class TestUploadPolicyParser(unittest.TestCase):
    """ Limits enforced directly by the multipart parser. """

    def test_exact_limits_pass(self):
        body = encode_multipart(
            fields=[('tag', 'v')],
            files=[('avatar', 'a.png', 'x' * 100)])
        policy = bottle.UploadPolicy(
            max_request_bytes=len(body), max_files=1, max_file_bytes=100,
            field_limits={'avatar': 1, 'tag': 1})
        parts = parse_parts(body, policy)
        try:
            self.assertEqual(['tag', 'avatar'], [p.name for p in parts])
            avatar = parts[1]
            self.assertEqual(avatar.raw, b'x' * 100)
        finally:
            for part in parts:
                part.close()

    def test_file_size_exceeded(self):
        body = encode_multipart(files=[('avatar', 'a.png', 'x' * 101)])
        policy = bottle.UploadPolicy(max_file_bytes=100)
        parts = []
        with self.assertRaises(bottle.FileSizeExceeded) as ctx:
            parts = parse_parts(body, policy)
        self.assertEqual(413, ctx.exception.status_code)
        self.assertEqual('avatar', ctx.exception.field_name)
        for part in parts:
            part.close()

    def test_file_count_exceeded(self):
        body = encode_multipart(
            files=[('a', 'a.bin', '1'), ('b', 'b.bin', '2')])
        policy = bottle.UploadPolicy(max_files=1)
        with self.assertRaises(bottle.FileCountExceeded) as ctx:
            parse_parts(body, policy)
        self.assertEqual(400, ctx.exception.status_code)

    def test_field_count_exceeded(self):
        body = encode_multipart(
            fields=[('tag', 'a'), ('tag', 'b'), ('tag', 'c')])
        policy = bottle.UploadPolicy(field_limits={'tag': 2})
        with self.assertRaises(bottle.FieldCountExceeded) as ctx:
            parse_parts(body, policy)
        self.assertEqual(400, ctx.exception.status_code)
        self.assertEqual('tag', ctx.exception.field_name)

    def test_field_count_includes_files(self):
        body = encode_multipart(
            files=[('asset', 'a', '1'), ('asset', 'b', '2')])
        policy = bottle.UploadPolicy(field_limits={'asset': 1})
        with self.assertRaises(bottle.FieldCountExceeded):
            parse_parts(body, policy)

    def test_unknown_field_accepted_by_default(self):
        body = encode_multipart(fields=[('surprise', 'v')])
        policy = bottle.UploadPolicy(field_limits={'known': 1})
        parts = parse_parts(body, policy)
        try:
            self.assertEqual('surprise', parts[0].name)
        finally:
            parts[0].close()

    def test_unknown_field_rejected(self):
        body = encode_multipart(fields=[('surprise', 'v')])
        policy = bottle.UploadPolicy(
            field_limits={'known': 1}, reject_unknown=True)
        with self.assertRaises(bottle.UnknownFieldError) as ctx:
            parse_parts(body, policy)
        self.assertEqual(400, ctx.exception.status_code)
        self.assertEqual('surprise', ctx.exception.field_name)

    def test_spill_to_disk_then_exceed(self):
        """ A file that crosses the memory->disk spill point and keeps
            growing past the per-file limit is rejected and cleaned up. """
        body = encode_multipart(files=[('big', 'big.bin', 'y' * 200)])
        policy = bottle.UploadPolicy(max_file_bytes=150, memfile_max=64)
        parts = []
        with self.assertRaises(bottle.FileSizeExceeded):
            parts = parse_parts(body, policy, memfile_limit=64)
        self.assertTrue(all(p.file is False or p.file.closed for p in parts))

    def test_spill_to_disk_success_readable(self):
        body = encode_multipart(
            fields=[('tag', 'hello')],
            files=[('big', 'big.bin', 'z' * 300)])
        policy = bottle.UploadPolicy(memfile_max=64)
        parts = parse_parts(body, policy, memfile_limit=64)
        try:
            self.assertFalse(parts[1].is_buffered())
            self.assertEqual(parts[1].raw, b'z' * 300)
            self.assertEqual(parts[0].value, 'hello')
        finally:
            for part in parts:
                part.close()

    def test_no_policy_keeps_defaults(self):
        """ Without a policy, parser defaults apply (no new limits). """
        body = encode_multipart(
            files=[('a', 'a', '1'), ('b', 'b', '2')])
        parts = parse_parts(body)
        try:
            self.assertEqual(2, len(parts))
        finally:
            for part in parts:
                part.close()


class TestUploadPolicyRoute(ServerTestBase):
    """ End-to-end limits through the WSGI stack, including lazy parsing. """

    def install_route(self, policy, record=None, access='files'):
        @bottle.post('/', upload=policy)
        def handler():
            if access == 'files':
                items = [(u.name, len(u.file.read()))
                         for u in bottle.request.files.values()]
            else:
                items = list(bottle.request.forms.allitems())
            if record is not None:
                record['called'] = True
                record['items'] = items
            return 'ok'

    def request_body(self, body, **kwargs):
        return self.urlopen('/', method='POST',
                            env=multipart_environ(body, **kwargs))

    def test_policy_stored_on_route(self):
        policy = bottle.UploadPolicy(max_files=1)
        @bottle.post('/p', upload=policy)
        def handler():
            return 'ok'
        routes = [r for r in self.app.routes if r.rule == '/p']
        self.assertIs(policy, routes[0].config['upload_policy'])

    def test_lazy_access_is_covered(self):
        record = {}
        self.install_route(bottle.UploadPolicy(max_file_bytes=10), record)
        body = encode_multipart(files=[('avatar', 'a.png', 'x' * 11)])
        result = self.request_body(body)
        self.assertEqual(413, result['code'])
        self.assertNotIn('called', record)

    def test_multi_value_order_preserved(self):
        record = {}
        policy = bottle.UploadPolicy(
            field_limits={'tag': 3}, memfile_max=64)
        @bottle.post('/', upload=policy)
        def handler():
            record['called'] = True
            record['tags'] = bottle.request.forms.getall('tag')
            return 'ok'
        body = encode_multipart(fields=[('tag', 'one'), ('tag', 'two'),
                                        ('tag', 'three')])
        result = self.request_body(body)
        self.assertEqual(200, result['code'])
        self.assertEqual(['one', 'two', 'three'], record['tags'])

    def test_disk_spill_content_and_cleanup(self):
        created = []
        original = bottle.NamedTemporaryFile

        def tracking(*args, **kwargs):
            handle = original(*args, **kwargs)
            created.append(handle)
            return handle

        record = {}
        self.install_route(
            bottle.UploadPolicy(max_file_bytes=500, memfile_max=64), record)
        body = encode_multipart(files=[('avatar', 'a.png', 'q' * 600)])
        bottle.NamedTemporaryFile = tracking
        try:
            result = self.request_body(body)
        finally:
            bottle.NamedTemporaryFile = original
        # The 600 byte file spills both the spooled body and the part to disk
        # (memfile_max=64), exceeds the 500 byte per-file limit and every
        # temporary file created along the way must be closed.
        self.assertEqual(413, result['code'])
        self.assertNotIn('called', record)
        self.assertTrue(created)
        self.assertTrue(all(handle.closed for handle in created))

    def test_disk_spill_success_content_readable(self):
        record = {}
        self.install_route(
            bottle.UploadPolicy(max_file_bytes=1000, memfile_max=64), record)
        body = encode_multipart(
            fields=[('tag', 'kept')],
            files=[('avatar', 'a.png', 'w' * 700)])
        result = self.request_body(body)
        self.assertEqual(200, result['code'])
        self.assertEqual([('avatar', 700)], record['items'])

    def test_missing_content_length_still_enforced(self):
        record = {}
        self.install_route(
            bottle.UploadPolicy(max_request_bytes=200), record)
        body = encode_multipart(files=[('avatar', 'a.png', 'x' * 300)])
        result = self.request_body(body, content_length=None)
        self.assertEqual(413, result['code'])
        self.assertNotIn('called', record)

    def test_forged_small_content_length_still_enforced(self):
        record = {}
        self.install_route(
            bottle.UploadPolicy(max_request_bytes=100000), record)
        body = encode_multipart(files=[('avatar', 'a.png', 'x' * 500)])
        result = self.request_body(body, content_length=5)
        self.assertIn(result['code'], (400, 413))
        self.assertNotIn('called', record)

    def test_chunked_transfer_happy_path(self):
        record = {}
        self.install_route(bottle.UploadPolicy(
            max_request_bytes=100000, max_file_bytes=1000), record)
        body = encode_multipart(
            fields=[('tag', 'v')],
            files=[('avatar', 'a.png', 'x' * 50)])
        result = self.request_body(body, chunked=True)
        self.assertEqual(200, result['code'])
        self.assertTrue(record['called'])

    def test_chunked_transfer_exceeds_read_budget(self):
        record = {}
        self.install_route(
            bottle.UploadPolicy(max_request_bytes=100), record)
        body = encode_multipart(files=[('avatar', 'a.png', 'x' * 500)])
        result = self.request_body(body, chunked=True)
        self.assertEqual(413, result['code'])
        self.assertNotIn('called', record)

    def test_chunked_small_chunks_file_limit(self):
        """ Seven-byte HTTP chunks split headers, field data and boundaries,
            yet the per-file limit is still enforced exactly. """
        record = {}
        self.install_route(
            bottle.UploadPolicy(max_file_bytes=20), record)
        body = encode_multipart(files=[('avatar', 'a.png', 'x' * 21)])
        result = self.request_body(body, chunked=True)
        self.assertEqual(413, result['code'])
        self.assertNotIn('called', record)

        body_ok = encode_multipart(files=[('avatar', 'a.png', 'x' * 20)])
        result = self.request_body(body_ok, chunked=True)
        self.assertEqual(200, result['code'])

    def test_exact_request_size_passes(self):
        record = {}
        self.install_route(bottle.UploadPolicy(max_request_bytes=None), record)
        body = encode_multipart(fields=[('tag', 'v')])
        # Same body with a tight, exactly-fitting read budget.
        self.install_route(
            bottle.UploadPolicy(max_request_bytes=len(body)), {})
        result = self.request_body(body)
        self.assertEqual(200, result['code'])

    def test_exact_request_size_passes_chunked(self):
        record = {}
        body = encode_multipart(fields=[('tag', 'v')])
        raw = encode_chunked(body)
        self.install_route(
            bottle.UploadPolicy(max_request_bytes=len(raw)), record)
        result = self.request_body(body, chunked=True)
        self.assertEqual(200, result['code'])
        self.assertTrue(record['called'])

    def test_one_byte_over_request_size_fails(self):
        body = encode_multipart(fields=[('tag', 'v')])
        self.install_route(
            bottle.UploadPolicy(max_request_bytes=len(body) - 1), {})
        result = self.request_body(body)
        self.assertEqual(413, result['code'])

    def test_unknown_field_end_to_end(self):
        record = {}
        self.install_route(bottle.UploadPolicy(
            field_limits={'avatar': 1}, reject_unknown=True), record)
        body = encode_multipart(fields=[('evil', 'v')])
        result = self.request_body(body)
        self.assertEqual(400, result['code'])
        self.assertNotIn('called', record)

    def test_file_count_end_to_end(self):
        record = {}
        self.install_route(bottle.UploadPolicy(max_files=1), record)
        body = encode_multipart(
            files=[('a', 'a.bin', '1'), ('b', 'b.bin', '2')])
        result = self.request_body(body)
        self.assertEqual(400, result['code'])
        self.assertNotIn('called', record)

    def test_routes_without_policy_keep_defaults(self):
        created = []
        original = bottle.NamedTemporaryFile

        def tracking(*args, **kwargs):
            handle = original(*args, **kwargs)
            created.append(handle)
            return handle

        @bottle.post('/default')
        def default_handler():
            # Two files and repeated fields are accepted without a policy.
            tags = bottle.request.forms.getall('tag')
            count = len(bottle.request.files.getall('f'))
            return '%d:%d' % (len(tags), count)

        body = encode_multipart(
            fields=[('tag', '1'), ('tag', '2')],
            files=[('f', 'a', 'a'), ('f', 'b', 'b')])
        bottle.NamedTemporaryFile = tracking
        try:
            result = self.urlopen('/default', method='POST',
                                  env=multipart_environ(body))
        finally:
            bottle.NamedTemporaryFile = original
        self.assertEqual(200, result['code'])
        self.assertEqual(b'2:2', result['body'])


if __name__ == '__main__':
    unittest.main()
