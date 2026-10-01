# -*- coding: utf-8 -*-
import os
from unittest import mock

import bottle

from test.tools import ServerTestBase


BOUNDARY = b'b'


def field(name, value):
    return (
        b'--b\r\n'
        + ('Content-Disposition: form-data; name="%s"\r\n\r\n' % name).encode()
        + value + b'\r\n'
    )


def upload(name, filename, value):
    return (
        b'--b\r\n'
        + ('Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
           % (name, filename)).encode()
        + b'Content-Type: application/octet-stream\r\n\r\n'
        + value + b'\r\n'
    )


def multipart(*parts):
    return b''.join(parts) + b'--b--\r\n'


def encode_chunked(body, size=13):
    encoded = b''
    for offset in range(0, len(body), size):
        chunk = body[offset:offset + size]
        encoded += ('%x\r\n' % len(chunk)).encode() + chunk + b'\r\n'
    return encoded + b'0\r\n\r\n'


def environ(body, chunked=False, content_length=True):
    env = {
        'REQUEST_METHOD': 'POST',
        'CONTENT_TYPE': 'multipart/form-data; boundary=b',
        'wsgi.input': bottle.BytesIO(body),
    }
    if content_length:
        env['CONTENT_LENGTH'] = str(len(body))
    if chunked:
        env['HTTP_TRANSFER_ENCODING'] = 'chunked'
        env['wsgi.input'] = bottle.BytesIO(encode_chunked(body))
        env.pop('CONTENT_LENGTH', None)
    return env


class TrackedTempFiles:
    def __init__(self):
        self.created = []
        self.original = bottle.NamedTemporaryFile

    def __call__(self, *args, **kwargs):
        temp = self.original(*args, **kwargs)
        self.created.append(temp)
        return temp

    def assert_all_closed(self, test):
        for temp in self.created:
            test.assertTrue(temp.closed)
            test.assertFalse(os.path.exists(temp.name))


class UploadPolicyTest(ServerTestBase):
    def setUp(self):
        super().setUp()
        self.body = multipart(
            field('note', b'one'),
            field('note', b'two'),
            upload('avatar', 'a.txt', b'0123456789'),
        )
        self.policy = bottle.UploadPolicy(
            max_request_bytes=len(self.body),
            max_files=1,
            max_file_bytes=10,
            max_field_counts={'note': 2, 'avatar': 1},
            allowed_fields=('note', 'avatar'),
        )

        @self.app.post('/upload', upload_policy=self.policy)
        def upload_route():
            notes = bottle.request.forms.getall('note')
            files = bottle.request.files.getall('avatar')
            self.assertEqual(['one', 'two'], notes)
            self.assertEqual(1, len(files))
            self.assertEqual(b'0123456789', files[0].file.read())
            return b'ok'

        @self.app.post('/limited', upload_policy=self.policy)
        def limited_route():
            return repr((
                len(bottle.request.forms.getall('note')),
                len(bottle.request.files.getall('avatar')),
            ))

    def request(self, body=None, chunked=False, content_length=True):
        return self.urlopen('/upload', method='POST',
                            env=environ(body or self.body, chunked,
                                        content_length))

    def request_limited(self, body):
        return self.urlopen('/limited', method='POST', env=environ(body))

    def test_exact_limits_pass_for_content_length_and_chunked(self):
        with mock.patch.object(bottle.BaseRequest, 'MEMFILE_MAX', 8):
            self.assertEqual(200, self.request()['code'])
            self.assertEqual(200, self.request(chunked=True)['code'])

    def test_missing_content_length_cannot_bypass_request_budget(self):
        with mock.patch.object(bottle.BaseRequest, 'MEMFILE_MAX', 8):
            self.assertEqual(200, self.request(content_length=False)['code'])
            oversized = self.body + b' '
            result = self.urlopen('/upload', method='POST',
                                  env=environ(oversized, content_length=False))
            self.assertEqual(413, result['code'])
            self.assertEqual('request_bytes',
                             result['header']['X-Upload-Error'])

    def test_overstated_content_length_is_rejected(self):
        env = environ(self.body)
        env['CONTENT_LENGTH'] = str(len(self.body) + 5)
        self.assertEqual(413, self.urlopen('/upload', method='POST',
                                          env=env)['code'])

    def test_understated_content_length_cannot_raise_budget(self):
        env = environ(self.body + b' ignored')
        env['CONTENT_LENGTH'] = str(len(self.body))
        result = self.urlopen('/upload', method='POST', env=env)
        self.assertNotEqual(413, result['code'])

    def test_limits_are_distinguishable_and_tempfiles_are_cleaned(self):
        tracked = TrackedTempFiles()
        oversized_file = b'x' * 9 + b'\r\n' + b'yy'
        field_count_body = multipart(
            field('item', b'a'),
            field('item', b'b'),
        )
        cases = (
            ('file_bytes',
             multipart(upload('avatar', 'a.txt', oversized_file)), 413),
            ('file_count', multipart(
                upload('avatar', 'a.txt', b'abc'),
                upload('avatar', 'b.txt', b'def'),
            ), 413),
        )

        with mock.patch.object(bottle.BaseRequest, 'MEMFILE_MAX', 8), \
                mock.patch.object(bottle, 'NamedTemporaryFile', tracked):
            for reason, body, status in cases:
                tracked.created.clear()
                result = self.request_limited(body)
                self.assertEqual(status, result['code'], reason)
                self.assertEqual(reason, result['header']['X-Upload-Error'])
                if reason == 'file_bytes':
                    self.assertGreaterEqual(len(tracked.created), 2)
                self.assertGreater(len(tracked.created), 0)
                tracked.assert_all_closed(self)

        field_route = bottle.Route(
            self.app, '/field-count', 'POST',
            lambda: repr(bottle.request.forms.getall('item')),
            upload_policy={'max_request_bytes': len(field_count_body),
                           'max_field_counts': {'item': 1},
                           'reject_unknown_fields': False})
        self.app.add_route(field_route)
        result = self.urlopen('/field-count', method='POST',
                              env=environ(field_count_body))
        self.assertEqual(400, result['code'])
        self.assertEqual('field_count', result['header']['X-Upload-Error'])

    def test_unknown_fields_can_be_rejected_or_counted(self):
        body = multipart(field('unexpected', b'x'))

        route = bottle.Route(
            self.app, '/strict', 'POST',
            lambda: repr(dict(bottle.request.forms)),
            upload_policy={'allowed_fields': ['avatar'],
                           'unknown_fields': 'reject'})
        self.app.add_route(route)
        result = self.urlopen('/strict', method='POST', env=environ(body))
        self.assertEqual(400, result['code'])
        self.assertEqual('unknown_field', result['header']['X-Upload-Error'])

        allowed_route = bottle.Route(
            self.app, '/allowed', 'POST',
            lambda: repr(dict(bottle.request.forms)),
            upload_policy={'max_request_bytes': len(body),
                           'reject_unknown_fields': False})
        self.app.add_route(allowed_route)
        self.assertEqual(200, self.urlopen('/allowed', method='POST',
                                           env=environ(body))['code'])

        small_route = bottle.Route(
            self.app, '/small', 'POST',
            lambda: repr(dict(bottle.request.forms)),
            upload_policy={'max_request_bytes': len(body) - 1,
                           'reject_unknown_fields': False})
        self.app.add_route(small_route)
        result = self.urlopen('/small', method='POST', env=environ(body))
        self.assertEqual(413, result['code'])
        self.assertEqual('request_bytes', result['header']['X-Upload-Error'])

    def test_lazy_files_access_enforces_policy_before_callback_result(self):
        callback_seen = []

        @self.app.post('/lazy-files', upload_policy={
            'max_request_bytes': len(self.body),
            'max_files': 0,
            'max_file_bytes': 10,
            'max_field_counts': {'note': 2, 'avatar': 1},
            'allowed_fields': ('note', 'avatar'),
        })
        def lazy_files():
            callback_seen.append('entered')
            files = bottle.request.files.getall('avatar')
            callback_seen.append(repr(files))
            return b'unreachable'

        result = self.urlopen('/lazy-files', method='POST',
                              env=environ(self.body))
        self.assertEqual(413, result['code'])
        self.assertEqual('file_count', result['header']['X-Upload-Error'])
        self.assertEqual(['entered'], callback_seen)

    def test_urlencoded_request_limit_closes_body_tempfile(self):
        body = b'a=' + b'x' * 20
        tracked = TrackedTempFiles()
        route = bottle.Route(
            self.app, '/form', 'POST',
            lambda: repr(bottle.request.forms.getall('a')),
            upload_policy={'max_request_bytes': 10,
                           'reject_unknown_fields': False})
        self.app.add_route(route)
        env = {
            'REQUEST_METHOD': 'POST',
            'CONTENT_TYPE': 'application/x-www-form-urlencoded',
            'CONTENT_LENGTH': str(len(body)),
            'wsgi.input': bottle.BytesIO(body),
        }
        with mock.patch.object(bottle.BaseRequest, 'MEMFILE_MAX', 8), \
                mock.patch.object(bottle, 'NamedTemporaryFile', tracked):
            result = self.urlopen('/form', method='POST', env=env)
        self.assertEqual(413, result['code'])
        self.assertEqual('request_bytes', result['header']['X-Upload-Error'])
        tracked.assert_all_closed(self)

    def test_routes_without_policy_keep_original_behavior(self):
        @self.app.post('/default')
        def default_route():
            return repr('note' in bottle.request.forms)

        result = self.urlopen('/default', method='POST',
                              env=environ(self.body))
        self.assertEqual(200, result['code'])
        self.assertEqual(b'True', result['body'])
