# -*- coding: utf-8 -*-

import unittest
import bottle
import warnings


class TestRouter(unittest.TestCase):
    CGI = False
    
    def setUp(self):
        self.r = bottle.Router()
    
    def add(self, path, target, method='GET', **ka):
        with warnings.catch_warnings() as r:
            warnings.simplefilter("ignore")
            self.r.add(path, method, target, **ka)

    def match(self, path, method='GET'):
        env = {'PATH_INFO': path, 'REQUEST_METHOD': method}
        if self.CGI:
            env['wsgi.run_once'] = 'true'
        return self.r.match(env)

    def assertMatches(self, rule, url, method='GET', **args):
        self.add(rule, rule, method)
        target, urlargs = self.match(url, method)
        self.assertEqual(rule, target)
        self.assertEqual(args, urlargs)

    def testBasic(self):
        self.assertMatches('/static', '/static')
        self.assertMatches('/\\:its/:#.+#/:test/:name#[a-z]+#/',
                           '/:its/a/cruel/world/',
                           test='cruel', name='world')
        self.assertMatches('/:test', '/test', test='test') # No tail
        self.assertMatches(':test/', 'test/', test='test') # No head
        self.assertMatches('/:test/', '/test/', test='test') # Middle
        self.assertMatches(':test', 'test', test='test') # Full wildcard
        self.assertMatches('/:#anon#/match', '/anon/match') # Anon wildcards
        self.assertRaises(bottle.HTTPError, self.match, '//no/m/at/ch/')

    def testNewSyntax(self):
        self.assertMatches('/static', '/static')
        self.assertMatches('/\\<its>/<:re:.+>/<test>/<name:re:[a-z]+>/',
                           '/<its>/a/cruel/world/',
                           test='cruel', name='world')
        self.assertMatches('/<test>', '/test', test='test') # No tail
        self.assertMatches('<test>/', 'test/', test='test') # No head
        self.assertMatches('/<test>/', '/test/', test='test') # Middle
        self.assertMatches('<test>', 'test', test='test') # Full wildcard
        self.assertMatches('/<:re:anon>/match', '/anon/match') # Anon wildcards
        self.assertRaises(bottle.HTTPError, self.match, '//no/m/at/ch/')

    def testUnicode(self):
        self.assertMatches('/uni/<x>', '/uni/瓶', x='瓶')

    def testValueErrorInFilter(self):
        self.r.add_filter('test', lambda x: ('.*', int, int))

        self.assertMatches('/int/<i:test>', '/int/5', i=5) # No tail
        self.assertRaises(bottle.HTTPError, self.match, '/int/noint')

    def testIntFilter(self):
        self.assertMatches('/object/<id:int>', '/object/567', id=567)
        self.assertRaises(bottle.HTTPError, self.match, '/object/abc')

    def testFloatFilter(self):
        self.assertMatches('/object/<id:float>', '/object/1', id=1)
        self.assertMatches('/object/<id:float>', '/object/1.1', id=1.1)
        self.assertMatches('/object/<id:float>', '/object/.1', id=0.1)
        self.assertMatches('/object/<id:float>', '/object/1.', id=1)
        self.assertRaises(bottle.HTTPError, self.match, '/object/abc')
        self.assertRaises(bottle.HTTPError, self.match, '/object/')
        self.assertRaises(bottle.HTTPError, self.match, '/object/.')

    def testPathFilter(self):
        self.assertMatches('/<id:path>/:f', '/a/b', id='a', f='b')
        self.assertMatches('/<id:path>', '/a', id='a')

    def testAnonWildcard(self):
        self.assertMatches('/anon/<>', '/anon/whatever')
        self.assertMatches('/anonfilter/<:int>', '/anonfilter/5')
        self.assertRaises(bottle.HTTPError, self.match, '/anonfilter/noint')

    def testWildcardNames(self):
        self.assertMatches('/alpha/:abc', '/alpha/alpha', abc='alpha')
        self.assertMatches('/alnum/:md5', '/alnum/sha1', md5='sha1')

    def testParentheses(self):
        self.assertMatches('/func(:param)', '/func(foo)', param='foo')
        self.assertMatches('/func2(:param#(foo|bar)#)', '/func2(foo)', param='foo')
        self.assertMatches('/func2(:param#(foo|bar)#)', '/func2(bar)', param='bar')
        self.assertRaises(bottle.HTTPError, self.match, '/func2(baz)')

    def testErrorInPattern(self):
        self.assertRaises(Exception, self.assertMatches, '/:bug#(#/', '/foo/')
        self.assertRaises(Exception, self.assertMatches, '/<:re:(>/', '/foo/')

    def testBuild(self):
        add, build = self.add, self.r.build
        add('/:test/:name#[a-z]+#/', 'handler', name='testroute')

        url = build('testroute', test='hello', name='world')
        self.assertEqual('/hello/world/', url)

        url = build('testroute', test='hello', name='world', q='value')
        self.assertEqual('/hello/world/?q=value', url)

        # RouteBuildError: Missing URL argument: 'test'
        self.assertRaises(bottle.RouteBuildError, build, 'test')

    def testBuildAnon(self):
        add, build = self.add, self.r.build
        add('/anon/:#.#', 'handler', name='anonroute')

        url = build('anonroute', 'hello')
        self.assertEqual('/anon/hello', url)

        url = build('anonroute', 'hello', q='value')
        self.assertEqual('/anon/hello?q=value', url)

        # RouteBuildError: Missing URL argument: anon0.
        self.assertRaises(bottle.RouteBuildError, build, 'anonroute')

    def testBuildFilter(self):
        add, build = self.add, self.r.build
        add('/int/<:int>', 'handler', name='introute')

        url = build('introute', '5')
        self.assertEqual('/int/5', url)

        # RouteBuildError: Missing URL argument: anon0.
        self.assertRaises(ValueError, build, 'introute', 'hello')

    def test_dynamic_before_static_any(self):
        ''' Static ANY routes have lower priority than dynamic GET routes. '''
        self.add('/foo', 'foo', 'ANY')
        self.assertEqual(self.match('/foo')[0], 'foo')
        self.add('/<:>', 'bar', 'GET')
        self.assertEqual(self.match('/foo')[0], 'bar')

    def test_any_static_before_dynamic(self):
        ''' Static ANY routes have higher priority than dynamic ANY routes. '''
        self.add('/<:>', 'bar', 'ANY')
        self.assertEqual(self.match('/foo')[0], 'bar')
        self.add('/foo', 'foo', 'ANY')
        self.assertEqual(self.match('/foo')[0], 'foo')

    def test_dynamic_any_if_method_exists(self):
        ''' Check dynamic ANY routes if the matching method is known,
            but not matched.'''
        self.add('/bar<:>', 'bar', 'GET')
        self.assertEqual(self.match('/barx')[0], 'bar')
        self.add('/foo<:>', 'foo', 'ANY')
        self.assertEqual(self.match('/foox')[0], 'foo')

    def test_lots_of_routes(self):
        n = bottle.Router._MAX_GROUPS_PER_PATTERN+10
        for i in range(n):        
            self.add('/<:>/'+str(i), str(i), 'GET')
        self.assertEqual(self.match('/foo/'+str(n-1))[0], str(n-1))


class TestRouterRemove(unittest.TestCase):

    def setUp(self):
        self.r = bottle.Router()

    def add(self, path, target, method='GET', **ka):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return self.r.add(path, method, target, **ka)

    def match(self, path, method='GET'):
        env = {'PATH_INFO': path, 'REQUEST_METHOD': method}
        return self.r.match(env)

    def assert404(self, path, method='GET'):
        with self.assertRaises(bottle.HTTPError) as cm:
            self.match(path, method)
        self.assertEqual(404, cm.exception.status_code)

    def assert405(self, path, method, allow):
        with self.assertRaises(bottle.HTTPError) as cm:
            self.match(path, method)
        self.assertEqual(405, cm.exception.status_code)
        self.assertEqual(allow, cm.exception.headers['Allow'])

    def test_add_returns_handle(self):
        handle = self.add('/foo', 'a')
        self.assertIsInstance(handle, bottle.RouteHandle)
        self.assertTrue(handle.active)
        self.assertEqual('/foo', handle.rule)
        self.assertEqual('GET', handle.method)
        self.assertEqual('a', handle.target)

    def test_remove_static(self):
        handle = self.add('/foo', 'a')
        self.assertEqual('a', self.match('/foo')[0])
        self.assertTrue(self.r.remove(handle))
        self.assertFalse(handle.active)
        self.assert404('/foo')

    def test_remove_dynamic(self):
        handle = self.add('/foo/<name>', 'a')
        self.assertEqual(('a', {'name': 'x'}), self.match('/foo/x'))
        self.assertTrue(handle.revoke())
        self.assert404('/foo/x')

    def test_double_revoke_is_noop(self):
        keep = self.add('/keep', 'keep')
        handle = self.add('/foo', 'a')
        self.assertTrue(self.r.remove(handle))
        self.assertTrue(self.r.remove(keep))
        # Revoking an already revoked handle returns False and changes nothing.
        self.assertFalse(self.r.remove(handle))
        self.assertFalse(handle.revoke())
        self.assert404('/foo')
        self.assert404('/keep')

    def test_handle_is_precise_not_path_based(self):
        # Two registrations for the same rule: the second overwrites the
        # first. Only the second handle stays revocable.
        first = self.add('/foo', 'first')
        second = self.add('/foo', 'second')
        self.assertFalse(first.active)
        self.assertEqual('second', self.match('/foo')[0])
        self.assertFalse(self.r.remove(first))
        self.assertEqual('second', self.match('/foo')[0])
        self.assertTrue(self.r.remove(second))
        self.assert404('/foo')

    def test_handle_from_other_router_rejected(self):
        other = bottle.Router()
        handle = other.add('/foo', 'a', 'GET')
        self.assertRaises(bottle.RouteError, self.r.remove, handle)
        self.assertRaises(bottle.RouteError, self.r.remove, '/foo')

    def test_shadowed_static_candidate_restored(self):
        # A static route shadows a dynamic one. Removing the static route
        # makes the previously shadowed dynamic route visible again.
        dyn = self.add('/item/<name>', 'dyn')
        static = self.add('/item/list', 'static')
        self.assertEqual('static', self.match('/item/list')[0])
        self.r.remove(static)
        self.assertEqual(('dyn', {'name': 'list'}), self.match('/item/list'))
        self.r.remove(dyn)
        self.assert404('/item/list')

    def test_shadowed_dynamic_candidate_restored(self):
        # The generic dynamic rule is registered first and shadows the more
        # specific one. Removing it re-activates the specific rule, including
        # its input filter.
        generic = self.add('/d/<value>', 'generic')
        specific = self.add('/d/<value:int>', 'specific')
        self.assertEqual(('generic', {'value': '5'}), self.match('/d/5'))
        self.r.remove(generic)
        self.assertEqual(('specific', {'value': 5}), self.match('/d/5'))
        self.r.remove(specific)
        self.assert404('/d/5')

    def test_group_positions_recomputed(self):
        # Removing a rule in the middle shifts the group positions within the
        # combined regular expression. Remaining rules must still map to
        # their own targets and arguments.
        handles = [self.add('/r%d/<name>' % i, 'target%d' % i) for i in range(5)]
        self.r.remove(handles[1])
        self.r.remove(handles[3])
        for i in (0, 2, 4):
            self.assertEqual(('target%d' % i, {'name': 'x'}),
                             self.match('/r%d/x' % i))
        self.assert404('/r1/x')
        self.assert404('/r3/x')

    def test_group_positions_recomputed_across_chunks(self):
        # Same as above, but across the boundary of two combined patterns.
        n = bottle.Router._MAX_GROUPS_PER_PATTERN + 10
        handles = [self.add('/<:>/%d' % i, str(i)) for i in range(n)]
        self.r.remove(handles[0])
        self.r.remove(handles[bottle.Router._MAX_GROUPS_PER_PATTERN - 1])
        self.r.remove(handles[bottle.Router._MAX_GROUPS_PER_PATTERN])
        self.assert404('/x/0')
        self.assertEqual((str(n - 1), {}), self.match('/x/%d' % (n - 1)))
        self.assertEqual(('1', {}), self.match('/x/1'))
        self.assertEqual((str(bottle.Router._MAX_GROUPS_PER_PATTERN + 1), {}),
                         self.match('/x/%d' % (bottle.Router._MAX_GROUPS_PER_PATTERN + 1)))

    def test_custom_filter_with_groups(self):
        # A custom filter whose pattern contains capturing groups. Group
        # positions in the combined pattern must stay correct after removal.
        self.r.add_filter('pair', lambda conf: (r'(\d+)-(\d+)', None, None))
        first = self.add('/range/<p:pair>', 'pair')
        second = self.add('/range/<p:pair>/sub', 'pair-sub')
        third = self.add('/other/<p:pair>', 'other')
        self.assertEqual(('pair', {'p': '1-2'}), self.match('/range/1-2'))
        self.r.remove(first)
        self.assert404('/range/1-2')
        self.assertEqual(('pair-sub', {'p': '3-4'}), self.match('/range/3-4/sub'))
        self.assertEqual(('other', {'p': '5-6'}), self.match('/other/5-6'))
        self.r.remove(second)
        self.r.remove(third)
        self.assert404('/range/3-4/sub')
        self.assert404('/other/5-6')

    def test_named_route_visibility_after_revoke(self):
        # With multiple registrations sharing a name, the most recent live
        # registration is visible to the URL builder. Revoking it reveals
        # the previous one.
        first = self.add('/a/<x>', 'a', name='n')
        second = self.add('/b/<x>', 'b', name='n')
        self.assertEqual('/b/1', self.r.build('n', x=1))
        self.r.remove(second)
        self.assertEqual('/a/1', self.r.build('n', x=1))
        self.r.remove(first)
        self.assertRaises(bottle.RouteBuildError, self.r.build, 'n', x=1)

    def test_named_route_revoke_older_first(self):
        # Revoking the older of two same-named registrations keeps the
        # newest visible.
        first = self.add('/a', 'a', name='n')
        second = self.add('/b', 'b', name='n')
        self.r.remove(first)
        self.assertEqual('/b', self.r.build('n'))
        self.r.remove(second)
        self.assertRaises(bottle.RouteBuildError, self.r.build, 'n')

    def test_rule_builder_removed_after_revoke(self):
        first = self.add('/same/<x:int>', 'a')
        second = self.add('/same/<x:int>', 'b')
        self.r.remove(second)
        # The first registration was overwritten, so its builder is gone too.
        self.assertRaises(bottle.RouteBuildError, self.r.build, '/same/<x:int>', x=1)

    def test_method_set_and_head_updated(self):
        get = self.add('/res', 'get', 'GET')
        post = self.add('/res', 'post', 'POST')
        # HEAD falls back to the GET route.
        self.assertEqual('get', self.match('/res', 'HEAD')[0])
        self.assert405('/res', 'DELETE', 'GET,POST')
        self.r.remove(post)
        self.assert405('/res', 'DELETE', 'GET')
        self.r.remove(get)
        self.assert404('/res', 'HEAD')
        self.assert404('/res', 'DELETE')

    def test_method_set_updated_dynamic(self):
        get = self.add('/dyn/<x>', 'get', 'GET')
        post = self.add('/dyn/<x>', 'post', 'POST')
        self.assert405('/dyn/1', 'DELETE', 'GET,POST')
        self.r.remove(get)
        self.assert405('/dyn/1', 'DELETE', 'POST')
        self.r.remove(post)
        self.assert404('/dyn/1', 'DELETE')

    def test_inflight_match_keeps_target(self):
        # A request that already matched keeps its selected target even if
        # the registration is revoked before the callback runs. The next
        # match sees the new table.
        handle = self.add('/foo/<x>', 'callback')
        target, args = self.match('/foo/1')
        self.r.remove(handle)
        self.assertEqual('callback', target)
        self.assertEqual({'x': '1'}, args)
        self.assert404('/foo/1')

    def test_interleaved_sequence(self):
        # Interleaved register/match/revoke/re-register sequence.
        a = self.add('/seq/<x:int>', 'a')
        self.assertEqual(('a', {'x': 1}), self.match('/seq/1'))
        b = self.add('/seq/<x>', 'b')
        # The int rule was registered first and still wins for integers.
        self.assertEqual(('a', {'x': 1}), self.match('/seq/1'))
        self.assertEqual(('b', {'x': 'y'}), self.match('/seq/y'))
        self.r.remove(a)
        # Now the generic rule takes over, without the int filter.
        self.assertEqual(('b', {'x': '1'}), self.match('/seq/1'))
        c = self.add('/seq/<x:int>', 'c')
        # Re-registered int rule is appended after the generic rule and
        # therefore shadowed by it.
        self.assertEqual(('b', {'x': '2'}), self.match('/seq/2'))
        self.r.remove(b)
        self.assertEqual(('c', {'x': 2}), self.match('/seq/2'))
        self.r.remove(c)
        self.assert404('/seq/2')

    def test_remove_all_dynamic_clears_method(self):
        handle = self.add('/only/<x>', 'a', 'PUT')
        self.r.remove(handle)
        # No dynamic routes left for PUT: no 405, no stale combined regex.
        self.assert404('/only/1', 'PUT')
        self.assertNotIn('PUT', self.r.dyna_regexes)

    def test_remove_static_cleans_method(self):
        handle = self.add('/only', 'a', 'PUT')
        self.r.remove(handle)
        self.assert404('/only', 'PUT')
        self.assertNotIn('PUT', self.r.static)

    def test_strict_order_dynamic_removal(self):
        r = bottle.Router(strict=True)
        handle = r.add('/plain', 'GET', 'static-ish')
        self.assertEqual('static-ish', r.match(
            {'PATH_INFO': '/plain', 'REQUEST_METHOD': 'GET'})[0])
        r.remove(handle)
        with self.assertRaises(bottle.HTTPError) as cm:
            r.match({'PATH_INFO': '/plain', 'REQUEST_METHOD': 'GET'})
        self.assertEqual(404, cm.exception.status_code)


class TestRouterInCGIMode(TestRouter):
    ''' Makes no sense since the default route does not optimize CGI anymore.'''
    CGI = True
