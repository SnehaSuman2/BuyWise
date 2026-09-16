"""Community experiences: moderation gate, anti-spam, flagging, admin isolation."""

import pytest

BODY = "Ordered on 2 September, arrived sealed and genuine four days later. Return was easy."


@pytest.mark.asyncio
async def test_report_is_not_public_until_approved(client, auth_headers, admin_headers, demo_product):
    created = await client.post(
        "/api/v1/community/reports",
        headers=auth_headers,
        json={"product_id": demo_product, "report_type": "purchase", "body": BODY, "rating": 4},
    )
    assert created.status_code == 201, created.text
    report = created.json()
    assert report["moderation_status"] == "pending"

    public = await client.get(f"/api/v1/community/reports?product_id={demo_product}")
    assert public.status_code == 200
    assert public.json() == []

    approved = await client.post(
        f"/api/v1/admin/moderation/{report['id']}",
        headers=admin_headers,
        json={"action": "approve"},
    )
    assert approved.status_code == 200

    public = await client.get(f"/api/v1/community/reports?product_id={demo_product}")
    assert [r["id"] for r in public.json()] == [report["id"]]


@pytest.mark.asyncio
async def test_rejected_report_never_becomes_public(client, auth_headers, admin_headers, demo_product):
    report = (
        await client.post(
            "/api/v1/community/reports",
            headers=auth_headers,
            json={"product_id": demo_product, "report_type": "authenticity", "body": BODY},
        )
    ).json()
    await client.post(
        f"/api/v1/admin/moderation/{report['id']}",
        headers=admin_headers,
        json={"action": "reject", "note": "unverifiable"},
    )
    public = await client.get(f"/api/v1/community/reports?product_id={demo_product}")
    assert public.json() == []


@pytest.mark.asyncio
async def test_links_and_contact_details_are_rejected(client, auth_headers, demo_product):
    for body in (
        "Great seller, order here https://example.com/deal for a discount on this exact item",
        "Message me on whatsapp for a much cheaper price on this same product today",
    ):
        r = await client.post(
            "/api/v1/community/reports",
            headers=auth_headers,
            json={"product_id": demo_product, "report_type": "purchase", "body": body},
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_report_requires_a_subject_and_minimum_length(client, auth_headers, demo_product):
    no_subject = await client.post(
        "/api/v1/community/reports",
        headers=auth_headers,
        json={"report_type": "purchase", "body": BODY},
    )
    assert no_subject.status_code == 422

    too_short = await client.post(
        "/api/v1/community/reports",
        headers=auth_headers,
        json={"product_id": demo_product, "report_type": "purchase", "body": "bad"},
    )
    assert too_short.status_code == 422


@pytest.mark.asyncio
async def test_order_reference_is_stored_hashed_and_never_returned(
    client, auth_headers, admin_headers, demo_product, db
):
    from sqlalchemy import select

    from app.models import CommunityReport

    reference = "408-1234567-7654321"
    created = await client.post(
        "/api/v1/community/reports",
        headers=auth_headers,
        json={
            "product_id": demo_product,
            "report_type": "delivery",
            "body": BODY,
            "order_reference": reference,
        },
    )
    assert created.status_code == 201
    assert reference not in created.text
    assert created.json()["verification_status"] == "pending"

    row = (await db.execute(select(CommunityReport))).scalars().first()
    assert row.order_reference_hash and row.order_reference_hash != reference
    assert len(row.order_reference_hash) == 64


@pytest.mark.asyncio
async def test_anonymous_cannot_write_and_non_admin_cannot_moderate(
    client, auth_headers, demo_product
):
    anon = await client.post(
        "/api/v1/community/reports",
        json={"product_id": demo_product, "report_type": "purchase", "body": BODY},
    )
    assert anon.status_code in (401, 403)

    report = (
        await client.post(
            "/api/v1/community/reports",
            headers=auth_headers,
            json={"product_id": demo_product, "report_type": "purchase", "body": BODY},
        )
    ).json()
    queue = await client.get("/api/v1/admin/moderation", headers=auth_headers)
    assert queue.status_code == 403
    moderate = await client.post(
        f"/api/v1/admin/moderation/{report['id']}",
        headers=auth_headers,
        json={"action": "approve"},
    )
    assert moderate.status_code == 403


@pytest.mark.asyncio
async def test_flagging_is_once_per_user_and_queue_shows_pending(
    client, auth_headers, admin_headers, demo_product
):
    report = (
        await client.post(
            "/api/v1/community/reports",
            headers=auth_headers,
            json={"product_id": demo_product, "report_type": "purchase", "body": BODY},
        )
    ).json()

    queue = await client.get("/api/v1/admin/moderation?status=pending", headers=admin_headers)
    assert report["id"] in [r["id"] for r in queue.json()]

    first = await client.post(
        f"/api/v1/community/reports/{report['id']}/flag",
        headers=admin_headers,
        json={"reason": "reads like an advertisement"},
    )
    assert first.status_code == 204
    again = await client.post(
        f"/api/v1/community/reports/{report['id']}/flag",
        headers=admin_headers,
        json={"reason": "reads like an advertisement"},
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_mine_returns_only_the_callers_reports(client, auth_headers, admin_headers, demo_product):
    await client.post(
        "/api/v1/community/reports",
        headers=auth_headers,
        json={"product_id": demo_product, "report_type": "purchase", "body": BODY},
    )
    mine = await client.get("/api/v1/community/reports/mine", headers=auth_headers)
    assert len(mine.json()) == 1
    other = await client.get("/api/v1/community/reports/mine", headers=admin_headers)
    assert other.json() == []
