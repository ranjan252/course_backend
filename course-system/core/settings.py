"""
Course API Lambda entry point.

Single Lambda handles all 7 routes via API Gateway path-based routing.
API Gateway sends the full event; we dispatch based on resource path + method.
"""
import logging
from core.response import error, extract_user_id

# Import route handlers
from handlers.warmup import handle_warmup
from handlers.warmup_done import handle_warmup_done
from handlers.next_content import handle_next
from handlers.submit import handle_submit
from handlers.progress import handle_progress
from handlers.sathi import handle_sathi
from handlers.rescue import handle_rescue

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Route table: (resource_path, http_method) → handler function
ROUTES = {
    ("/course/warmup", "GET"): handle_warmup,
    ("/course/warmup-done", "POST"): handle_warmup_done,
    ("/course/next", "GET"): handle_next,
    ("/course/submit", "POST"): handle_submit,
    ("/course/progress", "GET"): handle_progress,
    ("/course/sathi", "POST"): handle_sathi,
    ("/course/rescue", "POST"): handle_rescue,
}


def lambda_handler(event, context):
    """
    Main Lambda handler. Routes based on API Gateway resource path.
    """
    # Extract routing info
    resource = event.get("resource", "")
    method = event.get("httpMethod", "")

    logger.info(f"Request: {method} {resource}")

    # Auth check — every route requires authenticated user
    user_id = extract_user_id(event)
    if not user_id:
        return error("Unauthorized — missing or invalid token", 401)

    # Inject user_id into event for handlers
    event["_user_id"] = user_id

    # Dispatch
    handler = ROUTES.get((resource, method))
    if not handler:
        return error(f"Route not found: {method} {resource}", 404)

    try:
        return handler(event)
    except Exception as e:
        logger.exception(f"Unhandled error in {method} {resource}: {e}")
        return error("Internal server error", 500)