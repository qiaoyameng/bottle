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

    def diagnostic(self, routes):
        for path, target, method in routes:
            self.add(path, target, method)
        return self.r.diagnose_routes()

    def test_diagnostic_static_shadow(self):
        report = self.diagnostic([
            ('/files/<name:str>', 'dynamic', 'GET'),
            ('/files/name', 'static', 'GET'),
        ])
        self.assertEqual([], report['unknown'])
        conflict, = report['conflicts']
        self.assertEqual('ambiguous', conflict['type'])
        self.assertEqual('/files/name', conflict['witness'])
        self.assertEqual('static', self.match('/files/name')[0])

    def test_diagnostic_numeric_filters_intersect(self):
        report = self.diagnostic([
            ('/files/<id:int>', 'integer', 'GET'),
            ('/files/<id:float>', 'floating', 'GET'),
        ])
        conflict, = report['conflicts']
        self.assertEqual('ambiguous', conflict['type'])
        self.assertEqual('integer', self.match(conflict['witness'])[0])
        self.assertEqual(int, type(conflict['witness_args']['id']))

    def test_diagnostic_path_capture(self):
        report = self.diagnostic([
            ('/files/<name:str>', 'name', 'GET'),
            ('/files/<path:path>', 'path', 'GET'),
        ])
        conflict, = report['conflicts']
        self.assertEqual('ambiguous', conflict['type'])
        self.assertNotIn('/', conflict['witness'].rsplit('/', 1)[1])
        self.assertEqual('name', self.match(conflict['witness'])[0])

    def test_diagnostic_head_fallback(self):
        report = self.diagnostic([
            ('/files/<id:int>', 'integer', 'GET'),
            ('/files/<id:float>', 'floating', 'HEAD'),
        ])
        conflict, = report['conflicts']
        self.assertEqual('HEAD', conflict['witness_method'])
        self.assertEqual('floating',
                         self.match(conflict['witness'], 'HEAD')[0])
        self.assertEqual(float, type(conflict['witness_args']['id']))

    def test_diagnostic_disjoint_rules(self):
        report = self.diagnostic([
            ('/files/<id:int>', 'file', 'GET'),
            ('/other/<id:int>', 'other', 'GET'),
        ])
        self.assertEqual({'conflicts': [], 'unknown': []}, report)

    def test_diagnostic_unrelated_methods(self):
        report = self.diagnostic([
            ('/files/<id:int>', 'get', 'GET'),
            ('/files/<id:int>', 'post', 'POST'),
        ])
        self.assertEqual({'conflicts': [], 'unknown': []}, report)

    def test_diagnostic_full_shadow(self):
        report = self.diagnostic([
            ('/files/<id:float>', 'floating', 'GET'),
            ('/files/<id:int>', 'integer', 'GET'),
        ])
        conflict, = report['conflicts']
        self.assertEqual('shadowed', conflict['type'])
        self.assertEqual('/files/<id:int>', conflict['shadowed_rule'])
        self.assertEqual('floating', self.match(conflict['witness'])[0])

    def test_diagnostic_unknown_regex_is_not_probed(self):
        self.add('/files/<id:re:[a-z]+>', 'regex', 'GET')
        self.add('/files/<id:str>', 'string', 'GET')
        before = str(self.r.dyna_routes)
        report = self.r.diagnose_routes()
        self.assertEqual([], report['conflicts'])
        unknown, = report['unknown']
        self.assertIn('regular expression', unknown['reason'])
        self.assertEqual('<id:re:[a-z]+>', unknown['segment'])
        self.assertEqual(before, str(self.r.dyna_routes))

    def test_diagnostic_legacy_custom_regex_is_unknown(self):
        self.add('/:#[a-z]+#', 'legacy', 'GET')
        unknown, = self.r.diagnose_routes()['unknown']
        self.assertEqual(':#[a-z]+#', unknown['segment'])

    def test_diagnostic_is_stable_and_read_only(self):
        self.add('/files/<id:int>', 'integer', 'GET')
        self.add('/files/<id:float>', 'floating', 'GET')
        static_state = str(self.r.static)
        dynamic_state = str(self.r.dyna_routes)
        first = self.r.route_diagnostics()
        second = self.r.route_diagnostics()
        self.assertEqual(first, second)
        self.assertEqual(static_state, str(self.r.static))
        self.assertEqual(dynamic_state, str(self.r.dyna_routes))


class TestRouterInCGIMode(TestRouter):
    ''' Makes no sense since the default route does not optimize CGI anymore.'''
    CGI = True
