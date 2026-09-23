from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Protocol

from dotacni_majak_changes import ChangeEvent, ChangeSeverity, ChangeType
from dotacni_majak_watches import WatchMatch, WatchMatchStatus


class NotificationType(str, Enum):
    NEW_MATCHING_GRANT = "NEW_MATCHING_GRANT"
    MATCH_NEEDS_INFORMATION = "MATCH_NEEDS_INFORMATION"
    GRANT_CHANGED = "GRANT_CHANGED"
    DEADLINE_REMINDER = "DEADLINE_REMINDER"


class NotificationChannel(str, Enum):
    IN_APP = "IN_APP"
    WEB_PUSH = "WEB_PUSH"


class NotificationSeverity(str, Enum):
    INFO = "INFO"
    IMPORTANT = "IMPORTANT"
    CRITICAL = "CRITICAL"


class NotificationStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    READ = "READ"
    FAILED = "FAILED"
    SUPPRESSED = "SUPPRESSED"


@dataclass(frozen=True, slots=True)
class Notification:
    id: str
    user_id: str
    watch_id: str | None
    grant_call_version_id: str | None
    change_event_id: str | None
    notification_type: NotificationType
    channel: NotificationChannel
    severity: NotificationSeverity
    title: str
    body: str
    dedupe_key: str
    status: NotificationStatus
    created_at: datetime
    sent_at: datetime | None = None
    read_at: datetime | None = None
    last_error: str | None = None


@dataclass(frozen=True, slots=True)
class NotificationRequest:
    user_id: str
    watch_id: str | None
    grant_call_version_id: str | None
    change_event_id: str | None
    notification_type: NotificationType
    severity: NotificationSeverity
    title: str
    body: str
    dedupe_base: str
    web_push_opt_in: bool = False


@dataclass(frozen=True, slots=True)
class WebPushSubscription:
    id: str
    user_id: str
    endpoint_ref: str
    active: bool = True


@dataclass(frozen=True, slots=True)
class PushPayload:
    notification_id: str
    title: str
    body: str
    data: dict[str, str]


@dataclass(frozen=True, slots=True)
class PushDeliveryResult:
    delivered: bool
    provider_message_id: str | None = None
    error_code: str | None = None


class WebPushProvider(Protocol):
    def send(
        self,
        subscription: WebPushSubscription,
        payload: PushPayload,
    ) -> PushDeliveryResult: ...


class InMemoryNotificationRepository:
    def __init__(self) -> None:
        self._items: dict[str, Notification] = {}
        self._by_dedupe: dict[str, str] = {}

    def create(
        self,
        request: NotificationRequest,
        channel: NotificationChannel,
        *,
        now: datetime | None = None,
    ) -> Notification:
        dedupe_key = f"{request.dedupe_base}:channel:{channel.value}"
        existing_id = self._by_dedupe.get(dedupe_key)
        if existing_id is not None:
            return self._items[existing_id]

        created = _utc(now or datetime.now(timezone.utc))
        notification = Notification(
            id=_stable_id(dedupe_key),
            user_id=request.user_id,
            watch_id=request.watch_id,
            grant_call_version_id=request.grant_call_version_id,
            change_event_id=request.change_event_id,
            notification_type=request.notification_type,
            channel=channel,
            severity=request.severity,
            title=request.title,
            body=request.body,
            dedupe_key=dedupe_key,
            status=NotificationStatus.PENDING,
            created_at=created,
        )
        self._items[notification.id] = notification
        self._by_dedupe[dedupe_key] = notification.id
        return notification

    def get(self, notification_id: str) -> Notification:
        return self._items[notification_id]

    def mark_sent(
        self,
        notification_id: str,
        *,
        now: datetime | None = None,
    ) -> Notification:
        current = self._items[notification_id]
        if current.status is NotificationStatus.READ:
            return current
        updated = replace(
            current,
            status=NotificationStatus.SENT,
            sent_at=_utc(now or datetime.now(timezone.utc)),
            last_error=None,
        )
        self._items[notification_id] = updated
        return updated

    def mark_failed(self, notification_id: str, error_code: str) -> Notification:
        current = self._items[notification_id]
        updated = replace(
            current,
            status=NotificationStatus.FAILED,
            last_error=error_code,
        )
        self._items[notification_id] = updated
        return updated

    def mark_read(
        self,
        notification_id: str,
        *,
        now: datetime | None = None,
    ) -> Notification:
        current = self._items[notification_id]
        updated = replace(
            current,
            status=NotificationStatus.READ,
            read_at=_utc(now or datetime.now(timezone.utc)),
        )
        self._items[notification_id] = updated
        return updated

    def unread_for_user(self, user_id: str) -> tuple[Notification, ...]:
        items = [
            item
            for item in self._items.values()
            if item.user_id == user_id
            and item.channel is NotificationChannel.IN_APP
            and item.status is not NotificationStatus.READ
        ]
        return tuple(sorted(items, key=lambda item: (item.created_at, item.id)))


class NotificationComposer:
    def for_watch_match(
        self,
        *,
        user_id: str,
        match: WatchMatch,
        web_push_opt_in: bool,
    ) -> NotificationRequest | None:
        if not match.notification_candidate:
            return None

        if match.status is WatchMatchStatus.MATCHED:
            notification_type = NotificationType.NEW_MATCHING_GRANT
            severity = NotificationSeverity.IMPORTANT
            title = "Maják našel novou možnost pro váš projekt"
            body = (
                "Byla nalezena nová relevantní výzva. "
                "Otevřete detail a ověřte podmínky."
            )
        elif match.status is WatchMatchStatus.NEEDS_INFORMATION:
            notification_type = NotificationType.MATCH_NEEDS_INFORMATION
            severity = NotificationSeverity.INFO
            title = "Nová možnost potřebuje doplnit údaj"
            body = (
                "Výzva tematicky odpovídá projektu, ale pro bezpečné "
                "vyhodnocení potřebujeme další informaci."
            )
        else:
            return None

        return NotificationRequest(
            user_id=user_id,
            watch_id=match.watch_id,
            grant_call_version_id=match.grant_call_version_id,
            change_event_id=None,
            notification_type=notification_type,
            severity=severity,
            title=title,
            body=body,
            dedupe_base=f"watch-match:{match.dedupe_key}",
            web_push_opt_in=web_push_opt_in,
        )

    def for_change_event(
        self,
        *,
        user_id: str,
        watch_id: str,
        grant_call_version_id: str,
        event: ChangeEvent,
        web_push_opt_in: bool,
    ) -> NotificationRequest | None:
        if event.severity is ChangeSeverity.EDITORIAL:
            return None

        severity = {
            ChangeSeverity.CRITICAL: NotificationSeverity.CRITICAL,
            ChangeSeverity.IMPORTANT: NotificationSeverity.IMPORTANT,
            ChangeSeverity.INFORMATIONAL: NotificationSeverity.INFO,
            ChangeSeverity.EDITORIAL: NotificationSeverity.INFO,
        }[event.severity]

        title = _change_title(event.change_type)
        body = _change_body(event)

        return NotificationRequest(
            user_id=user_id,
            watch_id=watch_id,
            grant_call_version_id=grant_call_version_id,
            change_event_id=event.id,
            notification_type=NotificationType.GRANT_CHANGED,
            severity=severity,
            title=title,
            body=body,
            dedupe_base=f"change:{watch_id}:{event.id}",
            web_push_opt_in=(
                web_push_opt_in
                and event.severity in {
                    ChangeSeverity.CRITICAL,
                    ChangeSeverity.IMPORTANT,
                }
            ),
        )

    def deadline_reminder(
        self,
        *,
        user_id: str,
        watch_id: str,
        grant_call_version_id: str,
        days_remaining: int,
        web_push_opt_in: bool,
    ) -> NotificationRequest:
        if days_remaining < 0:
            raise ValueError("days_remaining must be >= 0")
        return NotificationRequest(
            user_id=user_id,
            watch_id=watch_id,
            grant_call_version_id=grant_call_version_id,
            change_event_id=None,
            notification_type=NotificationType.DEADLINE_REMINDER,
            severity=(
                NotificationSeverity.CRITICAL
                if days_remaining <= 3
                else NotificationSeverity.IMPORTANT
            ),
            title="Blíží se termín podání",
            body=f"Do uzávěrky zbývá {days_remaining} dní.",
            dedupe_base=(
                f"deadline:{watch_id}:{grant_call_version_id}:"
                f"{days_remaining}d"
            ),
            web_push_opt_in=web_push_opt_in,
        )


class DeadlineReminderPlanner:
    def __init__(
        self,
        offsets_days: tuple[int, ...] = (60, 30, 14, 7, 3, 1),
    ) -> None:
        if any(value <= 0 for value in offsets_days):
            raise ValueError("deadline offsets must be positive")
        self.offsets_days = tuple(sorted(set(offsets_days), reverse=True))

    def due(
        self,
        *,
        deadline: date,
        today: date,
        already_sent_offsets: set[int] | frozenset[int] = frozenset(),
    ) -> tuple[int, ...]:
        days = (deadline - today).days
        if days < 0:
            return ()
        if days in self.offsets_days and days not in already_sent_offsets:
            return (days,)
        return ()


class NotificationOutboxConsumer:
    """Creates idempotent channel rows from a logical notification request."""

    def __init__(self, repository: InMemoryNotificationRepository) -> None:
        self.repository = repository

    def consume(
        self,
        request: NotificationRequest,
        *,
        now: datetime | None = None,
    ) -> tuple[Notification, ...]:
        notifications = [
            self.repository.create(
                request,
                NotificationChannel.IN_APP,
                now=now,
            )
        ]
        if request.web_push_opt_in:
            notifications.append(
                self.repository.create(
                    request,
                    NotificationChannel.WEB_PUSH,
                    now=now,
                )
            )
        return tuple(notifications)


class NotificationDispatcher:
    def __init__(
        self,
        repository: InMemoryNotificationRepository,
        *,
        web_push_provider: WebPushProvider | None = None,
    ) -> None:
        self.repository = repository
        self.web_push_provider = web_push_provider

    def dispatch(
        self,
        notification: Notification,
        *,
        subscription: WebPushSubscription | None = None,
    ) -> Notification:
        if notification.channel is NotificationChannel.IN_APP:
            return self.repository.mark_sent(notification.id)

        if (
            self.web_push_provider is None
            or subscription is None
            or not subscription.active
        ):
            return self.repository.mark_failed(
                notification.id,
                "WEB_PUSH_NOT_AVAILABLE",
            )

        result = self.web_push_provider.send(
            subscription,
            PushPayload(
                notification_id=notification.id,
                title=notification.title,
                body=notification.body,
                data={"notification_id": notification.id},
            ),
        )
        if result.delivered:
            return self.repository.mark_sent(notification.id)
        return self.repository.mark_failed(
            notification.id,
            result.error_code or "WEB_PUSH_DELIVERY_FAILED",
        )


def _change_title(change_type: ChangeType) -> str:
    return {
        ChangeType.DEADLINE_CHANGED: "Změnil se termín výzvy",
        ChangeType.FUNDING_CHANGED: "Změnily se podmínky financování",
        ChangeType.BUDGET_CHANGED: "Změnily se finanční limity projektu",
        ChangeType.APPLICANT_RULE_CHANGED: "Změnily se podmínky pro žadatele",
        ChangeType.STATUS_CHANGED: "Změnil se stav výzvy",
        ChangeType.REQUIREMENT_CHANGED: "Změnily se požadavky výzvy",
        ChangeType.SUPPORTED_ACTIVITY_CHANGED: "Změnily se podporované aktivity",
        ChangeType.DOCUMENT_CHANGED: "Byl změněn dokument výzvy",
        ChangeType.OTHER: "Výzva byla aktualizována",
    }[change_type]


def _change_body(event: ChangeEvent) -> str:
    if _is_scalar(event.old_value) and _is_scalar(event.new_value):
        return f"{event.old_value} → {event.new_value}"
    return (
        "Podmínky výzvy byly aktualizovány. "
        "Otevřete detail a zkontrolujte konkrétní změnu."
    )


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _stable_id(value: str) -> str:
    return "ntf_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("notification timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)
