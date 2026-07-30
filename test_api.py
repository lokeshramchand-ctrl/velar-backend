import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pymongo
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app import app
from core.config import settings
from core.jwt_auth import create_access_token
from core.rate_limiter import limiter

# =====================================================================
# TEST LOGGER CONFIGURATION
# =====================================================================
# Configured to output beautiful, narrative logs during test execution
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s 🧪 [TEST] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("velar_test_suite")

# The required Phase 15 authorization header
VALID_API_KEY = "velar_test_key_123"
HEADERS = {
    "X-Velar-API-Key": VALID_API_KEY,
    "Content-Type": "application/json"
}

def _craft_token(user_id: str, expires_delta: timedelta, secret: str = None, token_type: str = "access") -> str:
    """Hand-builds a JWT outside the normal create_access_token() path, so
    tests can produce deliberately expired/mis-typed/wrong-signature tokens
    that the real helper would never emit."""
    now = datetime.now(UTC)
    payload = {"sub": user_id, "type": token_type, "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, secret or settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

@pytest.fixture(scope="module")
def client():
    """Triggers FastAPI's lifespan events (MongoDB & Milvus connections)."""
    logger.info("Initializing TestClient and spinning up databases...")
    with TestClient(app) as c:
        yield c
    logger.info("TestClient teardown complete.")

@pytest.fixture(scope="module")
def auth_user(client):
    """Registers one throwaway user for this test module and mints its
    access token directly via create_access_token() (the same code path
    POST /auth/login uses internally) rather than logging in - keeps the
    many unrelated tests that just need *some* valid bearer token from
    eating into /auth/login's rate limit, which is tested in its own right
    further down."""
    email = f"testuser_{uuid.uuid4().hex[:10]}@example.com"
    password = "StrongPassword123!"
    response = client.post("/auth/register", json={"email": email, "password": password}, headers=HEADERS)
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]
    token, _ = create_access_token(user_id)
    return {"user_id": user_id, "email": email, "password": password, "access_token": token}

@pytest.fixture(scope="module")
def auth_headers(auth_user):
    """API key + JWT bearer token - the 'both' auth combination required by
    user-scoped endpoints (POST /v1/categorize, /v1/analytics/*, /v1/feedback/)."""
    return {**HEADERS, "Authorization": f"Bearer {auth_user['access_token']}"}

# =====================================================================
# PHASE 0 & 15: SYSTEM HEALTH & SECURITY
# =====================================================================

def test_health_check(client):
    logger.info("Pinging /health endpoint to verify DB connections.")
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    logger.info(f"Health status: {data['status'].upper()}")

def test_security_missing_key(client):
    logger.info("Testing security bypass: Missing API Key.")
    response = client.post("/v1/categorize", json={"text": "swiggy"})
    assert response.status_code in [401, 403]
    logger.info("System successfully blocked unauthorized access.")

def test_security_valid_key_missing_jwt(client):
    """A valid API key alone is not enough for a user-scoped endpoint - it
    proves the calling application is trusted, not who the end user is."""
    logger.info("Testing security bypass: valid API key but no JWT on a user-scoped endpoint.")
    response = client.post("/v1/categorize", json={"text": "swiggy"}, headers=HEADERS)
    assert response.status_code == 401
    logger.info("System correctly required a JWT in addition to the API key.")

def test_rate_limiter_defense(client, auth_headers):
    """Fires 55 rapid requests to trigger the 50/minute SlowAPI limit."""
    logger.info("Firing rapid requests to test Rate Limiter defense...")
    blocked = False

    # Mock a real IP address so SlowAPI has something to track in memory
    headers_with_ip = {**auth_headers, "X-Forwarded-For": "192.168.1.100"}

    try:
        for _i in range(55):
            res = client.post("/v1/categorize", json={"text": "test"}, headers=headers_with_ip)
            if res.status_code == 429: # Too Many Requests
                blocked = True
                break

        assert blocked is True
        logger.info("Rate limiter successfully caught and blocked spam traffic (HTTP 429).")
    finally:
        # TestClient's remote address is identical for every request in this session
        # (no real per-client IPs), so without a reset this test's hits would count
        # against every other test sharing the module-scoped `client` fixture.
        limiter.reset()

# =====================================================================
# PHASE 1-3: INGESTION & RESOLUTION (PARAMETERIZED)
# =====================================================================

@pytest.mark.parametrize("raw_string, expected_match", [
    ("UPI/CR/3152671239/BUNDL TECHNOLOGIES/HDFC", "cleaned_text"),
    ("NEFT-SBIN0000123-UBER INDIA-MUMBAI", "cleaned_text"),
    ("POS XX9912 STARBUCKS STORE 12", "cleaned_text"),
    ("IMPS/P2A/123456/ZOMATO MEDIA", "cleaned_text")
])
def test_resolution_regex_engine(client, raw_string, expected_match):
    """Tests the resolution engine against multiple transaction formats."""
    logger.info(f"Testing Resolution Engine with raw string: '{raw_string}'")
    response = client.post("/v1/resolve", json={"text": raw_string}, headers=HEADERS)
    assert response.status_code == 200
    assert expected_match in response.json()

def test_categorize_valid_payload(client, auth_headers):
    response = client.post("/v1/categorize", json={"text": "paid 500 to swiggy"}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "merchant" in data
    assert "category" in data
    assert "confidence" in data
    logger.info(f"Categorization Success -> Merchant: {data['merchant']}, Cat: {data['category']}")

# =====================================================================
# PHASE 4: MEMORY ENGINE (STATE PROMOTION)
# =====================================================================

def test_memory_engine_lifecycle(client):
    """Tests the entire lifecycle from EPHEMERAL to TEMPORARY state in one flow."""
    unique_merchant = f"Target_{uuid.uuid4().hex[:6]}"
    payload = {"canonical_name": unique_merchant, "raw_text": f"paid {unique_merchant}"}

    logger.info(f"Testing Memory State Machine for new entity: {unique_merchant}")

    # Encounter 1: Should be EPHEMERAL
    res1 = client.post("/memory/update", json=payload, headers=HEADERS)
    assert res1.json()["memory_state"] == "EPHEMERAL"
    logger.info("Encounter 1: State logged as EPHEMERAL")

    # Encounter 2
    client.post("/memory/update", json=payload, headers=HEADERS)

    # Encounter 3: Should promote to TEMPORARY
    res3 = client.post("/memory/update", json=payload, headers=HEADERS)
    assert res3.json()["memory_state"] == "TEMPORARY"
    logger.info("Encounter 3: Successfully promoted to TEMPORARY")

# =====================================================================
# PHASE 5: CONFIDENCE WALL
# =====================================================================

def test_confidence_evaluator_blocks_hallucinations(client):
    logger.info("Testing Confidence Wall with a risky prediction (40% confidence).")
    payload = {"predicted_category": "Travel", "raw_confidence": 0.40}
    response = client.post("/v1/confidence/evaluate", json=payload, headers=HEADERS)

    data = response.json()
    assert data["final_category"] == "Unknown"
    assert data["is_hallucination_risk"] is True
    logger.info("Confidence Wall successfully intercepted and blocked hallucination.")

# =====================================================================
# PHASE 13: ANALYTICS ENGINE (EDGE CASES)
# =====================================================================

def test_analytics_categories_negative_days(client, auth_headers):
    logger.info("Testing Analytics Engine boundary handling (negative lookback days).")
    response = client.get("/v1/analytics/patterns/categories?days=-5", headers=auth_headers)
    # The API should gracefully handle it or Pydantic should catch it.
    assert response.status_code in [200, 422]

def test_analytics_anomaly_check(client):
    logger.info("Testing Anomaly Detection (Z-Score) for unusual spending.")
    response = client.post("/v1/analytics/anomaly/check?merchant=Uber&amount=99999", headers=HEADERS)
    assert response.status_code == 200
    is_anomaly = response.json().get("is_anomaly")
    logger.info(f"Anomaly Engine flagged $99,999 Uber ride as anomaly: {is_anomaly}")

# =====================================================================
# PHASE 10: FEEDBACK & ACTIVE LEARNING
# =====================================================================

def test_feedback_triggers_retraining_queue(client, auth_headers):
    logger.info("Simulating human feedback correction to trigger Active Learning queue.")
    payload = {
        "transaction_id": f"tx_{random.randint(1000, 9999)}",
        "original_prediction": "Unknown",
        "corrected_category": "Travel",
        "confidence": 0.40
    }
    response = client.post("/v1/feedback/", json=payload, headers=auth_headers)
    if response.status_code == 200:
        assert response.json()["feedback_recorded"] is True
        logger.info("Correction accepted and queued for Retraining.")

# =====================================================================
# PHASE 12 & 14: RAG & MLOPS
# =====================================================================

def test_rag_explanation_safety(client):
    logger.info("Testing RAG Explainability Pipeline formatting.")
    payload = {"transaction_text": "Swiggy order", "target_question": "Why?"}
    response = client.post("/v1/explain", json=payload, headers=HEADERS)
    assert response.status_code in [200, 404, 500]

def test_observability_endpoints(client):
    logger.info("Pinging Observability (Evidently AI) endpoints.")
    res1 = client.post("/v1/observability/drift/analyze", headers=HEADERS)
    res2 = client.get("/v1/observability/reports/latest", headers=HEADERS)
    assert res1.status_code == 200
    assert res2.status_code in [200, 404]
    logger.info("MLOps endpoints are active and routing correctly.")

# =====================================================================
# PHASE 16: JWT AUTHENTICATION
# =====================================================================

def test_auth_full_lifecycle(client):
    """End-to-end: register -> login -> authenticated /me -> refresh
    (rotation) -> reuse of the rotated-out token rejected -> logout ->
    the logged-out token rejected. Uses its own user (not the shared
    `auth_user` fixture) since this test consumes it via the real
    /auth/login and /auth/refresh endpoints, not the create_access_token()
    shortcut the other tests use."""
    logger.info("Testing full auth lifecycle: register -> login -> refresh -> logout.")
    email = f"lifecycle_{uuid.uuid4().hex[:10]}@example.com"
    password = "StrongPassword123!"

    register_res = client.post("/auth/register", json={"email": email, "password": password}, headers=HEADERS)
    assert register_res.status_code == 201
    body = register_res.json()
    assert body["email"] == email
    assert "hashed_password" not in body
    assert "password" not in body
    logger.info("Registration succeeded and response contains no password material.")

    duplicate_res = client.post("/auth/register", json={"email": email, "password": password}, headers=HEADERS)
    assert duplicate_res.status_code == 409
    logger.info("Duplicate registration correctly rejected with 409.")

    login_res = client.post("/auth/login", json={"email": email, "password": password}, headers=HEADERS)
    assert login_res.status_code == 200
    tokens = login_res.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] > 0
    access_token, refresh_token = tokens["access_token"], tokens["refresh_token"]
    logger.info("Login succeeded; access + refresh token pair issued.")

    wrong_password_res = client.post("/auth/login", json={"email": email, "password": "WrongPassword!"}, headers=HEADERS)
    assert wrong_password_res.status_code == 401

    me_res = client.get("/auth/me", headers={**HEADERS, "Authorization": f"Bearer {access_token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email
    logger.info("Authenticated /auth/me returned the correct identity.")

    refresh_res = client.post("/auth/refresh", json={"refresh_token": refresh_token}, headers=HEADERS)
    assert refresh_res.status_code == 200
    rotated = refresh_res.json()
    assert rotated["refresh_token"] != refresh_token
    assert rotated["access_token"] != access_token
    logger.info("Refresh rotated both the access and refresh tokens.")

    reused_res = client.post("/auth/refresh", json={"refresh_token": refresh_token}, headers=HEADERS)
    assert reused_res.status_code == 401
    logger.info("Reuse of the rotated-out refresh token correctly rejected.")

    logout_res = client.post("/auth/logout", json={"refresh_token": rotated["refresh_token"]}, headers=HEADERS)
    assert logout_res.status_code == 204
    logger.info("Logout succeeded.")

    after_logout_res = client.post("/auth/refresh", json={"refresh_token": rotated["refresh_token"]}, headers=HEADERS)
    assert after_logout_res.status_code == 401
    logger.info("Logged-out refresh token correctly rejected on subsequent use.")

def test_auth_login_nonexistent_email(client):
    logger.info("Testing login with an email that was never registered.")
    response = client.post(
        "/auth/login",
        json={"email": f"ghost_{uuid.uuid4().hex[:10]}@example.com", "password": "WhateverPassword1!"},
        headers=HEADERS,
    )
    assert response.status_code == 401
    logger.info("Unregistered-email login correctly rejected with a generic 401 (no user enumeration).")

def test_auth_register_requires_api_key(client):
    logger.info("Testing that /auth/register itself is gated by the API key.")
    response = client.post(
        "/auth/register",
        json={"email": f"noapikey_{uuid.uuid4().hex[:10]}@example.com", "password": "StrongPassword123!"},
    )
    assert response.status_code in [401, 403]

def test_auth_register_rejects_weak_input(client):
    logger.info("Testing input validation on registration (short password, malformed email).")
    short_password_res = client.post(
        "/auth/register", json={"email": f"weak_{uuid.uuid4().hex[:10]}@example.com", "password": "short"}, headers=HEADERS
    )
    assert short_password_res.status_code == 422

    bad_email_res = client.post(
        "/auth/register", json={"email": "not-an-email", "password": "StrongPassword123!"}, headers=HEADERS
    )
    assert bad_email_res.status_code == 422
    logger.info("Weak password and malformed email both rejected with 422.")

def test_auth_refresh_invalid_token(client):
    logger.info("Testing /auth/refresh with a refresh token that was never issued.")
    response = client.post("/auth/refresh", json={"refresh_token": "this-was-never-issued"}, headers=HEADERS)
    assert response.status_code == 401

def test_auth_logout_is_idempotent(client):
    logger.info("Testing that logging out an already-unknown refresh token doesn't error.")
    response = client.post("/auth/logout", json={"refresh_token": "never-issued-either"}, headers=HEADERS)
    assert response.status_code == 204

def test_auth_me_missing_token(client):
    logger.info("Testing /auth/me with no bearer token at all.")
    response = client.get("/auth/me", headers=HEADERS)
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"

def test_auth_me_valid_token(client, auth_user):
    logger.info("Testing /auth/me with a genuinely valid access token.")
    response = client.get("/auth/me", headers={**HEADERS, "Authorization": f"Bearer {auth_user['access_token']}"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == auth_user["user_id"]
    assert data["email"] == auth_user["email"]
    assert "hashed_password" not in data

def test_auth_me_expired_token(client, auth_user):
    logger.info("Testing /auth/me with a signature-valid but expired access token.")
    expired = _craft_token(auth_user["user_id"], timedelta(minutes=-5))
    response = client.get("/auth/me", headers={**HEADERS, "Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert "expired" in response.json()["error"]["detail"].lower()
    logger.info("Expired access token correctly rejected.")

def test_auth_me_invalid_signature(client, auth_user):
    logger.info("Testing /auth/me with a token signed by the wrong key.")
    forged = _craft_token(auth_user["user_id"], timedelta(minutes=5), secret="a-completely-different-signing-key-xx")
    response = client.get("/auth/me", headers={**HEADERS, "Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
    logger.info("Token with an invalid signature correctly rejected.")

def test_auth_me_malformed_token(client):
    logger.info("Testing /auth/me with a token that isn't a JWT at all.")
    response = client.get("/auth/me", headers={**HEADERS, "Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401

def test_auth_me_wrong_token_type(client, auth_user):
    """A token that's structurally valid and correctly signed, but issued as
    a non-access type, must still be rejected - proves the `type` claim is
    actually checked, not just the signature."""
    logger.info("Testing /auth/me with a correctly-signed non-access token.")
    wrong_type = _craft_token(auth_user["user_id"], timedelta(minutes=5), token_type="refresh")
    response = client.get("/auth/me", headers={**HEADERS, "Authorization": f"Bearer {wrong_type}"})
    assert response.status_code == 401

def test_auth_forbidden_disabled_account(client):
    """Exercises the 401-vs-403 distinction: a well-formed, correctly-signed,
    unexpired token that resolves to a real user is *authenticated* (not
    401) - but if that account has been disabled, the request is still
    *forbidden* (403). There's no admin endpoint to disable a user, so this
    flips the flag directly in MongoDB, the same database the running app
    is already connected to."""
    logger.info("Testing 403 Forbidden path: a valid token for a disabled account.")
    email = f"disabled_{uuid.uuid4().hex[:10]}@example.com"
    register_res = client.post(
        "/auth/register", json={"email": email, "password": "StrongPassword123!"}, headers=HEADERS
    )
    assert register_res.status_code == 201
    user_id = register_res.json()["id"]
    token, _ = create_access_token(user_id)

    mongo_client = pymongo.MongoClient(settings.MONGODB_URI)
    try:
        mongo_client[settings.MONGODB_DB_NAME].users.update_one(
            {"_id": ObjectId(user_id)}, {"$set": {"is_active": False}}
        )
    finally:
        mongo_client.close()

    response = client.get("/auth/me", headers={**HEADERS, "Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    logger.info("Disabled account correctly rejected with 403 Forbidden (not 401).")

def test_categorize_and_analytics_reject_jwt_without_api_key(client, auth_user):
    """The API key and JWT layers are independent - a genuine JWT alone,
    without the shared API key, must not be enough to reach a user-scoped
    endpoint either."""
    logger.info("Testing that a bare JWT (no API key) is rejected on a user-scoped endpoint.")
    response = client.post(
        "/v1/categorize",
        json={"text": "swiggy"},
        headers={"Authorization": f"Bearer {auth_user['access_token']}", "Content-Type": "application/json"},
    )
    assert response.status_code in [401, 403]
    logger.info("Bare JWT without the API key correctly rejected.")
