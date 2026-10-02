# -*- coding: utf-8 -*-
import bottle
from .tools import ServerTestBase, api
from bottle import response

class TestAppMounting(ServerTestBase):
    def setUp(self):
        ServerTestBase.setUp(self)
        self.subapp = bottle.Bottle()

        @self.subapp.route('/')
        @self.subapp.route('/test/<test>')
        def test(test='foo'):
            return test

    def test_mount_unicode_path_bug602(self):
        self.app.mount('/mount/', self.subapp)
        self.assertBody('äöü', '/mount/test/äöü')
        self.app.route('/route/<param>', callback=lambda param: param)
        self.assertBody('äöü', '/route/äöü')

    def test_mount_order_bug581(self):
        self.app.mount('/test/', self.subapp)

        # This should not match
        self.app.route('/<test:path>', callback=lambda test: test)

        self.assertStatus(200, '/test/')
        self.assertBody('foo', '/test/')

    def test_mount(self):
        self.app.mount('/test/', self.subapp)
        self.assertStatus(404, '/')
        self.assertStatus(404, '/test')
        self.assertStatus(200, '/test/')
        self.assertBody('foo', '/test/')
        self.assertStatus(200, '/test/test/bar')
        self.assertBody('bar', '/test/test/bar')

    def test_mount_meta(self):
        self.app.mount('/test/', self.subapp)
        self.assertEqual(
            self.subapp.config['_mount.prefix'], '/test/')
        self.assertEqual(
            self.subapp.config['_mount.app'], self.app)

    @api('0.9', '0.13')
    def test_no_slash_prefix(self):
        self.app.mount('/test', self.subapp)
        self.assertStatus(404, '/')
        self.assertStatus(200, '/test')
        self.assertBody('foo', '/test')
        self.assertStatus(200, '/test/')
        self.assertBody('foo', '/test/')
        self.assertStatus(200, '/test/test/bar')
        self.assertBody('bar', '/test/test/bar')

    def test_mount_no_plugins(self):
        def plugin(func):
            def wrapper(*a, **ka):
                return 'Plugin'
            return wrapper
        self.app.install(plugin)
        self.app.route('/foo', callback=lambda: 'baz')
        self.app.mount('/test/', self.subapp)
        self.assertBody('Plugin', '/foo')
        self.assertBody('foo', '/test/')

    def test_mount_wsgi(self):
        status = {}
        def app(environ, start_response):
            start_response('200 OK', [('X-Test', 'WSGI')])
            return 'WSGI ' + environ['PATH_INFO']
        self.app.mount('/test', app)
        self.assertStatus(200, '/test/')
        self.assertBody('WSGI /', '/test')
        self.assertBody('WSGI /', '/test/')
        self.assertHeader('X-Test', 'WSGI', '/test/')
        self.assertBody('WSGI /test/bar', '/test/test/bar')
            
    def test_mount_cookie(self):
        @self.subapp.route('/cookie')
        def test_cookie():
            response.set_cookie('a', 'a')
            response.set_cookie('b', 'b')
        self.app.mount('/test/', self.subapp)
        c = self.urlopen('/test/cookie')['header']['Set-Cookie']
        self.assertEqual(['a=a', 'b=b'], list(sorted(c.split(', '))))

    def test_mount_wsgi_ctype_bug(self):
        status = {}
        def app(environ, start_response):
            start_response('200 OK', [('Content-Type', 'test/test')])
            return 'WSGI ' + environ['PATH_INFO']
        self.app.mount('/test', app)
        self.assertHeader('Content-Type', 'test/test', '/test/')

    def test_mount_json_bug(self):
        @self.subapp.route('/json')
        def route():
            return {'a': 5}
        self.app.mount('/test/', self.subapp)
        self.assertHeader('Content-Type', 'application/json', '/test/json')

    def test_mount_get_url(self):
        @self.subapp.route('/test', name="test")
        def route():
            return bottle.url("test")

        self.app.mount('/test/', self.subapp)
        self.assertBody('/test/test', '/test/test')


class TestAppMerging(ServerTestBase):
    def setUp(self):
        ServerTestBase.setUp(self)
        self.subapp = bottle.Bottle()
        @self.subapp.route('/')
        @self.subapp.route('/test/<test>')
        def test(test='foo'):
            return test

    def test_merge(self):
        self.app.merge(self.subapp)
        self.assertStatus(200, '/')
        self.assertBody('foo', '/')
        self.assertStatus(200, '/test/bar')
        self.assertBody('bar', '/test/bar')


class TestMountRouteRemoval(ServerTestBase):
    def test_mounted_wsgi_app_registrations_can_be_removed(self):
        def wsgi_app(environ, start_response):
            start_response('200 OK', [])
            return [b'mounted']

        handles = self.app.mount('/raw', wsgi_app)

        self.assertEqual(2, len(handles))
        self.assertBody('mounted', '/raw')
        self.assertBody('mounted', '/raw/item')

        for handle in handles:
            self.assertTrue(self.app.remove_route(handle))

        self.assertStatus(404, '/raw')
        self.assertStatus(404, '/raw/item')

    def test_mounted_filtered_route_can_be_removed_and_registered_again(self):
        def pair_filter(config):
            return r'(\w+)-(\w+)', None, None

        self.app.router.add_filter('pair', pair_filter)
        child = bottle.Bottle()
        child.router.add_filter('pair', pair_filter)

        @child.route('/items/<item:pair>')
        def item(item):
            return item

        handles = self.app.mount('/api/', child)
        self.assertEqual(1, len(handles))
        self.assertBody('one-two', '/api/items/one-two')

        self.assertTrue(self.app.remove_route(handles[0]))
        self.assertStatus(404, '/api/items/one-two')
        self.assertFalse(self.app.remove_route(handles[0]))
        self.assertNotIn(child, self.app._mounts)
        self.assertNotIn('_mount.app', child.config)
        self.assertEqual('/items/<item:pair>', child.routes[0].rule)

        handle = self.app.route('/api/items/<item:pair>',
                                callback=lambda item: 'again:' + item,
                                return_handle=True)[0]
        self.assertBody('again:one-two', '/api/items/one-two')
        self.assertTrue(self.app.remove_route(handle))
        self.assertStatus(404, '/api/items/one-two')

    def test_route_change_after_match_does_not_affect_current_request(self):
        handle = {}

        def temporary(id):
            self.app.remove_route(handle['current'])
            handle['replacement'] = self.app.route(
                '/diagnostic/<id:int>',
                callback=lambda id: 'next:' + str(id),
                return_handle=True)[0]
            return 'current:ok'

        handle['current'] = self.app.route(
            '/diagnostic/<id:int>',
            callback=temporary,
            return_handle=True)[0]

        self.assertBody('current:ok', '/diagnostic/12')
        self.assertBody('next:34', '/diagnostic/34')

        self.assertTrue(self.app.remove_route(handle['replacement']))
        self.assertStatus(404, '/diagnostic/56')
        self.assertFalse(self.app.remove_route(handle['current']))

    def test_remove_one_duplicate_route_object_registration(self):
        def callback(item):
            return item

        route = bottle.Route(self.app, '/items/<item>', 'GET', callback)
        first = self.app.add_route(route)
        second = self.app.add_route(route)

        self.assertBody('one', '/items/one')
        self.assertTrue(self.app.remove_route(second))
        self.assertIs(first, self.app.routes[0].handle)
        self.assertIs(route, self.app.routes[0])
        self.assertBody('one', '/items/one')
        self.assertTrue(self.app.remove_route(first))
        self.assertEqual([], self.app.routes)
        self.assertStatus(404, '/items/one')
