# -*- coding: utf-8 -*-
import unittest
import bottle


def env(path='/', host=None, method='GET', scheme='http', **extra):
    e = {'PATH_INFO': path, 'REQUEST_METHOD': method,
         'wsgi.url_scheme': scheme, 'SERVER_NAME': 'localhost',
         'SERVER_PORT': '80'}
    if host is not None:
        e['HTTP_HOST'] = host
    e.update(extra)
    return e


class TestHostRouting(unittest.TestCase):

    def setUp(self):
        self.r = bottle.Router()

    def add(self, path, target, host=None, method='GET', name=None):
        self.r.add(path, method, target, host=host, name=name)

    def match(self, **kwargs):
        return self.r.match(env(**kwargs))

    def assertHTTPError(self, code, **kwargs):
        try:
            self.r.match(env(**kwargs))
            self.fail('HTTPError expected')
        except bottle.HTTPError as e:
            self.assertEqual(code, e.status_code)

    def test_same_path_two_tenants(self):
        self.add('/reports/<id>', 'a', host='a.example.com')
        self.add('/reports/<id>', 'b', host='b.example.com')
        self.add('/reports/<id>', 'generic')
        self.assertEqual(('a', {'id': '1'}),
                         self.match(path='/reports/1', host='a.example.com'))
        self.assertEqual(('b', {'id': '1'}),
                         self.match(path='/reports/1', host='b.example.com'))
        self.assertEqual(('generic', {'id': '1'}),
                         self.match(path='/reports/1', host='other.test'))

    def test_host_case_insensitive(self):
        self.add('/x', 'h', host='example.com')
        self.assertEqual('h', self.match(path='/x', host='EXAMPLE.Com')[0])
        self.assertEqual('h', self.match(path='/x', host='example.COM')[0])

    def test_idn_ulabel_equals_alabel(self):
        self.add('/x', 'h', host='bücher.example')
        self.assertEqual('h', self.match(path='/x', host='BÜCHER.example')[0])
        self.assertEqual('h',
                         self.match(path='/x',
                                    host='xn--bcher-kva.example')[0])

    def test_ipv6_literal_normalized(self):
        self.add('/x', 'h', host='[2001:db8::1]')
        self.assertEqual(
            'h', self.match(path='/x', host='[2001:DB8:0:0:0:0:0:1]')[0])
        self.assertEqual('h', self.match(path='/x', host='[2001:db8::1]:80')[0])
        self.assertEqual(
            'h', self.match(path='/x', host='[2001:db8::1]:443',
                            scheme='https')[0])

    def test_default_ports_ignored(self):
        self.add('/x', 'plain', host='h.test')
        self.assertEqual('plain',
                         self.match(path='/x', host='h.test:80')[0])
        self.assertEqual('plain',
                         self.match(path='/x', host='h.test:443',
                                    scheme='https')[0])
        # Explicit non-default port is a different host
        self.assertHTTPError(404, path='/x', host='h.test:8080')

    def test_default_ports_single_rule_no_duplicate(self):
        self.add('/x', 'p80', host='h.test:80')
        self.add('/x', 'plain', host='h.test')
        # Both registration forms collapse into one normalized host key.
        keys = list(self.r.host_static['GET'])
        self.assertEqual(['h.test'], keys)

    def test_nondefault_port_kept(self):
        self.add('/x', 'p', host='h.test:8080')
        self.assertEqual('p', self.match(path='/x', host='h.test:8080')[0])
        self.assertHTTPError(404, path='/x', host='h.test')

    def test_trailing_dot_equivalent(self):
        self.add('/x', 'h', host='example.com')
        self.assertEqual('h', self.match(path='/x', host='example.com.')[0])

    def test_dynamic_host_wildcard(self):
        self.add('/reports/<id>', 't', host='<tenant>.example.com')
        target, args = self.match(path='/reports/9',
                                  host='acme.example.com')
        self.assertEqual('t', target)
        self.assertEqual({'tenant': 'acme', 'id': '9'}, args)

    def test_dynamic_host_default_pattern_does_not_cross_dot(self):
        self.add('/x', 'h', host='<t>.example.com')
        self.assertHTTPError(404, path='/x', host='a.b.example.com')

    def test_dynamic_host_filter(self):
        self.add('/u/<id>', 'n', host='<n:int>.numbers.test')
        target, args = self.match(path='/u/1', host='42.numbers.test')
        self.assertEqual('n', target)
        self.assertEqual({'n': 42, 'id': '1'}, args)

    def test_dynamic_host_idn_literal_label(self):
        self.add('/x', 'h', host='<t>.bücher.example', name='r')
        self.assertEqual('h', self.match(
            path='/x', host='acme.xn--bcher-kva.example')[0])
        self.assertEqual('h', self.match(
            path='/x', host='acme.BÜCHER.example')[0])
        self.assertEqual('//acme.xn--bcher-kva.example/x',
                         self.r.build('r', t='acme'))

    def test_dynamic_host_non_ascii_sharing_label_rejected(self):
        self.assertRaises(bottle.RouteSyntaxError, self.add,
                          '/x', 'h', host='<t>bücher.test')

    def test_dynamic_host_float_filter_bad_value_is_400(self):
        self.add('/x', 'h', host='<n:float>.num.test')
        self.assertHTTPError(400, path='/x', host='1.2.3.num.test')

    def test_host_path_name_clash_rejected(self):
        self.assertRaises(bottle.RouteNameClashError, self.add,
                          '/<id>', 'x', host='<id>.example.com')

    def test_empty_host_rule_rejected(self):
        self.assertRaises(bottle.RouteSyntaxError, self.add,
                          '/x', 'x', host='   ')

    def test_same_pattern_overwrites_in_place_with_warning(self):
        import warnings
        old_debug = bottle.DEBUG
        bottle.DEBUG = True
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                self.add('/<id>', 'first', host='<t>.test')
                self.add('/<id>', 'second', host='<t>.test')
        finally:
            bottle.DEBUG = old_debug
        self.assertEqual(1, len(self.r.host_dyna['GET']))
        self.assertTrue(any('overwrites' in str(w.message) for w in caught))
        self.assertEqual('second',
                         self.match(path='/x', host='a.test')[0])

    def test_priority_static_host_before_dynamic_host_before_unqualified(self):
        self.add('/fixed', 'sh', host='host.test')
        self.add('/fixed', 'dh', host='<t>.test')
        self.add('/fixed', 'global')
        self.assertEqual('sh',
                         self.match(path='/fixed', host='host.test')[0])
        self.assertEqual('dh',
                         self.match(path='/fixed', host='other.test')[0])
        self.assertEqual('global',
                         self.match(path='/fixed', host='unrelated.org')[0])

    def test_static_host_dynamic_path_beats_dynamic_host_static_path(self):
        self.add('/<page>', 'a', host='host.test')
        self.add('/fixed', 'b', host='<t>.test')
        self.assertEqual('a',
                         self.match(path='/fixed', host='host.test')[0])

    def test_priority_does_not_depend_on_registration_order(self):
        for host in ['zeta.test', 'alpha.test', 'mid.test']:
            self.add('/s', host, host=host)
        for host in ['alpha.test', 'mid.test', 'zeta.test']:
            self.assertEqual(host, self.match(path='/s', host=host)[0])

    def test_invalid_host_header_is_400(self):
        self.add('/x', 'h', host='h.test')
        for bad in ['evil .com', 'evil\\.com', 'host name', '[::1',
                    'h.test:abc', 'h.test:99999']:
            self.assertHTTPError(400, path='/x', host=bad)

    def test_forwarded_host_ignored_by_default(self):
        r = bottle.Router(trust_proxy_headers=False)
        r.add('/x', 'GET', 'internal', host='internal.test')
        r.add('/x', 'GET', 'public', host='public.test')
        e = env(path='/x', host='internal.test',
                **{'HTTP_X_FORWARDED_HOST': 'public.test, proxy.test'})
        self.assertEqual('internal', r.match(e)[0])

    def test_forwarded_host_used_when_trusted(self):
        r = bottle.Router(trust_proxy_headers=True)
        r.add('/x', 'GET', 'internal', host='internal.test')
        r.add('/x', 'GET', 'public', host='public.test')
        e = env(path='/x', host='internal.test',
                **{'HTTP_X_FORWARDED_HOST': 'public.test, proxy.test'})
        self.assertEqual('public', r.match(e)[0])

    def test_405_collects_alternatives_across_host_groups(self):
        self.add('/r', 'post', host='a.test', method='POST')
        self.add('/r', 'getany')
        self.assertRaises(bottle.HTTPError, self.r.match,
                          env(path='/r', host='a.test', method='DELETE'))
        try:
            self.r.match(env(path='/r', host='a.test', method='DELETE'))
        except bottle.HTTPError as e:
            self.assertEqual('GET,POST', e.get_header('Allow'))

    def test_build_host_route(self):
        self.add('/reports/<id>', 't', host='<tenant>.example.com',
                 name='rep')
        self.assertEqual('//acme.example.com/reports/42',
                         self.r.build('rep', tenant='acme', id=42))

    def test_build_host_idna(self):
        self.add('/x', 't', host='<h>.example', name='r')
        self.assertEqual('//xn--bcher-kva.example/x',
                         self.r.build('r', h='bücher'))

    def test_build_host_vs_path_escaping(self):
        self.add('/<p>', 't', host='<h>.test', name='r')
        url = self.r.build('r', h='a.b/c d', p='x/y z')
        self.assertEqual('//a.b%2Fc%20d.test/x/y%20z', url)

    def test_build_query_string(self):
        self.add('/reports/<id>', 't', host='<tenant>.example.com',
                 name='rep')
        self.assertEqual('//a.example.com/reports/1?q=v',
                         self.r.build('rep', tenant='a', id=1, q='v'))

    def test_build_path_only_unchanged(self):
        self.add('/hello/<name>', 't', name='hi')
        self.assertEqual('/hello/world', self.r.build('hi', name='world'))

    def test_build_missing_argument(self):
        self.add('/x', 't', host='<h>.test', name='r')
        self.assertRaises(bottle.RouteBuildError, self.r.build, 'r')

    def test_path_only_app_keeps_working_without_host_header(self):
        r = bottle.Router()
        r.add('/x', 'GET', 'h')
        # No HTTP_HOST at all; host-less route still matches.
        e = {'PATH_INFO': '/x', 'REQUEST_METHOD': 'GET'}
        self.assertEqual('h', r.match(e)[0])

    def test_old_path_syntax_still_works_but_not_in_host(self):
        # Colons in an IPv6 host rule must not be treated as old wildcards.
        self.add('/x', 'h', host='[fe80::1]')
        self.assertEqual(
            'h', self.match(path='/x', host='[FE80:0:0:0:0:0:0:1]')[0])


class TestHostRoutingApp(unittest.TestCase):

    def test_route_decorator_accepts_host(self):
        app = bottle.Bottle()

        @app.route('/reports/<id>', host='<tenant>.saas.test', name='report')
        def report(tenant, id):
            return '%s:%s' % (tenant, id)

        @app.route('/reports/<id>', name='fallback')
        def fallback(id):
            return 'generic:%s' % id

        route, args = app.router.match(
            env(path='/reports/7', host='acme.saas.test'))
        self.assertEqual(report, route.callback)
        self.assertEqual({'tenant': 'acme', 'id': '7'}, args)
        route, args = app.router.match(
            env(path='/reports/7', host='other.test'))
        self.assertEqual(fallback, route.callback)
        self.assertEqual({'id': '7'}, args)

    def test_get_url_with_host(self):
        app = bottle.Bottle()

        @app.route('/r/<id>', host='<t>.test', name='r')
        def cb(t, id):
            pass

        bottle.request.bind(env(host='acme.test'))
        self.assertEqual('//acme.test/r/1',
                         app.get_url('r', t='acme', id=1))

    def test_get_url_path_only(self):
        app = bottle.Bottle()

        @app.route('/r/<id>', name='r')
        def cb(id):
            pass

        bottle.request.bind(env(host='acme.test'))
        self.assertEqual('/r/1', app.get_url('r', id=1))

    def test_config_enables_proxy_trust(self):
        app = bottle.Bottle()
        self.assertFalse(app.router.trust_proxy_headers)
        app.config['router.trust_proxy_headers'] = True
        self.assertTrue(app.router.trust_proxy_headers)

    def test_mounted_subapp_with_host_routes(self):
        parent = bottle.Bottle()
        sub = bottle.Bottle()

        @sub.route('/hello/<name>')
        def hello(name):
            return name

        parent.mount('/sub/', sub)
        target, args = parent.router.match(
            env(path='/sub/hello/world', host='anything.test'))
        self.assertEqual({'name': 'world'}, args)
        self.assertTrue(callable(target.get_callback_args))

    def test_mounted_subapp_host_rule_is_kept(self):
        parent = bottle.Bottle()
        sub = bottle.Bottle()

        @sub.route('/x', host='api.test')
        def x():
            pass

        parent.mount('/sub/', sub)
        route, _ = parent.router.match(
            env(path='/sub/x', host='api.test'))
        self.assertEqual(x, route.callback)
        self.assertHTTPErrorApp(parent, 404,
                                path='/sub/x', host='other.test')

    def assertHTTPErrorApp(self, app, code, **kwargs):
        try:
            app.router.match(env(**kwargs))
            self.fail('HTTPError expected')
        except bottle.HTTPError as e:
            self.assertEqual(code, e.status_code)

    def test_wsgi_application_dispatch_by_host(self):
        app = bottle.Bottle()

        @app.route('/x', host='a.test')
        def a():
            return 'a'

        @app.route('/x')
        def g():
            return 'g'

        def call(host):
            captured = {}

            def start_response(status, headers, exc_info=None):
                captured['status'] = status

            result = b''.join(app(env(path='/x', host=host),
                                  start_response))
            return captured['status'], result.decode()

        self.assertEqual(('200 OK', 'a'), call('a.test'))
        self.assertEqual(('200 OK', 'g'), call('b.test'))
        status, body = call('bad host')
        self.assertEqual('400 Bad Request', status)


if __name__ == '__main__':
    unittest.main()
