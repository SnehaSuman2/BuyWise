"""Community reports: submission, moderation queue, flags. Approved reports feed the Trust Engine."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CommunityReport, ReportFlag, User
from app.schemas.community import CommunityReportCreate, CommunityReportResponse

BANNED_PATTERNS = ("http://", "https://", "whatsapp", "telegram", "call me", "dm me")


class CommunityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user: User, data: CommunityReportCreate) -> CommunityReportResponse:
        if not (data.product_id or data.retailer_id or data.seller_id):
            raise HTTPException(
                status_code=422, detail="A product, retailer or seller must be referenced"
            )
        body_l = data.body.lower()
        if any(p in body_l for p in BANNED_PATTERNS):
            raise HTTPException(
                status_code=422, detail="Reports cannot contain links or contact details"
            )
        ref_hash = (
            hashlib.sha256(data.order_reference.strip().lower().encode()).hexdigest()
            if data.order_reference
            else None
        )
        report = CommunityReport(
            user_id=user.id,
            product_id=data.product_id,
            retailer_id=data.retailer_id,
            seller_id=data.seller_id,
            report_type=data.report_type,
            title=data.title,
            body=data.body,
            rating=data.rating,
            order_reference_hash=ref_hash,
            verification_status="pending" if ref_hash else "unverified",
            moderation_status="pending",
        )
        self.db.add(report)
        await self.db.flush()
        return self._response(report, user.username)

    async def list_public(
        self,
        product_id: uuid.UUID | None,
        retailer_id: uuid.UUID | None,
        seller_id: uuid.UUID | None,
        page: int,
        page_size: int,
    ) -> list[CommunityReportResponse]:
        stmt = (
            select(CommunityReport, User.username)
            .join(User, User.id == CommunityReport.user_id)
            .where(CommunityReport.moderation_status == "approved")
        )
        if product_id:
            stmt = stmt.where(CommunityReport.product_id == product_id)
        if retailer_id:
            stmt = stmt.where(CommunityReport.retailer_id == retailer_id)
        if seller_id:
            stmt = stmt.where(CommunityReport.seller_id == seller_id)
        rows = (
            await self.db.execute(
                stmt.order_by(CommunityReport.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return [self._response(r, username) for r, username in rows]

    async def mine(self, user: User) -> list[CommunityReportResponse]:
        rows = (
            (
                await self.db.execute(
                    select(CommunityReport)
                    .where(CommunityReport.user_id == user.id)
                    .order_by(CommunityReport.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return [self._response(r, user.username) for r in rows]

    async def flag(self, user: User, report_id: uuid.UUID, reason: str) -> None:
        report = (
            await self.db.execute(select(CommunityReport).where(CommunityReport.id == report_id))
        ).scalar_one_or_none()
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        self.db.add(ReportFlag(report_id=report_id, user_id=user.id, reason=reason))
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(status_code=409, detail="You already flagged this report") from None
        report.flag_count += 1
        if report.flag_count >= 3 and report.moderation_status == "approved":
            report.moderation_status = "hidden"

    async def moderation_queue(self, status: str = "pending") -> list[CommunityReportResponse]:
        rows = (
            await self.db.execute(
                select(CommunityReport, User.username)
                .join(User, User.id == CommunityReport.user_id)
                .where(CommunityReport.moderation_status == status)
                .order_by(CommunityReport.created_at.asc())
                .limit(100)
            )
        ).all()
        return [self._response(r, u) for r, u in rows]

    async def moderate(
        self, moderator: User, report_id: uuid.UUID, action: str, note: str | None
    ) -> CommunityReportResponse:
        report = (
            await self.db.execute(select(CommunityReport).where(CommunityReport.id == report_id))
        ).scalar_one_or_none()
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        if action in ("approve", "reject", "hide"):
            report.moderation_status = {
                "approve": "approved",
                "reject": "rejected",
                "hide": "hidden",
            }[action]
        elif action == "verify":
            report.verification_status = "verified"
        elif action == "reject_verification":
            report.verification_status = "rejected"
        report.moderation_note = note
        report.moderated_at = datetime.now(timezone.utc)
        return self._response(report, None)

    @staticmethod
    def _response(r: CommunityReport, username: str | None) -> CommunityReportResponse:
        return CommunityReportResponse(
            id=r.id,
            username=username,
            product_id=r.product_id,
            retailer_id=r.retailer_id,
            seller_id=r.seller_id,
            report_type=r.report_type,
            title=r.title,
            body=r.body,
            rating=float(r.rating) if r.rating else None,
            verification_status=r.verification_status,
            moderation_status=r.moderation_status,
            flag_count=r.flag_count,
            helpful_count=r.helpful_count,
            is_demo=r.is_demo,
            created_at=r.created_at,
        )
