"""
Consistent API response formatting.
Every handler returns through these helpers.
"""
import json
import logging
from config.settings import CORS_ORIGIN

logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": CORS_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
    "Content-Type": "application/json",
}


def success(body: dict, status_code: int = 200) -> dict:
    """Return success response."""
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body, default=str),
    }


def error(message: str, status_code: int = 400, details: dict = None) -> dict:
    """Return error response."""
    body = {"error": message}
    if details:
        body["details"] = details
    logger.warning(f"[{status_code}] {message}")
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body, default=str),
    }


def not_found(message: str = "Resource not found") -> dict:
    return error(message, 404)


def server_error(message: str = "Internal server error") -> dict:
    return error(message, 500)


def extract_user_id(event: dict) -> str | None:
    """
    Extract user_id from Cognito JWT claims.
    API Gateway passes these in requestContext.authorizer.claims.
    """
    try:
        claims = event["requestContext"]["authorizer"]["claims"]
        return claims.get("sub") or claims.get("cognito:username")
    except (KeyError, TypeError):
        return None


def extract_query_param(event: dict, param: str) -> str | None:
    """Extract a query string parameter."""
    params = event.get("queryStringParameters") or {}
    return params.get(param)


def extract_body(event: dict) -> dict:
    """Parse JSON body from POST request."""
    try:
        body = event.get("body", "{}")
        if isinstance(body, str):
            return json.loads(body)
        return body or {}
    except (json.JSONDecodeError, TypeError):
        return {}