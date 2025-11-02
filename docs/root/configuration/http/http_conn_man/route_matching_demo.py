#!/usr/bin/env python3
"""
Demonstration script showing how Envoy's router would match different paths
against various route configurations (prefix, exact, regex).

This script simulates the matching logic to help understand how routes work.
"""

import re
from typing import List, Dict, Tuple, Optional

class RouteMatch:
    """Represents a route match configuration"""
    
    def __init__(self, match_type: str, pattern: str, cluster: str):
        self.match_type = match_type  # 'prefix', 'exact', or 'regex'
        self.pattern = pattern
        self.cluster = cluster
        self.compiled_regex = None
        
        if match_type == 'regex':
            self.compiled_regex = re.compile(pattern)
    
    def matches(self, path: str) -> bool:
        """Check if the given path matches this route configuration"""
        # Remove query string and fragment (as Envoy does)
        sanitized_path = path.split('?')[0].split('#')[0]
        
        if self.match_type == 'prefix':
            return sanitized_path.startswith(self.pattern)
        elif self.match_type == 'exact':
            return sanitized_path == self.pattern
        elif self.match_type == 'regex':
            return self.compiled_regex.match(sanitized_path) is not None
        
        return False
    
    def __str__(self):
        return f"{self.match_type}='{self.pattern}' -> {self.cluster}"


class VirtualHost:
    """Represents a virtual host with multiple routes"""
    
    def __init__(self, name: str, domains: List[str]):
        self.name = name
        self.domains = domains
        self.routes: List[RouteMatch] = []
    
    def add_route(self, match_type: str, pattern: str, cluster: str):
        """Add a route to this virtual host"""
        self.routes.append(RouteMatch(match_type, pattern, cluster))
    
    def match_domain(self, domain: str) -> bool:
        """Check if domain matches this virtual host"""
        # Simple exact match (Envoy supports wildcards, but we simplify here)
        return domain in self.domains
    
    def route_request(self, path: str) -> Optional[str]:
        """
        Route a request path through this virtual host's routes.
        Returns the cluster name if a match is found, None otherwise.
        Routes are checked in order, first match wins.
        """
        for route in self.routes:
            if route.matches(path):
                return route.cluster
        return None


def demonstrate_routing():
    """Demonstrate how Envoy routes requests"""
    
    print("=" * 80)
    print("Envoy Router Path Matching Demonstration")
    print("=" * 80)
    print()
    
    # Create a virtual host with various route types
    vhost = VirtualHost("api_service", ["api.example.com"])
    
    # Add routes in order (order matters!)
    print("Configured Routes (checked in order):")
    print("-" * 80)
    
    # 1. Regex: Versioned API endpoints
    vhost.add_route('regex', r'^/api/v[0-9]+/.*', 'api_versioned_cluster')
    print("1. regex: ^/api/v[0-9]+/.* -> api_versioned_cluster")
    
    # 2. Regex: User detail with numeric ID
    vhost.add_route('regex', r'^/users/[0-9]+$', 'user_detail_cluster')
    print("2. regex: ^/users/[0-9]+$ -> user_detail_cluster")
    
    # 3. Prefix: All user endpoints (fallback)
    vhost.add_route('prefix', '/users', 'users_cluster')
    print("3. prefix: /users -> users_cluster")
    
    # 4. Exact: Health check endpoint
    vhost.add_route('exact', '/health', 'health_cluster')
    print("4. exact: /health -> health_cluster")
    
    # 5. Regex: Static assets with extensions
    vhost.add_route('regex', r'^/static/.*\.(jpg|jpeg|png|gif|css|js)$', 'static_cluster')
    print("5. regex: ^/static/.*\\.(jpg|jpeg|png|gif|css|js)$ -> static_cluster")
    
    # 6. Prefix: Admin (with imaginary header check, simplified here)
    vhost.add_route('prefix', '/admin', 'admin_cluster')
    print("6. prefix: /admin -> admin_cluster")
    
    # 7. Catch-all prefix
    vhost.add_route('prefix', '/', 'default_cluster')
    print("7. prefix: / -> default_cluster (catch-all)")
    
    print()
    print("=" * 80)
    print("Request Routing Examples:")
    print("=" * 80)
    
    # Test cases
    test_cases = [
        # (path, description)
        ("/api/v1/users", "Versioned API endpoint"),
        ("/api/v2/products", "Versioned API endpoint (v2)"),
        ("/users/123", "User detail with numeric ID"),
        ("/users/abc", "User with non-numeric ID"),
        ("/users", "Users list endpoint"),
        ("/users/list", "Users sub-path"),
        ("/health", "Health check endpoint"),
        ("/health/status", "Health sub-path (not exact match)"),
        ("/static/logo.png", "Static image file"),
        ("/static/script.js", "Static JavaScript file"),
        ("/static/readme.txt", "Static file (no matching extension)"),
        ("/admin/dashboard", "Admin endpoint"),
        ("/api/users", "API without version (no match for regex)"),
        ("/other/endpoint", "Unmatched path (catch-all)"),
        ("/users/123?filter=active", "User with query string"),
        ("/health#section", "Health with fragment"),
    ]
    
    for path, description in test_cases:
        cluster = vhost.route_request(path)
        print(f"\nPath: {path}")
        print(f"  Description: {description}")
        print(f"  Routed to: {cluster}")
        
        # Show which route matched
        for i, route in enumerate(vhost.routes, 1):
            if route.matches(path):
                print(f"  Matched route #{i}: {route.match_type}='{route.pattern}'")
                break
    
    print()
    print("=" * 80)
    print("Key Observations:")
    print("=" * 80)
    print("1. Routes are evaluated IN ORDER - first match wins")
    print("2. More specific routes should come before general routes")
    print("3. Regex patterns must match the entire path (use ^ and $ anchors)")
    print("4. Query strings and fragments are removed before matching")
    print("5. Prefix matches are simple string prefix checks")
    print("6. Exact matches require the complete path to match")
    print()
    
    # Demonstrate the importance of ordering
    print("=" * 80)
    print("Ordering Example - Why Order Matters:")
    print("=" * 80)
    print()
    print("If routes were in reverse order (general before specific):")
    print("  - prefix: / would match EVERYTHING first")
    print("  - Other routes would never be checked")
    print("  - Result: All traffic goes to default_cluster")
    print()
    print("Correct ordering (specific before general):")
    print("  - Specific routes (regex, exact) are checked first")
    print("  - General routes (prefix) are checked later")
    print("  - Catch-all route (prefix: /) is checked last")
    print("  - Result: Traffic is properly routed based on patterns")
    print()


def demonstrate_regex_patterns():
    """Demonstrate various regex pattern examples"""
    
    print("=" * 80)
    print("Common Regex Patterns for Envoy Routing")
    print("=" * 80)
    print()
    
    patterns = [
        (r'^/api/v[0-9]+/.*', "Versioned API paths", 
         ["/api/v1/users", "/api/v2/products"], 
         ["/api/users", "/api/vX/test"]),
        
        (r'^/users/[0-9]+$', "User ID (numeric only)",
         ["/users/123", "/users/999"],
         ["/users/abc", "/users/123/profile"]),
        
        (r'^/archive/[0-9]{4}-[0-9]{2}-[0-9]{2}$', "Date-based paths (YYYY-MM-DD)",
         ["/archive/2024-01-15", "/archive/2023-12-31"],
         ["/archive/2024-1-15", "/archive/24-01-15"]),
        
        (r'^/resource/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 
         "UUID paths",
         ["/resource/550e8400-e29b-41d4-a716-446655440000"],
         ["/resource/invalid-uuid", "/resource/123"]),
        
        (r'^/[a-z]{2}/.*', "Language-specific paths (2-letter codes)",
         ["/en/home", "/es/about", "/fr/contact"],
         ["/eng/home", "/e/home"]),
        
        (r'^/api/.*\.(json|xml)$', "API endpoints with format extension",
         ["/api/users.json", "/api/products.xml"],
         ["/api/users", "/api/users.txt"]),
    ]
    
    for pattern, description, matches, non_matches in patterns:
        print(f"Pattern: {pattern}")
        print(f"Description: {description}")
        print(f"  Matches:")
        for path in matches:
            print(f"    ✓ {path}")
        print(f"  Does NOT match:")
        for path in non_matches:
            print(f"    ✗ {path}")
        print()


if __name__ == "__main__":
    demonstrate_routing()
    print()
    demonstrate_regex_patterns()
