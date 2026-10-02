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

    def test_remove_rebuilds_group_positions_across_patterns(self):
        handles = [self.r.add('/%d/<id>' % i, 'GET', str(i))
                   for i in range(bottle.Router._MAX_GROUPS_PER_PATTERN + 10)]

        for handle in handles[:-10]:
            self.assertTrue(handle.remove())

        index = bottle.Router._MAX_GROUPS_PER_PATTERN + 9
        self.assertEqual(str(index), self.match('/%d/value' % index)[0])
        self.assertEqual(1, len(self.r.dyna_regexes['GET']))

        for handle in handles[:-10]:
            self.assertFalse(handle.remove())
        for handle in handles[-10:]:
            self.assertTrue(handle.remove())

    def test_remove_static_route_updates_method_set(self):
        get = self.r.add('/users', 'GET', 'get')
        post = self.r.add('/users', 'POST', 'post')

        self.assert_error('/users', 'PUT', 405, 'GET,POST')
        self.assertTrue(get.remove())
        self.assert_error('/users', 'PUT', 405, 'POST')
        self.assert_error('/users', 'GET', 405, 'POST')
        self.assertTrue(post.remove())
        self.assert_error('/users', 'PUT', 404)

    def test_remove_by_handle_restores_previous_registration(self):
        generic = self.r.add('/<x>', 'GET', 'generic')
        specific = self.r.add('/foo', 'GET', 'specific')

        self.assertEqual('specific', self.match('/foo')[0])
        self.assertTrue(specific.remove())
        self.assertEqual(('generic', {'x': 'foo'}), self.match('/foo'))

        specific = self.r.add('/foo', 'GET', 'specific-again')
        self.assertEqual('specific-again', self.match('/foo')[0])
        self.assertTrue(generic.remove())
        self.assertEqual('specific-again', self.match('/foo')[0])
        self.assertTrue(specific.remove())
        self.assertRaises(bottle.HTTPError, self.match, '/foo')
        self.assertFalse(specific.remove())

    def test_remove_exact_duplicate_registration(self):
        first = self.r.add('/item/<id>', 'GET', 'first')
        second = self.r.add('/item/<id>', 'GET', 'second')

        self.assertEqual('second', self.match('/item/1')[0])
        self.assertTrue(second.remove())
        self.assertEqual('first', self.match('/item/1')[0])
        self.assertFalse(second.remove())

        third = self.r.add('/item/<id>', 'GET', 'third')
        self.assertEqual('third', self.match('/item/1')[0])
        self.assertTrue(first.remove())
        self.assertEqual('third', self.match('/item/1')[0])
        self.assertTrue(third.remove())
        self.assertRaises(bottle.HTTPError, self.match, '/item/1')

    def test_remove_updates_named_route_builders(self):
        first = self.r.add('/old/<id>', 'GET', 'first', name='item')
        second = self.r.add('/new/<id>', 'GET', 'second', name='item')

        self.assertEqual('/new/1', self.r.build('item', id=1))
        self.assertTrue(second.remove())
        self.assertEqual('/old/1', self.r.build('item', id=1))
        self.assertTrue(first.remove())
        self.assertRaises(bottle.RouteBuildError, self.r.build, 'item', id=1)

    def assert_error(self, path, method, status, allow=None):
        with self.assertRaises(bottle.HTTPError) as context:
            self.match(path, method)
        self.assertEqual(status, context.exception.status_code)
        if allow is not None:
            self.assertEqual(allow, context.exception.headers['Allow'])

    def test_remove_updates_method_sets_and_head_fallback(self):
        get = self.r.add('/users/<id:int>', 'GET', 'get')
        post = self.r.add('/users/<id:int>', 'POST', 'post')

        self.assertEqual('get', self.match('/users/1')[0])
        self.assert_error('/users/1', 'PUT', 405, 'GET,POST')

        self.assertTrue(get.remove())
        self.assert_error('/users/1', 'GET', 405, 'POST')
        self.assert_error('/users/1', 'PUT', 405, 'POST')
        self.assert_error('/users/1', 'HEAD', 405, 'POST')

        head = self.r.add('/users/<id:int>', 'HEAD', 'head')
        self.assertEqual('head', self.match('/users/1', 'HEAD')[0])
        options = self.r.add('/users/<id:int>', 'OPTIONS', 'options')
        self.assert_error('/users/1', 'PUT', 405, 'HEAD,OPTIONS,POST')

        self.assertTrue(post.remove())
        self.assert_error('/users/1', 'PUT', 405, 'HEAD,OPTIONS')
        self.assertTrue(head.remove())
        self.assertTrue(options.remove())
        self.assert_error('/users/1', 'PUT', 404)

    def test_remove_rebuilds_dynamic_group_positions(self):
        def pair_filter(config):
            return r'(\w+)-(\w+)', None, None

        self.r.add_filter('pair', pair_filter)
        first = self.r.add('/a/<x>', 'GET', 'first')
        pair = self.r.add('/items/<item:pair>', 'GET', 'pair')
        fallback = self.r.add('/<other:path>', 'GET', 'fallback')

        self.assertEqual(('first', {'x': '1'}), self.match('/a/1'))
        self.assertEqual(('pair', {'item': 'one-two'}),
                         self.match('/items/one-two'))
        self.assertEqual(('fallback', {'other': 'other'}),
                         self.match('/other'))

        self.assertTrue(first.remove())
        self.assertEqual(('pair', {'item': 'one-two'}),
                         self.match('/items/one-two'))
        self.assertEqual(('fallback', {'other': 'other'}),
                         self.match('/other'))
        self.assertTrue(pair.remove())
        self.assertEqual(('fallback', {'other': 'items/one-two'}),
                         self.match('/items/one-two'))
        self.assertTrue(fallback.remove())
        self.assertRaises(bottle.HTTPError, self.match, '/items/one-two')

class TestRouterInCGIMode(TestRouter):
    ''' Makes no sense since the default route does not optimize CGI anymore.'''
    CGI = True
