import functools
import io
import unittest
import wsgiref.util
import bottle
from .tools import api
from bottle import _re_flatten


class TestReFlatten(unittest.TestCase):

    def test_re_flatten(self):
        self.assertEqual(_re_flatten(r"(?:aaa)(_bbb)"), '(?:aaa)(?:_bbb)')
        self.assertEqual(_re_flatten(r"(aaa)(_bbb)"), '(?:aaa)(?:_bbb)')
        self.assertEqual(_re_flatten(r"aaa)(_bbb)"), 'aaa)(?:_bbb)')
        self.assertEqual(_re_flatten(r"aaa(_bbb)"), 'aaa(?:_bbb)')
        self.assertEqual(_re_flatten(r"aaa_bbb"), 'aaa_bbb')


class TestRoute(unittest.TestCase):

    @api('0.12')
    def test_callback_inspection(self):
        def x(a, b): pass
        def d(f):
            @functools.wraps(f)
            def w():
                return f()
            return w
        route = bottle.Route(bottle.Bottle(), None, None, d(x))
        self.assertEqual(route.get_undecorated_callback(), x)
        self.assertEqual(set(route.get_callback_args()), set(['a', 'b']))

        def d2(foo):
            def d(f):
                @functools.wraps(f)
                def w():
                    return f()
                return w
            return d

        route = bottle.Route(bottle.Bottle(), None, None, d2('foo')(x))
        self.assertEqual(route.get_undecorated_callback(), x)
        self.assertEqual(set(route.get_callback_args()), set(['a', 'b']))

    def test_callback_inspection_multiple_args(self):
        # decorator with argument, modifying kwargs
        def d2(f="1"):
            def d(fn):
                @functools.wraps(fn)
                def w(*args, **kwargs):
                    # modification of kwargs WITH the decorator argument
                    # is necessary requirement for the error
                    kwargs["a"] = f
                    return fn(*args, **kwargs)
                return w
            return d

        @d2(f='foo')
        def x(a, b):
            return

        route = bottle.Route(bottle.Bottle(), None, None, x)

        # triggers the "TypeError: 'foo' is not a Python function"
        self.assertEqual(set(route.get_callback_args()), set(['a', 'b']))

    def test_callback_inspection_newsig(self):
        env = {}
        eval(compile('def foo(a, *, b=5): pass', '<foo>', 'exec'), env, env)
        route = bottle.Route(bottle.Bottle(), None, None, env['foo'])
        self.assertEqual(set(route.get_callback_args()), set(['a', 'b']))

    def test_unwrap_wrapped(self):
        import functools
        def func(): pass
        @functools.wraps(func)
        def wrapped():
            return func()

        route = bottle.Route(bottle.Bottle(), None, None, wrapped)
        self.assertEqual(route.get_undecorated_callback(), func)

    @api("0.12", "0.14")
    def test_unwrap_closure(self):
        def func(): pass
        wrapped = _null_decorator(func, update_wrapper=False)
        route = bottle.Route(bottle.Bottle(), None, None, wrapped)
        self.assertEqual(route.get_undecorated_callback(), func)

    # @api("0.15")
    # def test_not_unwrap_closure(self):
    #     def other(): pass
    #     def func():
    #         return other()
    #     route = bottle.Route(bottle.Bottle(), None, None, func)
    #     self.assertEqual(route.get_undecorated_callback(), func)

    @api("0.13", "0.14")
    def test_unwrap_closure_callable(self):
        class Foo:
            def __call__(self): pass

        func = Foo()
        wrapped = _null_decorator(func, update_wrapper=False)
        route = bottle.Route(bottle.Bottle(), None, None, wrapped)
        self.assertEqual(route.get_undecorated_callback(), func)
        repr(route) # Raised cause cb has no '__name__'

    def test_unwrap_method(self):
        def func(self): pass

        class Foo:
            test = _null_decorator(func)

        wrapped = Foo().test
        route = bottle.Route(bottle.Bottle(), None, None, wrapped)
        self.assertEqual(route.get_undecorated_callback(), func)


def _null_decorator(func, update_wrapper=True):
    def wrapper():
        return func()
    if update_wrapper:
        functools.update_wrapper(wrapper, func)
    return wrapper


class TestRouteRemoval(unittest.TestCase):

    def make_app(self):
        return bottle.Bottle()

    def request(self, app, path, method='GET'):
        env = {}
        wsgiref.util.setup_testing_defaults(env)
        env['REQUEST_METHOD'] = method
        env['PATH_INFO'] = path
        env['wsgi.input'] = io.BytesIO(b'')
        status = []

        def start_response(s, h, exc_info=None):
            status.append(s)

        body = b''.join(app.wsgi(env, start_response))
        return int(status[0].split()[0]), body

    def add_route(self, app, rule, callback, method='GET', **ka):
        route = bottle.Route(app, rule, method, callback, **ka)
        handle = app.add_route(route)
        return handle, route

    def test_add_route_returns_handle(self):
        app = self.make_app()
        handle, route = self.add_route(app, '/diag', lambda: 'ok')
        self.assertIsInstance(handle, bottle.RouteHandle)
        self.assertIs(handle.target, route)
        self.assertEqual((200, b'ok'), self.request(app, '/diag'))

    def test_remove_route(self):
        app = self.make_app()
        handle, route = self.add_route(app, '/diag', lambda: 'ok')
        self.assertEqual(200, self.request(app, '/diag')[0])
        self.assertTrue(app.remove_route(handle))
        self.assertNotIn(route, app.routes)
        self.assertEqual(404, self.request(app, '/diag')[0])
        # Revoking the same handle twice is a no-op.
        self.assertFalse(app.remove_route(handle))
        self.assertEqual(404, self.request(app, '/diag')[0])

    def test_remove_route_dynamic(self):
        app = self.make_app()
        handle, route = self.add_route(app, '/diag/<name>', lambda name: name)
        self.assertEqual((200, b'x'), self.request(app, '/diag/x'))
        app.remove_route(handle)
        self.assertEqual(404, self.request(app, '/diag/x')[0])

    def test_remove_route_updates_head_and_405(self):
        app = self.make_app()
        get, _ = self.add_route(app, '/res', lambda: 'get', 'GET')
        post, _ = self.add_route(app, '/res', lambda: 'post', 'POST')
        self.assertEqual(200, self.request(app, '/res', 'HEAD')[0])
        app.remove_route(post)
        self.assertEqual(405, self.request(app, '/res', 'DELETE')[0])
        app.remove_route(get)
        self.assertEqual(404, self.request(app, '/res', 'HEAD')[0])
        self.assertEqual(404, self.request(app, '/res', 'DELETE')[0])

    def test_revoke_during_request(self):
        # A registration revoked by the currently running request stays
        # usable for that request. The next request sees the new table.
        app = self.make_app()
        holder = {}

        def diag():
            app.remove_route(holder['handle'])
            return 'ok'

        holder['handle'], _ = self.add_route(app, '/diag', diag)
        self.assertEqual((200, b'ok'), self.request(app, '/diag'))
        self.assertEqual(404, self.request(app, '/diag')[0])

    def test_named_route_visibility(self):
        app = self.make_app()
        first, _ = self.add_route(app, '/a', lambda: 'a', name='n')
        second, _ = self.add_route(app, '/b', lambda: 'b', name='n')
        self.assertEqual('/b', app.router.build('n'))
        app.remove_route(second)
        self.assertEqual('/a', app.router.build('n'))
        app.remove_route(first)
        self.assertRaises(bottle.RouteBuildError, app.router.build, 'n')

    def test_shadowed_route_restored(self):
        app = self.make_app()
        dyn, _ = self.add_route(app, '/item/<name>', lambda name: 'dyn')
        static, _ = self.add_route(app, '/item/list', lambda: 'static')
        self.assertEqual((200, b'static'), self.request(app, '/item/list'))
        app.remove_route(static)
        self.assertEqual((200, b'dyn'), self.request(app, '/item/list'))
        app.remove_route(dyn)
        self.assertEqual(404, self.request(app, '/item/list')[0])

    def test_mounted_app_removal(self):
        parent = self.make_app()
        child = self.make_app()
        pair_filter = lambda conf: (r'(\d+)-(\d+)', None, None)
        parent.router.add_filter('pair', pair_filter)
        child.router.add_filter('pair', pair_filter)

        @child.route('/inner/<p:pair>')
        def inner(p):
            return 'inner:' + p

        @child.route('/plain')
        def plain():
            return 'plain'

        handles = parent.mount('/sub/', child)
        self.assertEqual(2, len(handles))
        by_rule = dict((h.rule, h) for h in handles)
        self.assertEqual((200, b'inner:1-2'), self.request(parent, '/sub/inner/1-2'))
        self.assertEqual((200, b'plain'), self.request(parent, '/sub/plain'))
        # Revoke the dynamic mounted route; the static one keeps working.
        self.assertTrue(parent.remove_route(by_rule['/sub/inner/<p:pair>']))
        self.assertEqual(404, self.request(parent, '/sub/inner/1-2')[0])
        self.assertEqual((200, b'plain'), self.request(parent, '/sub/plain'))
        # Re-register and revoke the remaining route.
        self.assertTrue(parent.remove_route(by_rule['/sub/plain']))
        self.assertEqual(404, self.request(parent, '/sub/plain')[0])

    def test_interleaved_app_sequence(self):
        app = self.make_app()
        first, _ = self.add_route(app, '/x/<i:int>', lambda i: 'int:%d' % i)
        self.assertEqual((200, b'int:1'), self.request(app, '/x/1'))
        second, _ = self.add_route(app, '/x/<i>', lambda i: 'any:%s' % i)
        self.assertEqual((200, b'int:1'), self.request(app, '/x/1'))
        self.assertEqual((200, b'any:a'), self.request(app, '/x/a'))
        app.remove_route(first)
        self.assertEqual((200, b'any:1'), self.request(app, '/x/1'))
        third, _ = self.add_route(app, '/x/<i:int>', lambda i: 'int2:%d' % i)
        # Re-registered rule is appended and shadowed by the generic one.
        self.assertEqual((200, b'any:2'), self.request(app, '/x/2'))
        app.remove_route(second)
        self.assertEqual((200, b'int2:2'), self.request(app, '/x/2'))
        app.remove_route(third)
        self.assertEqual(404, self.request(app, '/x/2')[0])
