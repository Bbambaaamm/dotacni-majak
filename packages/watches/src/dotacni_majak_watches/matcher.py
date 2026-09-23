from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum

from dotacni_majak_eligibility import EligibilityStatus
from dotacni_majak_finance import FinanceStatus
from dotacni_majak_search import MatchBand, RankedGrantMatch


class WatchType(str, Enum):
    PROJECT = "PROJECT"
    GRANT = "GRANT"
    CATEGORY = "CATEGORY"
    PROVIDER = "PROVIDER"
    GEOGRAPHY = "GEOGRAPHY"
    CUSTOM_SEARCH = "CUSTOM_SEARCH"


class WatchMatchStatus(str, Enum):
    MATCHED = "MATCHED"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    NOT_FINANCIALLY_COMPATIBLE = "NOT_FINANCIALLY_COMPATIBLE"
    NOT_RELEVANT = "NOT_RELEVANT"


class WatchMatchAction(str, Enum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True, slots=True)
class ProjectWatch:
    id: str
    project_id: str
    enabled: bool = True
    minimum_match_band: MatchBand = MatchBand.POSSIBLE

    def __post_init__(self) -> None:
        if not self.id or not self.project_id:
            raise ValueError("watch/project ids must not be empty")


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    grant_call_id: str
    grant_call_version_id: str
    relevance: RankedGrantMatch
    eligibility_status: EligibilityStatus | None
    finance_status: FinanceStatus | None

    def __post_init__(self) -> None:
        if self.relevance.grant_call_version_id != self.grant_call_version_id:
            raise ValueError(
                "relevance result does not belong to grant_call_version_id"
            )


@dataclass(frozen=True, slots=True)
class WatchMatch:
    id: str
    watch_id: str
    project_id: str
    grant_call_id: str
    grant_call_version_id: str
    status: WatchMatchStatus
    match_band: MatchBand
    relevance_score: float
    reason_codes: tuple[str, ...]
    notification_candidate: bool
    dedupe_key: str


@dataclass(frozen=True, slots=True)
class WatchMatchResult:
    action: WatchMatchAction
    match: WatchMatch


class InMemoryWatchMatchRepository:
    def __init__(self) -> None:
        self._latest_by_watch_call: dict[tuple[str, str], WatchMatch] = {}

    def latest(
        self,
        watch_id: str,
        grant_call_id: str,
    ) -> WatchMatch | None:
        return self._latest_by_watch_call.get((watch_id, grant_call_id))

    def save(self, match: WatchMatch) -> None:
        self._latest_by_watch_call[(match.watch_id, match.grant_call_id)] = match


class ProjectWatchMatcher:
    def __init__(
        self,
        *,
        repository: InMemoryWatchMatchRepository | None = None,
    ) -> None:
        self.repository = repository or InMemoryWatchMatchRepository()

    def reevaluate(
        self,
        watch: ProjectWatch,
        candidate: CandidateEvaluation,
    ) -> WatchMatchResult:
        status = self._status(watch, candidate)
        reasons = self._reason_codes(candidate, status)

        dedupe_key = (
            f"watch:{watch.id}:call:{candidate.grant_call_id}:"
            f"version:{candidate.grant_call_version_id}:status:{status.value}"
        )
        match = WatchMatch(
            id=_stable_id(dedupe_key),
            watch_id=watch.id,
            project_id=watch.project_id,
            grant_call_id=candidate.grant_call_id,
            grant_call_version_id=candidate.grant_call_version_id,
            status=status,
            match_band=candidate.relevance.match_band,
            relevance_score=candidate.relevance.relevance_score,
            reason_codes=reasons,
            notification_candidate=self._notification_candidate(status),
            dedupe_key=dedupe_key,
        )

        previous = self.repository.latest(watch.id, candidate.grant_call_id)
        if previous is not None and previous.dedupe_key == match.dedupe_key:
            return WatchMatchResult(
                action=WatchMatchAction.UNCHANGED,
                match=previous,
            )

        action = (
            WatchMatchAction.CREATED
            if previous is None
            else WatchMatchAction.UPDATED
        )
        self.repository.save(match)
        return WatchMatchResult(action=action, match=match)

    def _status(
        self,
        watch: ProjectWatch,
        candidate: CandidateEvaluation,
    ) -> WatchMatchStatus:
        if not watch.enabled:
            return WatchMatchStatus.NOT_RELEVANT

        if not _band_at_least(
            candidate.relevance.match_band,
            watch.minimum_match_band,
        ):
            return WatchMatchStatus.NOT_RELEVANT

        if candidate.eligibility_status is EligibilityStatus.INELIGIBLE:
            return WatchMatchStatus.NOT_ELIGIBLE
        if candidate.eligibility_status is EligibilityStatus.NEEDS_REVIEW:
            return WatchMatchStatus.NEEDS_REVIEW
        if (
            candidate.eligibility_status is EligibilityStatus.NEEDS_INFORMATION
            or candidate.eligibility_status is None
        ):
            return WatchMatchStatus.NEEDS_INFORMATION

        if candidate.finance_status is FinanceStatus.SCENARIO_NOT_APPLICABLE:
            return WatchMatchStatus.NOT_FINANCIALLY_COMPATIBLE
        if candidate.finance_status in {
            FinanceStatus.ERROR,
            FinanceStatus.INSTRUMENT_NOT_SUPPORTED,
        }:
            return WatchMatchStatus.NEEDS_REVIEW
        if (
            candidate.finance_status is FinanceStatus.NEEDS_INFORMATION
            or candidate.finance_status is None
        ):
            return WatchMatchStatus.NEEDS_INFORMATION

        return WatchMatchStatus.MATCHED

    @staticmethod
    def _notification_candidate(status: WatchMatchStatus) -> bool:
        # MATCHED is a strong signal. NEEDS_INFORMATION is still valuable:
        # user action may unlock an otherwise relevant new opportunity.
        return status in {
            WatchMatchStatus.MATCHED,
            WatchMatchStatus.NEEDS_INFORMATION,
        }

    @staticmethod
    def _reason_codes(
        candidate: CandidateEvaluation,
        status: WatchMatchStatus,
    ) -> tuple[str, ...]:
        reasons = [
            f"RELEVANCE_{candidate.relevance.match_band.value}",
            *(
                reason.value
                for reason in candidate.relevance.reasons
            ),
            f"WATCH_STATUS_{status.value}",
        ]
        if candidate.eligibility_status is not None:
            reasons.append(
                f"ELIGIBILITY_{candidate.eligibility_status.value}"
            )
        else:
            reasons.append("ELIGIBILITY_NOT_EVALUATED")

        if candidate.finance_status is not None:
            reasons.append(f"FINANCE_{candidate.finance_status.value}")
        else:
            reasons.append("FINANCE_NOT_EVALUATED")

        return tuple(dict.fromkeys(reasons))


def _band_at_least(actual: MatchBand, minimum: MatchBand) -> bool:
    order = {
        MatchBand.WEAK: 0,
        MatchBand.POSSIBLE: 1,
        MatchBand.VERY_GOOD: 2,
    }
    return order[actual] >= order[minimum]


def _stable_id(dedupe_key: str) -> str:
    digest = hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()
    return f"wm_{digest[:24]}"
