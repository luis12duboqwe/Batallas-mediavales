from collections import Counter

from app.main import app
from app.routers.chat import websocket_chat


MVP_HTTP_CONTRACT = {
    ("GET", "/health"),
    ("POST", "/auth/register"),
    ("POST", "/auth/token"),
    ("POST", "/auth/verify-email"),
    ("POST", "/auth/forgot-password"),
    ("POST", "/auth/reset-password"),
    ("GET", "/auth/me"),
    ("PATCH", "/auth/me"),
    ("GET", "/worlds/"),
    ("GET", "/worlds/active"),
    ("POST", "/worlds/active"),
    ("POST", "/worlds/{world_id}/join"),
    ("GET", "/city/"),
    ("GET", "/city/{city_id}/status"),
    ("GET", "/building/available"),
    ("POST", "/building/upgrade"),
    ("DELETE", "/building/queue/{queue_id}"),
    ("POST", "/troop/train"),
    ("POST", "/troop/research"),
    ("DELETE", "/troop/queue/{queue_id}"),
    ("GET", "/movement/"),
    ("POST", "/movement/"),
    ("GET", "/map/tiles"),
    ("GET", "/map/oasis/{oasis_id}"),
    ("GET", "/report/"),
    ("GET", "/ranking/players"),
    ("GET", "/ranking/alliances"),
    ("GET", "/ranking/search"),
    ("GET", "/message/inbox"),
    ("GET", "/message/sent"),
    ("POST", "/message/send"),
    ("GET", "/message/{message_id}"),
    ("DELETE", "/message/{message_id}"),
    ("GET", "/market/offers"),
    ("POST", "/market/offers"),
    ("POST", "/market/offers/{offer_id}/accept"),
    ("DELETE", "/market/offers/{offer_id}"),
    ("POST", "/market/transport"),
    ("POST", "/market/npc_trade"),
    ("GET", "/alliance/"),
    ("GET", "/alliance/invitations"),
    ("POST", "/alliance/invitations/{invitation_id}/accept"),
    ("POST", "/alliance/{alliance_id}/invite"),
    ("POST", "/alliance/{alliance_id}/mass-message"),
    ("GET", "/alliance/{alliance_id}/diplomacy"),
    ("POST", "/alliance/{alliance_id}/diplomacy"),
    ("POST", "/alliance/{alliance_id}/diplomacy/{diplomacy_id}/accept"),
    ("DELETE", "/alliance/{alliance_id}/diplomacy/{diplomacy_id}"),
    ("GET", "/tutorial/status"),
    ("POST", "/tutorial/advance"),
    ("GET", "/queue/status"),
    ("GET", "/protection/status"),
    ("PATCH", "/admin/city/{city_id}/resources"),
    ("PATCH", "/admin/city/{city_id}/building/{building_type}"),
    ("PATCH", "/admin/city/{city_id}/troops"),
    ("POST", "/admin/city/create"),
    ("PATCH", "/admin/city/{city_id}/coordinates"),
    ("DELETE", "/admin/user/{user_id}"),
    ("DELETE", "/admin/city/{city_id}"),
    ("GET", "/anticheat/flags"),
    ("PATCH", "/anticheat/resolve/{flag_id}"),
}

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def _http_pairs():
    """Read the public OpenAPI contract instead of framework route classes."""

    pairs = []
    for path, operations in app.openapi().get("paths", {}).items():
        for operation in operations:
            if operation.lower() in _HTTP_METHODS and operation.lower() not in {"head", "options"}:
                pairs.append((operation.upper(), path))
    return pairs


def _walk_routes(routes, seen=None):
    """Recursively traverse Starlette/FastAPI route containers.

    Framework releases have changed which route path attributes are exposed,
    so traversal is used only for implementation identity and duplicate HTTP
    detection. The HTTP contract itself is read from OpenAPI above.
    """

    if seen is None:
        seen = set()
    for route in routes:
        identity = id(route)
        if identity in seen:
            continue
        seen.add(identity)
        yield route

        nested = getattr(route, "routes", None)
        if nested:
            yield from _walk_routes(nested, seen)

        router = getattr(route, "router", None)
        router_routes = getattr(router, "routes", None)
        if router_routes:
            yield from _walk_routes(router_routes, seen)


def _raw_http_pairs():
    pairs = []
    for route in _walk_routes(app.routes):
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        for method in methods:
            if method not in {"HEAD", "OPTIONS"}:
                pairs.append((method, path))
    return pairs


def test_mvp_http_contract_is_registered():
    registered = set(_http_pairs())
    missing = sorted(MVP_HTTP_CONTRACT - registered)
    assert missing == [], f"Missing MVP API routes: {missing}"


def test_routes_do_not_have_duplicate_method_path_pairs():
    counts = Counter(_raw_http_pairs())
    duplicates = sorted(pair for pair, count in counts.items() if count > 1)
    assert duplicates == [], f"Ambiguous duplicate API routes: {duplicates}"


def test_queue_router_is_not_double_prefixed():
    registered = set(_http_pairs())
    assert ("GET", "/queue/status") in registered
    assert all(not path.startswith("/queue/queue/") for _, path in registered)


def test_global_chat_websocket_is_registered():
    """Verify the chat endpoint is mounted without depending on route internals.

    Starlette 1.x no longer exposes ``path`` consistently on websocket route
    wrappers. The endpoint callable remains stable and proves that the included
    chat router reached the application routing tree.
    """

    endpoints = {
        getattr(route, "endpoint", None)
        for route in _walk_routes(app.routes)
    }
    assert websocket_chat in endpoints
