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


Host routing
--------------------------------------------------------------------------------

Sometimes the same path has to be served by different callbacks depending on
the request host, e.g. for multi-tenant applications. Instead of inspecting
``request.headers['Host']`` inside your callbacks, you can bind routes to a
host rule via the ``host`` parameter::

    @app.route('/reports/<id>', host='<tenant>.example.com')
    def reports(tenant, id):
        return 'Report %s for tenant %s' % (id, tenant)

    @app.route('/reports/<id>')
    def reports_fallback(id):
        return 'Report %s' % id

The host rule supports the same wildcard syntax (including filters) as path
rules, but only the new ``<name>`` / ``<name:filter>`` syntax. A host wildcard
name must not be reused by a path wildcard of the same route; doing so raises
a :class:`RouteNameClashError` at registration time.

Host normalization
^^^^^^^^^^^^^^^^^^

To make matching predictable, request hosts and host rules are normalized
before they are compared:

* Host names are matched case-insensitively (``Example.COM`` equals
  ``example.com``).
* International domain names are converted to their IDNA/punycode form, so
  ``bücher.example`` and ``xn--bcher-kva.example`` are equivalent.
* IPv6 literals are compressed into their canonical form (``[2001:DB8::1]``
  equals ``[2001:db8:0:0::1]``).
* The default ports ``80`` (for ``http``) and ``443`` (for ``https``) are
  ignored, so a single rule never matches the same logical host twice.
  Explicit non-default ports are kept.

A syntactically invalid ``Host`` header results in ``400 Bad Request``.

Proxy headers
^^^^^^^^^^^^^

Only the WSGI ``HTTP_HOST`` variable is used by default. If your application
runs behind a trusted proxy that sets ``X-Forwarded-Host``, you have to opt in
explicitly before that header is trusted::

    app.config['router.trust_proxy_headers'] = True

When enabled, the left-most (original) host in ``X-Forwarded-Host`` is used.

Matching order
^^^^^^^^^^^^^^

If several rules match a request, the first match wins with the following
fixed priority (independent of dictionary order); within each group, the rule
registered first wins:

#. Static host, static path
#. Static host, dynamic path
#. Dynamic host, static path
#. Dynamic host, dynamic path
#. No host rule, static path
#. No host rule, dynamic path

Thus, host-specific rules always take precedence over host-independent ones,
but a host-independent rule still matches if no host-specific rule does.

Building URLs for host routes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Named routes with a host rule build network-path URLs (starting with ``//``)
when you pass the host wildcard values::

    app.get_url('reports', tenant='acme', id=1)
    # '//acme.example.com/reports/1'

Host wildcard values are IDNA encoded and percent-escaped for the host
component, while path wildcard values use path escaping (slashes are kept
within path values but encoded within host labels).


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

