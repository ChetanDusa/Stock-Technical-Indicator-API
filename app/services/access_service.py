"""Tier authorization for returned history and analytical features."""

from __future__ import annotations

import datetime

from app.core.exceptions import (
    AccessDeniedException,
    InvalidDateRangeException,
)
from app.core.tiers import TIER_LIMITS
from app.services.rate_limiter import RateLimiter
from models import User


class AccessService:
    def __init__(self, rate_limiter: RateLimiter, reference_date: datetime.date) -> None:
        self.rate_limiter = rate_limiter
        self.reference_date = reference_date

    def check_access(
        self,
        user: User,
        indicator: str,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> None:
        """Validate that *user* may request *indicator* for the given date range.

        Raises domain exceptions on failure; returns None on success.
        """
        tier_info = TIER_LIMITS.get(user.subscription)
        if tier_info is None:
            raise AccessDeniedException("Invalid subscription tier")

        # indicator allowed?
        if indicator not in tier_info["allowed_indicators"]:
            raise AccessDeniedException(
                f"{indicator.upper()} not allowed for {user.subscription} tier"
            )

        # date range valid?
        if end_date < start_date:
            raise InvalidDateRangeException("End date must be after start date")

        # history window check
        allowed_start = self.reference_date - datetime.timedelta(days=tier_info["history_days"])
        if start_date < allowed_start:
            raise AccessDeniedException(
                f"{user.subscription.title()} tier only allows data from {allowed_start.isoformat()} onwards"
            )

    def check_screening_access(
        self,
        user: User,
        conditions: list,
    ) -> None:
        """Validate that *user* may perform stock screening with the given conditions.

        Raises AccessDeniedException if screening is disallowed or any condition
        references an indicator not permitted for the user's tier.
        """
        tier_info = TIER_LIMITS.get(user.subscription, {})

        if not tier_info.get("screening_allowed", False):
            raise AccessDeniedException(f"Screening not allowed for {user.subscription} tier")

        allowed_indicators = tier_info.get("allowed_screening_indicators", set())

        for cond in conditions:
            # Check LHS indicator
            lhs_ind = cond.indicator.upper()
            if lhs_ind not in allowed_indicators:
                raise AccessDeniedException(f"{lhs_ind} not allowed for {user.subscription} tier")

            # Check RHS indicator if reference is used
            if cond.reference is not None:
                rhs_ind = cond.reference.indicator.upper()
                if rhs_ind not in allowed_indicators:
                    raise AccessDeniedException(
                        f"{rhs_ind} not allowed for {user.subscription} tier"
                    )

    def enforce_rate_limit(self, user: User) -> None:
        """Check and increment the user's daily request counter atomically via Redis."""
        self.rate_limiter.enforce_rate_limit(user)
