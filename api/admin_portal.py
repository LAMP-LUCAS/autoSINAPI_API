# api/admin_portal.py
"""
Admin endpoints for subscription management, grants, and coupon system.

Provides:
- POST /api/v1/admin/subscriptions/grant — Grant a subscription (bypass MP)
- POST /api/v1/admin/coupons — Create a coupon
- GET  /api/v1/admin/coupons — List coupons
- PUT  /api/v1/admin/coupons/{id} — Update a coupon
- POST /api/v1/admin/coupons/validate — Validate a coupon code (public-facing)
- POST /api/v1/admin/coupons/apply — Apply coupon to create/grant subscription
- GET  /api/v1/admin/subscriptions/expiring — List subscriptions expiring soon
- POST /api/v1/admin/subscriptions/{id}/expire-now — Force-expire a subscription
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
import json
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Body, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import get_saas_db as get_db
from .schemas import _RATE_LIMIT_RESPONSE, _AUTH_RESPONSES

logger = logging.getLogger("autosinapi.admin")

router = APIRouter(tags=["Admin"])

# ── Auth dependency (shared) ──────────────────────────────────────────────────
from .admin_auth import verify_admin_token


# ── Schemas ───────────────────────────────────────────────────────────────────

class GrantRequest(BaseModel):
    client_id: str = Field(..., description="Client UUID to grant subscription to")
    plan_slug: str = Field(..., description="Plan slug (e.g. 'business', 'pro_anual')")
    days: Optional[int] = Field(None, description="Override duration in days (None = plan default)")
    reason: str = Field("admin_grant", description="Reason for the grant")
    source: str = Field("granted", description="Source: granted, promo, internal")
    coupon_code: Optional[str] = Field(None, description="Optional coupon code used")


class CouponCreate(BaseModel):
    code: str = Field(..., min_length=3, max_length=32, description="Unique coupon code")
    description: Optional[str] = None
    discount_type: str = Field("percent", description="percent | flat | grant_days | grant_plan")
    discount_value: float = Field(0, description="Discount value (depends on type)")
    target_plan: Optional[str] = Field(None, description="Plan slug this applies to (None = any)")
    grant_plan: Optional[str] = Field(None, description="For grant_plan: plan slug to grant")
    max_uses_total: int = Field(0, description="0 = unlimited")
    max_uses_per_user: int = Field(1)
    valid_from: Optional[str] = Field(None, description="ISO timestamp (default: now)")
    valid_until: Optional[str] = Field(None, description="ISO timestamp (None = never expires)")
    metadata: dict = Field(default_factory=dict)


class CouponValidate(BaseModel):
    code: str = Field(..., description="Coupon code to validate")
    plan_slug: Optional[str] = Field(None, description="Target plan for price calculation")


class CouponApply(BaseModel):
    code: str = Field(..., description="Coupon code to apply")
    client_id: str = Field(..., description="Client UUID")
    plan_slug: str = Field(..., description="Plan to subscribe to")


# ── Admin: Grant Subscription ─────────────────────────────────────────────────

@router.post(
    "/api/v1/admin/subscriptions/grant",
    summary="Grant a subscription (bypass Mercado Pago)",
    response_description="Created subscription details",
    dependencies=[Depends(verify_admin_token)],
    responses=_AUTH_RESPONSES,
)
def grant_subscription(req: GrantRequest, response: Response, db: Session = Depends(get_db)):
    # Resolve plan
    plan = db.execute(
        text("SELECT * FROM saas.plans WHERE slug = :slug AND active = TRUE"),
        {"slug": req.plan_slug},
    ).mappings().first()
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan '{req.plan_slug}' not found")

    # Check client exists
    client = db.execute(
        text("SELECT id, name, email FROM saas.clients WHERE id = :id"),
        {"id": req.client_id},
    ).mappings().first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{req.client_id}' not found")

    # Calculate period
    duration_days = req.days or plan["duration_days"]
    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=duration_days)

    # Cancel any active subscription for this client on same plan
    db.execute(
        text("""
            UPDATE saas.subscriptions 
            SET status = 'cancelled', updated_at = NOW()
            WHERE client_id = :client_id 
              AND plan_id = :plan_id 
              AND status = 'active'
        """),
        {"client_id": req.client_id, "plan_id": plan["id"]},
    )

    # Create subscription
    sub_result = db.execute(
        text("""
            INSERT INTO saas.subscriptions 
                (client_id, plan_id, status, source, granted_by, coupon_id,
                 current_period_start, current_period_end)
            VALUES 
                (:client_id, :plan_id, 'active', :source, :granted_by, :coupon_id,
                 :period_start, :period_end)
            RETURNING id
        """),
        {
            "client_id": req.client_id,
            "plan_id": plan["id"],
            "source": req.source,
            "granted_by": "admin",
            "coupon_id": None,
            "period_start": now,
            "period_end": period_end,
        },
    )
    sub_id = sub_result.scalar_one()

    # Create API key
    import secrets
    key_value = f"autosinapi_{secrets.token_hex(16)}"
    key_prefix = key_value[11:19]  # 8 hex chars after the "autosinapi_" prefix
    key_result = db.execute(
        text("""
            INSERT INTO saas.api_keys (client_id, subscription_id, key_prefix, key_hash, status)
            VALUES (:client_id, :sub_id, :prefix, crypt(:key_value, gen_salt('bf')), 'active')
            RETURNING id
        """),
        {
            "client_id": req.client_id,
            "sub_id": sub_id,
            "key_value": key_value,
            "prefix": key_prefix,
        },
    )
    key_id = key_result.scalar_one()

    # Audit
    db.execute(
        text("""
            INSERT INTO saas.subscription_audit (subscription_id, client_id, action, plan_id, new_status, changed_at)
            VALUES (:sub_id, :client_id, 'granted', :plan_id, 'active', NOW())
        """),
        {"sub_id": sub_id, "client_id": req.client_id, "plan_id": plan["id"]},
    )

    db.execute(
        text("""
            INSERT INTO saas.client_events (client_id, event_type, actor, details, occurred_at)
            VALUES (:client_id, 'subscription_granted', 'admin', CAST(:details AS jsonb), NOW())
        """),
        {
            "client_id": req.client_id,
            "details": json.dumps({
                "plan": req.plan_slug,
                "reason": req.reason,
                "days": duration_days,
                "source": req.source,
            }),
        },
    )

    db.commit()
    response.headers["Cache-Control"] = "no-store"

    return {
        "subscription_id": str(sub_id),
        "api_key": key_value,
        "plan": req.plan_slug,
        "period_end": period_end.isoformat(),
        "source": req.source,
        "reason": req.reason,
    }


# ── Admin: Coupon CRUD ────────────────────────────────────────────────────────

@router.post(
    "/api/v1/admin/coupons",
    summary="Create a promotional coupon",
    dependencies=[Depends(verify_admin_token)],
)
def create_coupon(req: CouponCreate, db: Session = Depends(get_db)):
    # Check code uniqueness
    existing = db.execute(
        text("SELECT id FROM saas.coupons WHERE code = :code"),
        {"code": req.code.upper()},
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Coupon '{req.code}' already exists")

    now = datetime.now(timezone.utc)
    result = db.execute(
        text("""
            INSERT INTO saas.coupons 
                (code, description, discount_type, discount_value, target_plan, grant_plan,
                 max_uses_total, max_uses_per_user, valid_from, valid_until, metadata)
            VALUES 
                (:code, :desc, :dtype, :dval, :tplan, :gplan,
                 :max_total, :max_user, :vfrom, :vuntil, CAST(:meta AS jsonb))
            RETURNING id, code, created_at
        """),
        {
            "code": req.code.upper(),
            "desc": req.description,
            "dtype": req.discount_type,
            "dval": req.discount_value,
            "tplan": req.target_plan,
            "gplan": req.grant_plan,
            "max_total": req.max_uses_total,
            "max_user": req.max_uses_per_user,
            "vfrom": req.valid_from or now.isoformat(),
            "vuntil": req.valid_until,
            "meta": json.dumps(req.metadata),
        },
    )
    coupon = result.mappings().first()
    db.commit()

    return {
        "id": str(coupon["id"]),
        "code": coupon["code"],
        "created_at": coupon["created_at"].isoformat(),
    }


@router.get(
    "/api/v1/admin/coupons",
    summary="List all coupons",
    dependencies=[Depends(verify_admin_token)],
)
def list_coupons(
    active_only: bool = Query(True, description="Only show active coupons"),
    db: Session = Depends(get_db),
):
    where = "WHERE active = TRUE" if active_only else ""
    rows = db.execute(
        text(f"""
            SELECT c.*, 
                   (SELECT COUNT(*) FROM saas.coupon_usages cu WHERE cu.coupon_id = c.id) as uses
            FROM saas.coupons c
            {where}
            ORDER BY c.created_at DESC
        """)
    ).mappings().all()

    return [{
        "id": str(r["id"]),
        "code": r["code"],
        "description": r["description"],
        "discount_type": r["discount_type"],
        "discount_value": float(r["discount_value"]),
        "target_plan": r["target_plan"],
        "grant_plan": r["grant_plan"],
        "max_uses_total": r["max_uses_total"],
        "max_uses_per_user": r["max_uses_per_user"],
        "current_uses": r["current_uses"],
        "actual_uses": r["uses"],
        "valid_from": r["valid_from"].isoformat() if r["valid_from"] else None,
        "valid_until": r["valid_until"].isoformat() if r["valid_until"] else None,
        "active": r["active"],
        "created_at": r["created_at"].isoformat(),
    } for r in rows]


@router.put(
    "/api/v1/admin/coupons/{coupon_id}",
    summary="Update a coupon",
    dependencies=[Depends(verify_admin_token)],
)
def update_coupon(coupon_id: str, req: CouponCreate, db: Session = Depends(get_db)):
    existing = db.execute(
        text("SELECT id FROM saas.coupons WHERE id = :id"),
        {"id": coupon_id},
    ).scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="Coupon not found")

    db.execute(
        text("""
            UPDATE saas.coupons SET
                code = :code, description = :desc, discount_type = :dtype,
                discount_value = :dval, target_plan = :tplan, grant_plan = :gplan,
                max_uses_total = :max_total, max_uses_per_user = :max_user,
                valid_until = :vuntil, metadata = CAST(:meta AS jsonb), updated_at = NOW()
            WHERE id = :id
        """),
        {
            "id": coupon_id,
            "code": req.code.upper(),
            "desc": req.description,
            "dtype": req.discount_type,
            "dval": req.discount_value,
            "tplan": req.target_plan,
            "gplan": req.grant_plan,
            "max_total": req.max_uses_total,
            "max_user": req.max_uses_per_user,
            "vuntil": req.valid_until,
            "meta": json.dumps(req.metadata),
        },
    )
    db.commit()
    return {"status": "updated", "id": coupon_id}


# ── Public: Validate Coupon ───────────────────────────────────────────────────

@router.post(
    "/api/v1/public/coupons/validate",
    summary="Validate a coupon code and show discount preview",
    response_description="Coupon details and computed discount",
    responses=_RATE_LIMIT_RESPONSE,
)
def validate_coupon(req: CouponValidate, db: Session = Depends(get_db)):
    code = req.code.upper().strip()
    coupon = db.execute(
        text("""
            SELECT * FROM saas.coupons 
            WHERE code = :code AND active = TRUE
        """),
        {"code": code},
    ).mappings().first()

    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found or inactive")

    now = datetime.now(timezone.utc)

    # Check validity window
    if coupon["valid_from"] and coupon["valid_from"] > now:
        raise HTTPException(status_code=400, detail="Coupon not yet valid")
    if coupon["valid_until"] and coupon["valid_until"] < now:
        raise HTTPException(status_code=400, detail="Coupon has expired")

    # Check usage limits
    if coupon["max_uses_total"] > 0 and coupon["current_uses"] >= coupon["max_uses_total"]:
        raise HTTPException(status_code=400, detail="Coupon usage limit reached")

    # Compute discount preview. Price-based types need a plan slug; grant-based
    # types are plan-independent and always previewable.
    discount_preview = None
    dtype = coupon["discount_type"]
    if dtype in ("grant_days", "grant_plan"):
        target = req.plan_slug or coupon["target_plan"] or coupon["grant_plan"]
        plan = None
        if target:
            plan = db.execute(
                text("SELECT * FROM saas.plans WHERE slug = :slug"),
                {"slug": target},
            ).mappings().first()
        discount_preview = _compute_discount(coupon, plan or {"price_cents": 0, "slug": target})
    elif req.plan_slug:
        plan = db.execute(
            text("SELECT * FROM saas.plans WHERE slug = :slug"),
            {"slug": req.plan_slug},
        ).mappings().first()
        if plan:
            discount_preview = _compute_discount(coupon, plan)

    return {
        "valid": True,
        "code": code,
        "description": coupon["description"],
        "discount_type": coupon["discount_type"],
        "discount_value": float(coupon["discount_value"]),
        "target_plan": coupon["target_plan"],
        "grant_plan": coupon["grant_plan"],
        "discount_preview": discount_preview,
    }


def _compute_discount(coupon: dict, plan: dict) -> dict:
    """Compute discount for a plan based on coupon type."""
    price = float(plan["price_cents"] or 0)
    dtype = coupon["discount_type"]
    dval = float(coupon["discount_value"])

    if dtype == "percent":
        discount_cents = round(price * dval / 100)
        final_price = price - discount_cents
        return {
            "original_price_cents": int(price),
            "discount_cents": int(discount_cents),
            "final_price_cents": int(final_price),
            "savings_percent": dval,
        }
    elif dtype == "flat":
        discount_cents = min(dval, price)
        final_price = price - discount_cents
        return {
            "original_price_cents": int(price),
            "discount_cents": int(discount_cents),
            "final_price_cents": int(final_price),
        }
    elif dtype == "grant_days":
        return {
            "grant_days": int(dval),
            "plan": plan["slug"],
        }
    elif dtype == "grant_plan":
        return {
            "grant_plan": coupon["grant_plan"],
            "grant_days": int(dval),
        }
    return None


# ── Admin: Apply Coupon ───────────────────────────────────────────────────────

@router.post(
    "/api/v1/admin/coupons/apply",
    summary="Apply a coupon to create/grant a subscription",
    dependencies=[Depends(verify_admin_token)],
)
def apply_coupon(req: CouponApply, response: Response, db: Session = Depends(get_db)):
    code = req.code.upper().strip()

    # Validate coupon
    coupon = db.execute(
        text("SELECT * FROM saas.coupons WHERE code = :code AND active = TRUE"),
        {"code": code},
    ).mappings().first()
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found or inactive")

    now = datetime.now(timezone.utc)
    if coupon["valid_from"] and coupon["valid_from"] > now:
        raise HTTPException(status_code=400, detail="Coupon not yet valid")
    if coupon["valid_until"] and coupon["valid_until"] < now:
        raise HTTPException(status_code=400, detail="Coupon has expired")
    if coupon["max_uses_total"] > 0 and coupon["current_uses"] >= coupon["max_uses_total"]:
        raise HTTPException(status_code=400, detail="Coupon usage limit reached")

    # Check per-user limit
    user_uses = db.execute(
        text("SELECT COUNT(*) FROM saas.coupon_usages WHERE coupon_id = :cid AND client_id = :clid"),
        {"cid": coupon["id"], "clid": req.client_id},
    ).scalar_one()
    if user_uses >= coupon["max_uses_per_user"]:
        raise HTTPException(status_code=400, detail="You have already used this coupon")

    # Determine target plan
    plan_slug = coupon["grant_plan"] if coupon["discount_type"] == "grant_plan" else req.plan_slug
    if not plan_slug:
        raise HTTPException(status_code=400, detail="No plan specified and coupon requires a target plan")

    plan = db.execute(
        text("SELECT * FROM saas.plans WHERE slug = :slug AND active = TRUE"),
        {"slug": plan_slug},
    ).mappings().first()
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan '{plan_slug}' not found")

    # Calculate duration
    if coupon["discount_type"] in ("grant_days", "grant_plan"):
        duration_days = int(coupon["discount_value"])
    else:
        duration_days = plan["duration_days"]

    # Create subscription
    period_end = now + timedelta(days=duration_days)

    # Cancel existing active sub on same plan
    db.execute(
        text("""
            UPDATE saas.subscriptions SET status = 'cancelled', updated_at = NOW()
            WHERE client_id = :cid AND plan_id = :pid AND status = 'active'
        """),
        {"cid": req.client_id, "pid": plan["id"]},
    )

    sub_result = db.execute(
        text("""
            INSERT INTO saas.subscriptions 
                (client_id, plan_id, status, source, coupon_id,
                 current_period_start, current_period_end)
            VALUES (:cid, :pid, 'active', 'promo', :coupon_id, :ps, :pe)
            RETURNING id
        """),
        {"cid": req.client_id, "pid": plan["id"], "coupon_id": coupon["id"],
         "ps": now, "pe": period_end},
    )
    sub_id = sub_result.scalar_one()

    # Create API key
    import secrets
    key_value = f"autosinapi_{secrets.token_hex(16)}"
    key_prefix = key_value[11:19]
    db.execute(
        text("""
            INSERT INTO saas.api_keys (client_id, subscription_id, key_prefix, key_hash, status)
            VALUES (:cid, :sid, :prefix, crypt(:kv, gen_salt('bf')), 'active')
        """),
        {"cid": req.client_id, "sid": sub_id, "kv": key_value, "prefix": key_prefix},
    )

    # Record coupon usage
    db.execute(
        text("""
            INSERT INTO saas.coupon_usages (coupon_id, client_id, subscription_id, discount_applied, details)
            VALUES (:cid, :clid, :sid, :disc, CAST(:det AS jsonb))
        """),
        {
            "cid": coupon["id"],
            "clid": req.client_id,
            "sid": sub_id,
            "disc": float(coupon["discount_value"]),
            "det": json.dumps({"code": code, "plan": plan_slug, "days": duration_days}),
        },
    )

    # Increment coupon usage count
    db.execute(
        text("UPDATE saas.coupons SET current_uses = current_uses + 1, updated_at = NOW() WHERE id = :id"),
        {"id": coupon["id"]},
    )

    # Audit
    db.execute(
        text("""
            INSERT INTO saas.client_events (client_id, event_type, actor, details, occurred_at)
            VALUES (:cid, 'coupon_applied', 'system', CAST(:det AS jsonb), NOW())
        """),
        {"cid": req.client_id, "det": json.dumps({"coupon": code, "plan": plan_slug, "days": duration_days})},
    )

    db.commit()
    response.headers["Cache-Control"] = "no-store"

    return {
        "subscription_id": str(sub_id),
        "api_key": key_value,
        "plan": plan_slug,
        "period_end": period_end.isoformat(),
        "coupon_code": code,
        "source": "promo",
    }


# ── Admin: Expiring Subscriptions ─────────────────────────────────────────────

@router.get(
    "/api/v1/admin/subscriptions/expiring",
    summary="List subscriptions expiring within N days",
    dependencies=[Depends(verify_admin_token)],
)
def expiring_subscriptions(
    days: int = Query(7, description="Days ahead to check"),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT s.id, s.client_id, s.status, s.source, s.current_period_end,
                   p.slug as plan_slug, p.name as plan_name,
                   c.name as client_name, c.email as client_email
            FROM saas.subscriptions s
            JOIN saas.plans p ON p.id = s.plan_id
            LEFT JOIN saas.clients c ON c.id = s.client_id
            WHERE s.status = 'active'
              AND s.current_period_end < NOW() + (make_interval(days => :days))
              AND s.current_period_end > NOW()
            ORDER BY s.current_period_end ASC
        """),
        {"days": days},
    ).mappings().all()

    return [{
        "subscription_id": str(r["id"]),
        "client_name": r["client_name"],
        "client_email": r["client_email"],
        "plan": r["plan_slug"],
        "source": r["source"],
        "period_end": r["current_period_end"].isoformat(),
        "days_remaining": (r["current_period_end"] - datetime.now(timezone.utc)).days,
    } for r in rows]


# ── Admin: Force Expire ───────────────────────────────────────────────────────

@router.post(
    "/api/v1/admin/subscriptions/{subscription_id}/expire-now",
    summary="Force-expire a subscription immediately",
    dependencies=[Depends(verify_admin_token)],
)
def force_expire(subscription_id: str, db: Session = Depends(get_db)):
    sub = db.execute(
        text("SELECT * FROM saas.subscriptions WHERE id = :id"),
        {"id": subscription_id},
    ).mappings().first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if sub["status"] != "active":
        raise HTTPException(status_code=400, detail=f"Subscription is already {sub['status']}")

    db.execute(
        text("UPDATE saas.subscriptions SET status = 'expired', updated_at = NOW() WHERE id = :id"),
        {"id": subscription_id},
    )

    db.execute(
        text("""
            INSERT INTO saas.subscription_audit (subscription_id, client_id, action, plan_id, old_status, new_status, changed_at)
            VALUES (:sid, :cid, 'force_expired', :pid, 'active', 'expired', NOW())
        """),
        {"sid": subscription_id, "cid": sub["client_id"], "pid": sub["plan_id"]},
    )

    db.execute(
        text("""
            INSERT INTO saas.client_events (client_id, event_type, actor, details, occurred_at)
            VALUES (:cid, 'subscription_expired', 'admin', '{"forced": true}', NOW())
        """),
        {"cid": sub["client_id"]},
    )

    db.commit()
    return {"status": "expired", "subscription_id": subscription_id}
