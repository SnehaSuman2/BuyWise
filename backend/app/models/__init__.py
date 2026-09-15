"""Import all models so they're registered with SQLAlchemy metadata."""

from app.models.affiliate import AffiliateClick
from app.models.alert import Notification, PriceAlert
from app.models.base import JSONType, SoftDeleteMixin, TimestampMixin, UUIDMixin, UUIDType
from app.models.billing import Payment, Subscription, WebhookEvent
from app.models.community import CommunityReport, ReportFlag
from app.models.jobs import JobRun
from app.models.offer import Offer
from app.models.price_history import PriceHistory
from app.models.product import Product, ProductVariant
from app.models.retailer import Retailer, Seller
from app.models.review import Review, ReviewAnalysis
from app.models.search import Search
from app.models.trust import TrustEvent, TrustEvidence, TrustScore
from app.models.user import RefreshSession, SavedProduct, User

__all__ = [
    "AffiliateClick",
    "Notification",
    "PriceAlert",
    "JSONType",
    "SoftDeleteMixin",
    "TimestampMixin",
    "UUIDMixin",
    "UUIDType",
    "Payment",
    "Subscription",
    "WebhookEvent",
    "CommunityReport",
    "ReportFlag",
    "JobRun",
    "Offer",
    "PriceHistory",
    "Product",
    "ProductVariant",
    "Retailer",
    "Seller",
    "Review",
    "ReviewAnalysis",
    "Search",
    "TrustEvent",
    "TrustEvidence",
    "TrustScore",
    "RefreshSession",
    "SavedProduct",
    "User",
]
