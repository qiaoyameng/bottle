# -*- coding: utf-8 -*-
""" Tests for host-based routing. All tests call the WSGI interface
    directly with a handcrafted environ, no real server is started. """

import io
import unittest

import bottle
from bottle import Bottle


def wsgi_request(app, path='/', host=None, method='GET', scheme='http',
                 extra=None):
    """ Perform a request against the WSGI interface of an app and return
        a (status_code, headers, body) tuple. """
    environ = {
        'REQUEST_METHOD': method,
        'PATH_INFO': path,
        'SCRIPT_NAME': '',
        'QUERY_STRING': '',
        'wsgi.url_scheme': scheme,
        'wsgi.errors': io.StringIO(),
        'wsgi.input': io.BytesIO(b''),
        'wsgi.version': (1, 0),
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': False,
        'SERVER_NAME': 'localhost',
        'SERVER_PORT': '443' if scheme == 'https' else '80',
        'SERVER_PROTOCOL': 'HTTP/1.1',
    }
    if host is not None:
        environ['HTTP_HOST'] = host
    if extra:
        environ.update(extra)
    result = {}

    def start_response(status, headers, exc_info=None):
        result['status'] = int(status.split()[0])
        result['headers'] = dict(headers)

    body = b''.join(app.wsgi(environ, start_response))
    if isinstance(body, bytes):
        body = body.decode('utf8')
    else:
        body = b''.join(body).decode('utf8')
    return result['status'], result['headers'], body


class TestHostRouting(unittest.TestCase):

    def setUp(self):
        self.app = Bottle()

    def request(self, *args, **kwargs):
        return wsgi_request(self.app, *args, **kwargs)

    def test_same_path_two_tenants(self):
        @self.app.route('/reports/<id>', host='<tenant>.example.com')
        def report(tenant, id):
            return 'tenant=%s id=%s' % (tenant, id)

        status, _, body = self.request('/reports/1', host='a.example.com')
        self.assertEqual((200, 'tenant=a id=1'), (status, body))
        status, _, body = self.request('/reports/2', host='b.example.com')
        self.assertEqual((200, 'tenant=b id=2'), (status, body))
        # Unknown host does not match
        status, _, _ = self.request('/reports/1', host='other.org')
        self.assertEqual(404, status)

    def test_host_wildcard_filters(self):
        @self.app.route('/x', host='<tenant:re:[a-z]+>.example.com')
        def report(tenant):
            return tenant

        self.assertEqual(200, self.request('/x', host='abc.example.com')[0])
        self.assertEqual(404, self.request('/x', host='a1c.example.com')[0])
        # Default host wildcards match a single label only
        self.assertEqual(404, self.request('/x', host='a.b.example.com')[0])

    def test_static_host_beats_dynamic_host(self):
        # Registration order must not matter: static hosts win.
        @self.app.route('/x', host='<tenant>.example.com')
        def dynamic(tenant):
            return 'dynamic'

        @self.app.route('/x', host='api.example.com')
        def static():
            return 'static'

        self.assertEqual('static', self.request('/x', host='api.example.com')[2])
        self.assertEqual('dynamic', self.request('/x', host='a.example.com')[2])

    def test_dynamic_host_beats_hostless(self):
        @self.app.route('/x')
        def hostless():
            return 'hostless'

        @self.app.route('/x', host='<tenant>.example.com')
        def dynamic(tenant):
            return 'dynamic'

        self.assertEqual('dynamic', self.request('/x', host='a.example.com')[2])
        self.assertEqual('hostless', self.request('/x', host='other.org')[2])
        self.assertEqual('hostless', self.request('/x')[2])

    def test_static_host_beats_hostless(self):
        @self.app.route('/x')
        def hostless():
            return 'hostless'

        @self.app.route('/x', host='api.example.com')
        def static():
            return 'static'

        self.assertEqual('static', self.request('/x', host='api.example.com')[2])
        self.assertEqual('hostless', self.request('/x', host='www.example.com')[2])

    def test_host_case_insensitive(self):
        @self.app.route('/x', host='api.example.com')
        def route():
            return 'ok'

        self.assertEqual(200, self.request('/x', host='API.Example.COM')[0])
        self.assertEqual(200, self.request('/x', host='api.example.com.')[0])

    def test_internationalized_domain_names(self):
        @self.app.route('/x', host='münchen.example.com')
        def route():
            return 'ok'

        # Rule in unicode, request in punycode and vice versa.
        self.assertEqual(200, self.request('/x', host='xn--mnchen-3ya.example.com')[0])
        self.assertEqual(200, self.request('/x', host='München.EXAMPLE.com')[0])

        app2 = Bottle()

        @app2.route('/x', host='xn--mnchen-3ya.example.com')
        def route2():
            return 'ok'

        self.assertEqual(200, wsgi_request(app2, '/x', host='münchen.example.com')[0])

    def test_idn_wildcard_value_is_unicode(self):
        @self.app.route('/x', host='<tenant>.example.com')
        def route(tenant):
            return tenant

        self.assertEqual('münchen',
                         self.request('/x', host='xn--mnchen-3ya.example.com')[2])

    def test_port_handling(self):
        @self.app.route('/x', host='example.com:8080')
        def route_port():
            return 'port'

        @self.app.route('/x', host='example.com')
        def route_any():
            return 'any'

        # Exact port rules win over port-less rules.
        self.assertEqual('port', self.request('/x', host='example.com:8080')[2])
        # Rules without a port match any port.
        self.assertEqual('any', self.request('/x', host='example.com:9090')[2])
        self.assertEqual('any', self.request('/x', host='example.com')[2])

    def test_default_port_is_normalized(self):
        # The default port does not change the request host: Both requests
        # match the same rule.
        @self.app.route('/x', host='example.com')
        def route():
            return 'ok'

        self.assertEqual(200, self.request('/x', host='example.com')[0])
        self.assertEqual(200, self.request('/x', host='example.com:80')[0])

        # A rule with an explicit default port also matches requests
        # without a port.
        app2 = Bottle()

        @app2.route('/x', host='example.com:80')
        def route2():
            return 'ok'

        self.assertEqual(200, wsgi_request(app2, '/x', host='example.com')[0])
        self.assertEqual(200, wsgi_request(app2, '/x', host='example.com:80')[0])
        self.assertEqual(404, wsgi_request(app2, '/x', host='example.com:8080')[0])

    def test_default_port_https(self):
        @self.app.route('/x', host='example.com:443')
        def route():
            return 'ok'

        self.assertEqual(200, self.request('/x', host='example.com', scheme='https')[0])
        self.assertEqual(404, self.request('/x', host='example.com')[0])

    def test_ipv6_literal(self):
        @self.app.route('/x', host='[::1]')
        def route():
            return 'ok'

        self.assertEqual(200, self.request('/x', host='[::1]')[0])
        # IPv6 addresses are canonicalized.
        self.assertEqual(200, self.request('/x', host='[0:0:0:0:0:0:0:1]')[0])
        self.assertEqual(200, self.request('/x', host='[::1]:80')[0])
        self.assertEqual(404, self.request('/x', host='[::2]')[0])

    def test_ipv6_literal_with_port(self):
        @self.app.route('/x', host='[::1]:8080')
        def route():
            return 'ok'

        self.assertEqual(200, self.request('/x', host='[::1]:8080')[0])
        self.assertEqual(404, self.request('/x', host='[::1]')[0])
        self.assertEqual(404, self.request('/x', host='[::1]:80')[0])

    def test_invalid_host_header(self):
        @self.app.route('/x', host='example.com')
        def route():
            return 'ok'

        for bad_host in ('exam ple.com', 'example.com:abc', 'example..com',
                         'example.com:99999', '[::1', '/etc/passwd',
                         'example.com@evil.org'):
            status, _, _ = self.request('/x', host=bad_host)
            self.assertEqual(400, status, 'Host %r should be rejected' % bad_host)

    def test_invalid_host_ignored_without_host_rules(self):
        # Applications without host rules are not affected by host
        # parsing or validation.
        @self.app.route('/x')
        def route():
            return 'ok'

        self.assertEqual(200, self.request('/x', host='exam ple.com')[0])
        self.assertEqual(200, self.request('/x', host='example.com:abc')[0])

    def test_forwarded_host_untrusted_by_default(self):
        @self.app.route('/x', host='internal.example.com')
        def route():
            return 'ok'

        env = {'HTTP_X_FORWARDED_HOST': 'internal.example.com'}
        self.assertEqual(404, self.request('/x', host='public.org', extra=env)[0])

    def test_forwarded_host_trusted(self):
        @self.app.route('/x', host='internal.example.com')
        def route():
            return 'ok'

        self.app.config['router.trust_forwarded_host'] = True
        env = {'HTTP_X_FORWARDED_HOST': 'internal.example.com'}
        self.assertEqual(200, self.request('/x', host='public.org', extra=env)[0])
        # The first entry of a multi-value header wins.
        env = {'HTTP_X_FORWARDED_HOST': 'internal.example.com, proxy.local'}
        self.assertEqual(200, self.request('/x', host='public.org', extra=env)[0])

    def test_host_path_name_collision_rejected(self):
        def callback(tenant, id):
            return ''

        self.assertRaises(bottle.RouteSyntaxError, self.app.route,
                          '/reports/<id>', callback=callback,
                          host='<id>.example.com')

    def test_invalid_host_rule_rejected(self):
        self.assertRaises(bottle.RouteSyntaxError, self.app.route,
                          '/x', callback=lambda: '', host='exam ple.com')
        self.assertRaises(bottle.RouteSyntaxError, self.app.route,
                          '/x', callback=lambda: '', host='example.com:abc')
        self.assertRaises(bottle.RouteSyntaxError, self.app.route,
                          '/x', callback=lambda: '', host='')
        self.assertRaises(bottle.RouteSyntaxError, self.app.route,
                          '/x', callback=lambda: '', host='[not-an-ip]')

    def test_405_includes_host_routes(self):
        @self.app.route('/x', method='GET', host='api.example.com')
        def route():
            return 'ok'

        status, headers, _ = self.request('/x', host='api.example.com',
                                          method='POST')
        self.assertEqual(405, status)
        self.assertEqual('GET', headers.get('Allow'))

    def test_mount_app_keeps_host_rules(self):
        child = Bottle()

        @child.route('/reports/<id>', host='<tenant>.example.com')
        def report(tenant, id):
            return '%s:%s' % (tenant, id)

        self.app.mount('/api/', child)
        status, _, body = self.request('/api/reports/1', host='a.example.com')
        self.assertEqual((200, 'a:1'), (status, body))
        self.assertEqual(404, self.request('/api/reports/1', host='other.org')[0])

    def test_mount_wsgi_with_host(self):
        def wsgi_app(environ, start_response):
            start_response('200 OK', [('Content-Type', 'text/plain')])
            return [b'wsgi']

        self.app.mount('/sub/', wsgi_app, host='wsgi.example.com')
        self.assertEqual(200, self.request('/sub/x', host='wsgi.example.com')[0])
        self.assertEqual(404, self.request('/sub/x', host='other.org')[0])


class TestHostUrlBuilding(unittest.TestCase):

    def setUp(self):
        self.app = Bottle()

    def test_build_with_host_wildcard(self):
        @self.app.route('/reports/<id>', host='<tenant>.example.com',
                        name='report')
        def report(tenant, id):
            return ''

        url = self.app.get_url('report', tenant='a', id=5)
        self.assertEqual('//a.example.com/reports/5', url)

    def test_build_static_host(self):
        @self.app.route('/x', host='api.example.com', name='api')
        def route():
            return ''

        self.assertEqual('//api.example.com/x', self.app.get_url('api'))

    def test_build_host_with_port(self):
        @self.app.route('/x', host='example.com:8080', name='x')
        def route():
            return ''

        self.assertEqual('//example.com:8080/x', self.app.get_url('x'))

    def test_build_escapes_host_labels_not_path(self):
        @self.app.route('/files/<name>', host='<tenant>.example.com',
                        name='files')
        def files(tenant, name):
            return ''

        # Host values are IDNA/punycode encoded, path values are not.
        url = self.app.get_url('files', tenant='münchen', name='瓶')
        self.assertEqual('//xn--mnchen-3ya.example.com/files/瓶', url)

    def test_build_rejects_invalid_host_values(self):
        @self.app.route('/x', host='<tenant>.example.com', name='x')
        def route(tenant):
            return ''

        self.assertRaises(bottle.RouteBuildError, self.app.get_url,
                          'x', tenant='foo/bar')
        self.assertRaises(bottle.RouteBuildError, self.app.get_url,
                          'x', tenant='foo:80')
        self.assertRaises(bottle.RouteBuildError, self.app.get_url,
                          'x', tenant='')

    def test_build_missing_host_argument(self):
        @self.app.route('/x', host='<tenant>.example.com', name='x')
        def route(tenant):
            return ''

        self.assertRaises(bottle.RouteBuildError, self.app.get_url, 'x')

    def test_build_query_string(self):
        @self.app.route('/x', host='a.example.com', name='x')
        def route():
            return ''

        self.assertEqual('//a.example.com/x?q=1',
                         self.app.get_url('x', q=1))

    def test_router_build_by_rule_tuple(self):
        router = bottle.Router()
        router.add('/x', 'GET', 'target', host='a.example.com')
        self.assertEqual('//a.example.com/x',
                         router.build(('a.example.com', '/x')))


if __name__ == '__main__':
    unittest.main()
