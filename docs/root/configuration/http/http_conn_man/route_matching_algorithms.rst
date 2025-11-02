.. _config_http_conn_man_route_matching_algorithms:

Route Matching Algorithms
==========================

This document explains how Envoy's router matches incoming HTTP requests against configured route entries,
with detailed coverage of different path matching types including regex-based matching.

Overview
--------

Envoy's router uses a two-stage matching process:

1. **Virtual Host Matching**: The HTTP request's ``host`` or ``:authority`` header is matched against
   configured virtual hosts.
2. **Route Matching**: Within the matched virtual host, route entries are evaluated to find the first
   matching route.

Path Matching Types
-------------------

Envoy supports several path matching types, each implemented as a separate route entry class:

Prefix Matching
~~~~~~~~~~~~~~~

**Implementation**: ``PrefixRouteEntryImpl``

Matches if the request path starts with the configured prefix. This is a simple string prefix comparison.

**Matching Algorithm**:

.. code-block:: c++

   bool matches = path_matcher_->match(sanitizePathBeforePathMatching(headers.getPathValue()));

The match is performed by:

1. Extracting the path from the request headers
2. Sanitizing the path (removing query parameters and fragments)
3. Checking if the sanitized path starts with the configured prefix

**Example Configuration**:

.. code-block:: yaml

   routes:
     - match:
         prefix: "/api"
       route:
         cluster: api_cluster

**Matching Behavior**:

- Request: ``/api/v1/users`` → **Matches** (starts with ``/api``)
- Request: ``/api`` → **Matches** (exact match with prefix)
- Request: ``/v1/api`` → **Does not match** (does not start with ``/api``)

Exact Path Matching
~~~~~~~~~~~~~~~~~~~

**Implementation**: ``PathRouteEntryImpl``

Matches only if the request path exactly equals the configured path.

**Matching Algorithm**:

.. code-block:: c++

   bool matches = path_matcher_->match(sanitizePathBeforePathMatching(headers.getPathValue()));

**Example Configuration**:

.. code-block:: yaml

   routes:
     - match:
         path: "/api/v1/users"
       route:
         cluster: users_cluster

**Matching Behavior**:

- Request: ``/api/v1/users`` → **Matches** (exact match)
- Request: ``/api/v1/users/123`` → **Does not match** (not exact)
- Request: ``/api/v1/users?filter=active`` → **Matches** (query string is ignored during matching)

Regex Matching
~~~~~~~~~~~~~~

**Implementation**: ``RegexRouteEntryImpl``

Matches if the request path matches a configured regular expression pattern. This is the most flexible
but also the most computationally expensive matching type.

**Matching Algorithm**:

.. code-block:: c++

   if (RouteEntryImplBase::matchRoute(headers, stream_info, random_value)) {
     if (path_matcher_->match(sanitizePathBeforePathMatching(headers.getPathValue()))) {
       return clusterEntry(headers, stream_info, random_value);
     }
   }

The matching process:

1. First checks if the route matches based on headers, runtime, and other criteria (``matchRoute``)
2. Extracts and sanitizes the path from request headers
3. Applies the regex pattern to the sanitized path
4. Returns the route if both checks pass

**Path Sanitization**: Before regex matching, the path undergoes sanitization which removes query
parameters and fragments using ``Http::PathUtil::removeQueryAndFragment()``.

**Example Configuration**:

.. code-block:: yaml

   routes:
     - match:
         safe_regex:
           regex: "^/api/v[0-9]+/.*"
       route:
         cluster: api_cluster

**Matching Behavior**:

- Request: ``/api/v1/users`` → **Matches** (matches pattern)
- Request: ``/api/v2/products`` → **Matches** (matches pattern)
- Request: ``/api/users`` → **Does not match** (missing version number)
- Request: ``/api/v1/users?filter=active`` → **Matches** (query string removed before matching)

**Performance Considerations**:

Regex matching is more expensive than prefix or exact matching. The regex engine must evaluate the
entire pattern against each request. For high-performance scenarios, consider:

- Using simpler match types (prefix/exact) when possible
- Placing frequently matched routes earlier in the route list
- Using optimized regex patterns (avoid backtracking)

Path-Separated Prefix Matching
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Implementation**: ``PathSeparatedPrefixRouteEntryImpl``

Similar to prefix matching, but respects path segment boundaries (``/`` separators). This prevents
partial matches within path segments.

**Example**:

- Configured prefix: ``/api``
- Request: ``/api/users`` → **Matches**
- Request: ``/api-v2/users`` → **Does not match** (would match with regular prefix)

Route Matching Order
--------------------

Within a virtual host, routes are evaluated **in the order they are configured**. The first route
that matches all criteria (path, headers, query parameters, etc.) is selected.

**Important**: This means that more specific routes should be placed before more general routes.

**Example**:

.. code-block:: yaml

   routes:
     # Specific regex route first
     - match:
         safe_regex:
           regex: "^/api/v1/users/[0-9]+$"
       route:
         cluster: user_detail_cluster
     
     # General prefix route second
     - match:
         prefix: "/api"
       route:
         cluster: api_cluster

In this example, a request to ``/api/v1/users/123`` matches the first route (user_detail_cluster),
while ``/api/v1/products`` matches the second route (api_cluster).

Combining Path Matching with Other Criteria
--------------------------------------------

Path matching can be combined with additional matching criteria:

Header Matching
~~~~~~~~~~~~~~~

.. code-block:: yaml

   routes:
     - match:
         safe_regex:
           regex: "^/api/.*"
         headers:
           - name: "x-api-version"
             safe_regex_match:
               regex: "v[0-9]+"
       route:
         cluster: versioned_api_cluster

Query Parameter Matching
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   routes:
     - match:
         prefix: "/search"
         query_parameters:
           - name: "debug"
             string_match:
               exact: "true"
       route:
         cluster: debug_cluster

Runtime Fraction Matching
~~~~~~~~~~~~~~~~~~~~~~~~~~

Routes can also use runtime-based percentage matching for A/B testing:

.. code-block:: yaml

   routes:
     - match:
         prefix: "/api"
         runtime_fraction:
           default_value:
             numerator: 10
             denominator: HUNDRED
           runtime_key: "routing.api.experiment"
       route:
         cluster: experimental_cluster

Implementation Details
----------------------

Internal Classes
~~~~~~~~~~~~~~~~

The route matching implementation uses the following key classes:

- ``RouteEntryImplBase``: Base class for all route entry types, contains common matching logic
- ``PrefixRouteEntryImpl``: Implements prefix-based path matching
- ``PathRouteEntryImpl``: Implements exact path matching
- ``RegexRouteEntryImpl``: Implements regex-based path matching
- ``PathMatcher``: Wrapper around ``StringMatcher`` that handles path-specific logic
- ``StringMatcherImpl``: Generic string matching supporting multiple patterns (exact, prefix, regex, etc.)

PathMatcher Behavior
~~~~~~~~~~~~~~~~~~~~

The ``PathMatcher`` class (defined in ``source/common/common/matchers.h``) wraps ``StringMatcherImpl``
and provides path-specific functionality:

.. code-block:: c++

   bool PathMatcher::match(const absl::string_view path) const {
     return matcher_.match(Http::PathUtil::removeQueryAndFragment(path));
   }

This ensures consistent handling of query parameters and fragments across all matching types.

Regex Pattern Compilation
~~~~~~~~~~~~~~~~~~~~~~~~~~

Regex patterns are compiled once during configuration loading using Google's RE2 library through
Envoy's ``Regex::Utility::parseRegex()`` function. This compilation happens in the
``RegexStringMatcher`` constructor:

.. code-block:: c++

   RegexStringMatcher(const RegexMatcherType& safe_regex,
                      Server::Configuration::CommonFactoryContext& context)
       : regex_(THROW_OR_RETURN_VALUE(Regex::Utility::parseRegex(safe_regex, context.regexEngine()),
                                      Regex::CompiledMatcherPtr)) {}

The compiled pattern is then reused for all subsequent matches, avoiding repeated compilation overhead.

Best Practices
--------------

1. **Prefer Simple Matches**: Use prefix or exact matching when possible for better performance
2. **Order Routes Carefully**: Place specific routes before general routes
3. **Optimize Regex Patterns**: Use anchors (``^`` and ``$``) and avoid complex backtracking patterns
4. **Test Route Configuration**: Use the :ref:`route table check tool <config_operations_tools_route_table_check_tool>`
   to validate your configuration
5. **Monitor Performance**: Watch for high CPU usage from regex matching in production

Interactive Demo
~~~~~~~~~~~~~~~~

A Python demonstration script is available at
``docs/root/configuration/http/http_conn_man/route_matching_demo.py`` that simulates
how Envoy routes requests. Run it to see examples of different matching types in action:

.. code-block:: bash

   python3 docs/root/configuration/http/http_conn_man/route_matching_demo.py

The demo shows:

- How routes are evaluated in order
- Which route matches different request paths
- The importance of route ordering
- Common regex patterns for typical use cases

Security Considerations
-----------------------

Regex Denial of Service (ReDoS)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Poorly crafted regex patterns can cause exponential backtracking, leading to high CPU usage.
Envoy uses Google's RE2 library, which guarantees linear time matching and prevents catastrophic
backtracking.

However, you should still:

- Test regex patterns with various inputs
- Use simple patterns when possible
- Monitor regex matching performance in production

Case Sensitivity
~~~~~~~~~~~~~~~~

By default, path matching in Envoy is case-sensitive. You can configure case-insensitive matching:

.. code-block:: yaml

   routes:
     - match:
         prefix: "/API"
         case_sensitive: false
       route:
         cluster: api_cluster

Related Documentation
---------------------

- :ref:`Route matching overview <config_http_conn_man_route_table_route_matching>`
- :ref:`Route configuration <envoy_v3_api_msg_config.route.v3.Route>`
- :ref:`RouteMatch API <envoy_v3_api_msg_config.route.v3.RouteMatch>`
- :ref:`Router filter <config_http_filters_router>`

Example Configurations
~~~~~~~~~~~~~~~~~~~~~~

A complete example configuration file demonstrating various path matching types is available at
``docs/root/configuration/http/http_conn_man/route_matching_examples.yaml``. This file includes:

- Regex matching for versioned API endpoints
- Prefix and exact path matching
- Case-insensitive matching
- Query parameter matching combined with regex
- Complex regex patterns (dates, UUIDs, language codes)
- Header-based matching

You can use this as a reference when configuring your own routes.

