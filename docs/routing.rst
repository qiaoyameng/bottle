.. currentmodule:: bottle

================================================================================
Request Routing
================================================================================

Bottle uses a powerful routing engine to find the right callback for each request. The :ref:`tutorial <tutorial-routing>` shows you the basics. This document covers advanced techniques and rule mechanics in detail.

Rule Syntax
--------------------------------------------------------------------------------

The :class:`Router` distinguishes between two basic types of routes: **static routes** (e.g. ``/contact``) and **dynamic routes** (e.g. ``/hello/<name>``). A route that contains one or more *wildcards* it is considered dynamic. All other routes are static.

.. versionchanged:: 0.10

The simplest form of a wildcard consists of a name enclosed in angle brackets (e.g. ``<name>``). The name should be unique for a given route and form a valid python identifier (alphanumeric, starting with a letter). This is because wildcards are used as keyword arguments for the request callback later.

Each wildcard matches one or more characters, but stops at the first slash (``/``). This equals a regular expression of ``[^/]+`` and ensures that only one path segment is matched and routes with more than one wildcard stay unambiguous.

The rule ``/<action>/<item>`` matches as follows:

============ =========================================
Path         Result
============ =========================================
/save/123    ``{'action': 'save', 'item': '123'}``
/save/123/   `No Match`
/save/       `No Match`
//123        `No Match`
============ =========================================

It is possible to escape characters like colon ``:`` with a backslash ``\``. This will prevent to trigger the old syntax in case you need to use ``:``.
For example: the rule ``/<action>/item:<id>`` triggers the old syntax, (see below) but ``/action/item\:<id>`` works as intended with the new syntax. 


You can change the exact behaviour in many ways using filters. This is described in the next section.

Wildcard Filters
--------------------------------------------------------------------------------

.. versionadded:: 0.10

Filters are used to define more specific wildcards, and/or transform the matched part of the URL before it is passed to the callback. A filtered wildcard is declared as ``<name:filter>`` or ``<name:filter:config>``. The syntax for the optional config part depends on the filter used.

The following standard filters are implemented:

* **:int** matches (signed) digits and converts the value to integer.
* **:float** similar to :int but for decimal numbers.
* **:path** matches all characters including the slash character in a non-greedy way and may be used to match more than one path segment.
* **:re[:exp]** allows you to specify a custom regular expression in the config field. The matched value is not modified.

You can add your own filters to the router. All you need is a function that returns three elements: A regular expression string, a callable to convert the URL fragment to a python value, and a callable that does the opposite. The filter function is called with the configuration string as the only parameter and may parse it as needed::

    app = Bottle()

    def list_filter(config):
        ''' Matches a comma separated list of numbers. '''
        delimiter = config or ','
        regexp = r'\d+(%s\d)*' % re.escape(delimiter)

        def to_python(match):
            return map(int, match.split(delimiter))
        
        def to_url(numbers):
            return delimiter.join(map(str, numbers))
        
        return regexp, to_python, to_url

    app.router.add_filter('list', list_filter)

    @app.route('/follow/<ids:list>')
    def follow_users(ids):
        for id in ids:
            ...


Legacy Syntax
--------------------------------------------------------------------------------

.. versionchanged:: 0.10

The new rule syntax was introduced in **Bottle 0.10** to simplify some common use cases, but the old syntax still works and you can find lot of code examples still using it. The differences are best described by example:

=================== ====================
Old Syntax          New Syntax
=================== ====================
``:name``           ``<name>``
``:name#regexp#``   ``<name:re:regexp>``
``:#regexp#``       ``<:re:regexp>``
``:##``             ``<:re>``
=================== ====================

Try to avoid the old syntax in future projects if you can. It is not currently deprecated, but will be eventually.


Host Rules
--------------------------------------------------------------------------------

.. versionadded:: 0.14

Routes can be restricted to a specific request host with the ``host`` parameter of :meth:`Bottle.route`. This allows different applications or tenants to be served from the same URL path, depending on the ``Host`` header of the request::

    @app.route('/reports/<id>', host='<tenant>.example.com')
    def report(tenant, id):
        ...

Host rules use the same wildcard syntax and filters as path rules, with two differences: A wildcard without a filter matches a single DNS label (``[^.]+`` instead of ``[^/]+``), and the deprecated ``:name`` syntax is not allowed, because a colon is ambiguous with the port separator. Wildcard names must be unique across the host rule and the path rule of a route; a name collision raises :exc:`RouteSyntaxError` when the route is registered.

An optional port restricts the rule to requests with that port (e.g. ``example.com:8080``). A rule without a port matches any port. The default port of the request scheme (80 for http, 443 for https) is normalized away, so ``example.com`` and ``example.com:80`` are the same request host and never match the same rule twice.

Hostnames are normalized before matching, so rules and requests compare equal regardless of:

* **Case:** Hostnames are matched case-insensitively.
* **Trailing dot:** ``example.com.`` equals ``example.com``.
* **Internationalized domain names:** Unicode names and their punycode form are interchangeable (``münchen.de`` equals ``xn--mnchen-3ya.de``). Matched host wildcards are passed to the callback in unicode form.
* **IPv6 literals:** Addresses are canonicalized (``[0:0:0:0:0:0:0:1]`` equals ``[::1]``).

Wildcard patterns and filters are applied to the normalized hostname, that is, the lowercase unicode form described above.

A request with a malformed ``Host`` header is answered with ``400 Bad Request``, but only if the application actually defines host rules. Applications without host rules are not affected.

If several routes could handle a request, they are considered in the following order:

#. Routes with a static host rule and a matching port.
#. Routes with a static host rule and no port.
#. Routes with a dynamic host rule, in order of registration.
#. Routes without a host rule.

Within each of these groups, static path rules are checked before dynamic path rules, as usual.

Behind a reverse proxy, the ``X-Forwarded-Host`` header is **not** used for routing unless the application explicitly opts in, because clients can send this header, too::

    app.config['router.trust_forwarded_host'] = True

Named routes with a host rule can be reversed with :meth:`Bottle.get_url`. Host wildcards are filled from the same keyword arguments as path wildcards, but escaped as DNS labels (IDNA encoded) instead of path segments. The result is a scheme-relative URL::

    @app.route('/reports/<id>', host='<tenant>.example.com', name='report')
    def report(tenant, id):
        ...

    app.get_url('report', tenant='münchen', id=5)
    # '//xn--mnchen-3ya.example.com/reports/5'


Explicit routing configuration
--------------------------------------------------------------------------------

Route decorator can also be directly called as method. This way provides flexibility in complex setups, allowing you to directly control, when and how routing configuration done.

Here is a basic example of explicit routing configuration for default bottle application::

    def setup_routing():
        bottle.route('/', 'GET', index)
        bottle.route('/edit', ['GET', 'POST'], edit)

In fact, any :class:`Bottle` instance routing can be configured same way::

    def setup_routing(app):
        app.route('/new', ['GET', 'POST'], form_new)
        app.route('/edit', ['GET', 'POST'], form_edit)

    app = Bottle()
    setup_routing(app)

