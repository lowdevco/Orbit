"""Small fixed-window rate limiter on Django's cache. Keyed by user id, or by IP for anonymous visitors."""

import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render


def _ident(request):
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        return f"u{request.user.pk}"
    # REMOTE_ADDR, not X-Forwarded-For: the header is client-controlled unless a trusted proxy rewrites it.
    return f"ip{request.META.get('REMOTE_ADDR', '')}"


def hit(request, scope, limit, period=60):
    """Count one request; return True if it is over the limit."""
    window = int(time.time() // period)
    key = f"rl:{scope}:{_ident(request)}:{window}"
    cache.add(key, 0, period + 1)
    try:
        count = cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, period + 1)
        count = 1
    return count > limit


def too_many(request, period=60):
    if request.path.endswith(".json") or request.headers.get("Accept", "").startswith("application/json"):
        resp = JsonResponse({"error": "Too many requests. Slow down a little."}, status=429)
    else:
        resp = render(request, "429.html", status=429)
    resp["Retry-After"] = str(period)
    return resp


def ratelimit(scope, limit, period=60):
    """Decorator: at most `limit` requests per `period` seconds per user/IP for this view."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if hit(request, scope, limit, period):
                return too_many(request, period)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


class PostRateLimitMiddleware:
    """Blanket cap on state-changing requests so no endpoint can be hammered."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in ("GET", "HEAD", "OPTIONS") and hit(
            request, "post", settings.RATELIMIT_POST_PER_MINUTE
        ):
            return too_many(request)
        return self.get_response(request)
