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

    def reports(self):
        return {(report['winner'], report['loser']): report
                for report in self.r.route_diagnostics()
                if report['status'] != 'unknown'}

    def assertReport(self, winner, loser, method, witness, expected_target,
                     status='ambiguous'):
        report = self.reports()[(winner, loser)]
        self.assertEqual(status, report['status'])
        self.assertEqual(method, report['method'])
        self.assertEqual(witness, report['witness'])
        matched_target, args = self.match(witness, method)
        self.assertEqual(expected_target, matched_target)
        return report

    def test_route_diagnostics_static_shadow(self):
        self.add('/files/<name>', 'dynamic')
        self.add('/files/settings', 'static')
        report = self.assertReport('/files/settings', '/files/<name>',
                                   'GET', '/files/settings', 'static')
        self.assertEqual(['/files/settings', '/files/<name>'], report['rules'])

    def test_route_diagnostics_numeric_filters_intersect(self):
        self.add('/items/<id:int>', 'integer')
        self.add('/items/<id:float>', 'floating')
        self.assertReport('/items/<id:int>', '/items/<id:float>',
                          'GET', '/items/00', 'integer')

    def test_route_diagnostics_path_filter_intersection(self):
        self.add('/files/<name>', 'name')
        self.add('/files/<path:path>', 'path')
        self.assertReport('/files/<name>', '/files/<path:path>',
                          'GET', '/files/-', 'name')

    def test_builtin_str_filter(self):
        self.assertMatches('/files/<name:str>', '/files/report',
                           name='report')

    def test_route_diagnostics_head_fallback(self):
        self.add('/shared/<name>', 'get', 'GET')
        self.add('/shared/<name>', 'head', 'HEAD')
        self.assertReport('/shared/<name>', '/shared/<name>',
                          'HEAD', '/shared/-', 'head', 'shadowed')
        self.assertEqual(['GET', 'HEAD'],
                         self.reports()[('/shared/<name>',
                                         '/shared/<name>')]['methods'])

    def test_route_diagnostics_ignores_disjoint_methods(self):
        self.add('/shared/<name>', 'get', 'GET')
        self.add('/shared/<name>', 'post', 'POST')
        self.assertEqual({}, self.reports())

    def test_route_diagnostics_unknown_custom_rules(self):
        self.add('/known/<name>', 'known')
        self.add('/custom/<name:re:[a-z]+>', 'regular-expression')
        self.r.add_filter('digits', lambda conf: (r'\d+', int, str))
        self.add('/filtered/<name:digits>', 'custom-filter')
        unknown = [report for report in self.r.route_diagnostics()
                   if report['status'] == 'unknown']
        self.assertEqual(
            ['/custom/<name:re:[a-z]+>', '/filtered/<name:digits>'],
            [report['rule'] for report in unknown])
        self.assertEqual(
            ['<name:re:[a-z]+>', '<name:digits>'],
            [report['segment'] for report in unknown])

    def test_route_diagnostics_is_stable_and_read_only(self):
        self.add('/files/<name>', 'name')
        self.add('/files/<path:path>', 'path')
        before = self.r.route_diagnostics()
        routes_before = (dict(self.r.static), self.r.dyna_routes.copy())
        after = self.r.route_diagnostics()
        self.assertEqual(before, after)
        self.assertEqual(routes_before,
                         (dict(self.r.static), self.r.dyna_routes.copy()))

    def test_bottle_exposes_route_diagnostics(self):
        app = bottle.Bottle()

        @app.route('/files/<name>')
        def name(name):
            return name

        @app.route('/files/<path:path>')
        def path(path):
            return path

        report = app.route_diagnostics()[0]
        self.assertEqual('/files/<name>', report['winner'])
        self.assertEqual('/files/<path:path>', report['loser'])

class TestRouterInCGIMode(TestRouter):
    ''' Makes no sense since the default route does not optimize CGI anymore.'''
    CGI = True
