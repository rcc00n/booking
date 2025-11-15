"""Staff-facing AI assistant that augments the Telegram bot."""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable

try:
    from openai import (
        APIError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        OpenAI,
        RateLimitError,
    )
except ImportError:  # pragma: no cover - handled at runtime
    OpenAI = None  # type: ignore[assignment]

    class APIError(Exception):  # type: ignore[no-redef]
        pass

    class APITimeoutError(Exception):  # type: ignore[no-redef]
        pass

    class AuthenticationError(Exception):  # type: ignore[no-redef]
        pass

    class BadRequestError(Exception):  # type: ignore[no-redef]
        pass

    class RateLimitError(Exception):  # type: ignore[no-redef]
        pass

from .models import TelegramBotSettings, TelegramChatSubscription, TelegramStaffAssistantSession
from .services import (
    TelegramCommandError,
    describe_payment_status,
    render_appointment_details,
    render_management_summary,
    render_outstanding_overview,
    render_schedule_overview,
    render_today_summary,
)

logger = logging.getLogger(__name__)

_openai_client: OpenAI | None = None
_openai_token_cache: str | None = None

ALLOWED_INTENTS = {
    "general",
    "today_summary",
    "management_summary",
    "schedule",
    "outstanding",
    "appointment_details",
    "payment_status",
    "booking_guidance",
}

STRUCTURED_RESPONSE_INTENTS = {
    "today_summary",
    "management_summary",
    "schedule",
    "outstanding",
    "appointment_details",
    "payment_status",
    "booking_guidance",
    "general",
}


def _format_static_block(title: str, lines: Iterable[str]) -> str:
    safe_title = html.escape(title)
    bullets = [f"• {html.escape(line)}" for line in lines if line]
    body = "\n".join(bullets) if bullets else "—"
    return f"<b>{safe_title}</b>\n{body}"


CAPABILITIES_MESSAGE = _format_static_block(
    "Assistant capabilities",
    (
        "Share today's KPIs and booking snapshot by asking for the daily summary.",
        "Generate management level revenue summaries for any day, week, or month.",
        "List the upcoming schedule (today, tomorrow, this week, next week) optionally with notes.",
        "Highlight unpaid or overdue appointments and their balances.",
        "Show appointment details or payment status whenever you provide an appointment ID.",
    ),
)

BOOKING_GUIDANCE_MESSAGE = _format_static_block(
    "Booking guidance",
    (
        "I cannot create or reschedule appointments directly from this assistant yet.",
        "Use /book in this chat or the admin dashboard to add or edit bookings.",
        "Send me an appointment ID if you need the latest details or payment status afterward.",
    ),
)


APPOINTMENT_ID_PATTERN = re.compile(r"(?:#|id|appointment|appt|booking)\s*(\d{3,})", re.IGNORECASE)
LIMIT_HINT_PATTERNS = [
    re.compile(r"(?:next|show|top|first)\s+(\d{1,2})", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s+(?:appointments?|bookings?|slots?)\b", re.IGNORECASE),
]
BOOKING_VERB_PATTERN = re.compile(r"\b(book|rebook|reschedule)\b", re.IGNORECASE)
SCHEDULE_VERB_PATTERN = re.compile(r"\bschedule\s+(?:a|an|the|new|another|appointments?)\b", re.IGNORECASE)


class StaffAssistantError(RuntimeError):
    """Raised when the AI assistant cannot fulfill a request."""


@dataclass
class AssistantPlan:
    intent: str
    arguments: dict[str, Any]
    rationale: str | None = None


@dataclass
class DatasetEntry:
    label: str
    body: str


@dataclass
class AIConfig:
    enabled: bool
    api_key: str
    model: str
    router_model: str
    max_history: int


def _history_slice(history: Iterable[dict[str, str]], limit: int) -> list[dict[str, str]]:
    limit = max(1, min(20, limit))
    return list(history)[-limit:]


def _load_ai_config() -> AIConfig:
    settings_obj = TelegramBotSettings.load()
    raw = settings_obj.ai_config()
    return AIConfig(
        enabled=bool(raw["enabled"]),
        api_key=str(raw["api_key"] or ""),
        model=str(raw["model"] or "gpt-4o-mini"),
        router_model=str(raw["router_model"] or raw["model"] or "gpt-4o-mini"),
        max_history=int(raw["max_history"] or 8),
    )


def _get_client(config: AIConfig) -> OpenAI | None:
    global _openai_client, _openai_token_cache
    if not config.enabled:
        return None
    if not config.api_key or OpenAI is None:
        return None

    if _openai_client is None or _openai_token_cache != config.api_key:
        _openai_client = OpenAI(api_key=config.api_key)
        _openai_token_cache = config.api_key
    return _openai_client


class StaffAssistant:
    """High-level orchestration for routing and answering staff prompts."""

    ROUTER_PROMPT = (
        "You evaluate staff questions about Malva's operations and pick the best data tool. "
        "Respond ONLY with strict JSON using this schema: "
        '{"intent": "<one of: today_summary, management_summary, schedule, outstanding, '
        'appointment_details, payment_status, booking_guidance, general>", "arguments": { ... }, '
        '"rationale": "<short reason>"} '
        "Use intent 'booking_guidance' when the user asks to create/reschedule appointments. "
        "If the user references a previous answer, infer the missing values from the conversation summary. "
        "Return intent 'general' when no predefined tool fits."
    )

    ASSISTANT_PROMPT = (
        "You are Malva's internal AI assistant embedded in a Telegram bot for staff. "
        "Use the structured data provided to craft concise, factual English answers. "
        "Always cite the relevant insight (e.g. 'Today's KPIs', 'Schedule overview'). "
        "If no live data is available, be transparent and ask clarifying questions when helpful. "
        "Never invent appointment IDs or financial figures. Keep tone professional and proactive."
    )

    def __init__(self, subscription: TelegramChatSubscription):
        self.subscription = subscription
        self.config = _load_ai_config()
        self.model = self.config.model
        self.router_model = self.config.router_model
        self.session, _ = TelegramStaffAssistantSession.objects.get_or_create(subscription=subscription)

    def answer(self, prompt: str) -> str:
        """Generate an assistant reply for the supplied prompt."""

        normalized = (prompt or "").strip()
        if not normalized:
            raise StaffAssistantError("Ask a question after /assistant so I know what to do.")

        client = _get_client(self.config)
        if client is None:
            raise StaffAssistantError(
                "AI assistant is not configured yet. Provide an OpenAI API key and enable it in Telegram bot settings."
            )

        history = _history_slice(self.session.context_log or [], self.config.max_history)
        plan = self._route_intent(client, normalized, history)
        dataset = self._collect_dataset(plan)
        if self._should_bypass_model(plan, dataset):
            reply = self._render_dataset_entries(dataset)
        else:
            reply = self._build_answer(client, normalized, history, dataset, plan)

        self.session.append_context("user", normalized)
        self.session.append_context("assistant", reply)
        self.session.last_error = ""
        self.session.save(update_fields=["context_log", "last_error", "last_interaction_at"])

        return reply

    def _route_intent(
        self,
        client: OpenAI,
        prompt: str,
        history: list[dict[str, str]],
    ) -> AssistantPlan:
        heuristic = self._heuristic_plan(prompt)
        if heuristic:
            return heuristic

        payload_lines: list[str] = []
        if history:
            payload_lines.append("Recent conversation:")
            for entry in history[-4:]:
                payload_lines.append(f"{entry.get('role', 'user')}: {entry.get('text', '')}")
        payload_lines.append(f"New request: {prompt}")
        user_payload = "\n".join(payload_lines)

        try:
            completion = client.chat.completions.create(
                model=self.router_model,
                temperature=0,
                messages=[
                    {"role": "system", "content": self.ROUTER_PROMPT},
                    {"role": "user", "content": user_payload},
                ],
            )
        except (APITimeoutError, RateLimitError) as exc:  # pragma: no cover - network timing
            logger.warning("AI router timeout/rate limit: %s", exc)
            raise StaffAssistantError("AI assistant is busy right now. Please try again in a few seconds.") from exc
        except AuthenticationError as exc:  # pragma: no cover - config issues
            logger.error("Invalid OpenAI credentials: %s", exc)
            raise StaffAssistantError("AI credentials are invalid. Ask an administrator to rotate the API key.") from exc
        except BadRequestError as exc:  # pragma: no cover
            logger.error("Router bad request: %s", exc)
            raise StaffAssistantError("AI assistant could not understand the request. Please rephrase and retry.") from exc
        except APIError as exc:  # pragma: no cover
            logger.error("Router API error: %s", exc)
            raise StaffAssistantError("AI assistant is temporarily unavailable. Try once more shortly.") from exc

        content = (completion.choices[0].message.content or "").strip()
        plan_data: dict[str, Any] | None = None
        if content:
            try:
                plan_data = json.loads(content)
            except json.JSONDecodeError:
                logger.warning("Router response is not JSON: %s", content)

        intent = str((plan_data or {}).get("intent") or "general").lower()
        if intent not in ALLOWED_INTENTS:
            intent = "general"
        arguments = plan_data.get("arguments") if plan_data else {}
        if not isinstance(arguments, dict):
            arguments = {}
        rationale = plan_data.get("rationale") if plan_data else None

        plan = AssistantPlan(intent=intent, arguments=arguments, rationale=rationale)
        if plan.intent == "general":
            fallback = self._heuristic_plan(prompt)
            if fallback:
                plan = fallback
        return plan

    def _collect_dataset(self, plan: AssistantPlan) -> list[DatasetEntry]:
        dataset: list[DatasetEntry] = []

        try:
            if plan.intent == "today_summary":
                dataset.append(DatasetEntry(label="Today's KPIs", body=render_today_summary()))
            elif plan.intent == "management_summary":
                period = plan.arguments.get("period") or "today"
                detailed = bool(plan.arguments.get("detailed"))
                dataset.append(
                    DatasetEntry(label=f"Management summary ({period})", body=render_management_summary(period, detailed=detailed))
                )
            elif plan.intent == "schedule":
                target = plan.arguments.get("target") or "today"
                limit = self._sanitize_int(plan.arguments.get("limit"), default=5, min_value=1, max_value=20)
                include_notes = bool(plan.arguments.get("include_notes"))
                dataset.append(
                    DatasetEntry(
                        label=f"Schedule overview ({target})",
                        body=render_schedule_overview(
                            target,
                            limit=limit,
                            staff_query=self._clean_str(plan.arguments.get("staff_query")),
                            client_query=self._clean_str(plan.arguments.get("client_query")),
                            status_filter=self._clean_str(plan.arguments.get("status_filter")),
                            payment_filter=self._clean_str(plan.arguments.get("payment_filter")),
                            include_notes=include_notes,
                        ),
                    )
                )
            elif plan.intent == "outstanding":
                limit = self._sanitize_int(plan.arguments.get("limit"), default=5, min_value=1, max_value=20)
                dataset.append(
                    DatasetEntry(label="Outstanding balances", body=render_outstanding_overview(limit=limit)),
                )
            elif plan.intent == "appointment_details":
                appointment_id = self._clean_str(plan.arguments.get("appointment_id"))
                if appointment_id:
                    dataset.append(
                        DatasetEntry(label=f"Appointment {appointment_id}", body=render_appointment_details(appointment_id))
                    )
                else:
                    dataset.append(DatasetEntry(label="System notice", body="Missing appointment ID for lookup."))
            elif plan.intent == "payment_status":
                appointment_id = self._clean_str(plan.arguments.get("appointment_id"))
                if appointment_id:
                    dataset.append(
                        DatasetEntry(
                            label=f"Payment status for {appointment_id}",
                            body=describe_payment_status(appointment_id),
                        )
                    )
                else:
                    dataset.append(DatasetEntry(label="System notice", body="Missing appointment ID for payment status."))
            elif plan.intent == "booking_guidance":
                dataset.append(DatasetEntry(label="Booking guidance", body=BOOKING_GUIDANCE_MESSAGE))
            elif plan.intent == "general":
                dataset.append(DatasetEntry(label="Assistant capabilities", body=CAPABILITIES_MESSAGE))
        except TelegramCommandError as exc:
            logger.info("Assistant data fetch failed: intent=%s error=%s", plan.intent, exc)
            dataset.append(DatasetEntry(label="System error", body=str(exc)))

        return dataset

    def _build_answer(
        self,
        client: OpenAI,
        prompt: str,
        history: list[dict[str, str]],
        dataset: list[DatasetEntry],
        plan: AssistantPlan,
    ) -> str:
        messages = [{"role": "system", "content": self.ASSISTANT_PROMPT}]
        for entry in history:
            role = entry.get("role", "user")
            text = entry.get("text", "")
            if role not in {"user", "assistant"}:
                role = "user"
            messages.append({"role": role, "content": text})

        context_lines: list[str] = []
        if dataset:
            for item in dataset:
                context_lines.append(f"[{item.label}]\n{item.body}")
        else:
            context_lines.append("No live data was collected for this prompt.")
        context_blob = "\n\n".join(context_lines)

        user_payload = f"Question: {prompt}\n\nOperational data:\n{context_blob}"

        try:
            completion = client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                messages=[
                    *messages,
                    {"role": "user", "content": user_payload},
                ],
            )
        except (APITimeoutError, RateLimitError) as exc:  # pragma: no cover
            logger.warning("Assistant timeout/rate limit: %s", exc)
            raise StaffAssistantError("AI assistant is overloaded right now. Give it another try shortly.") from exc
        except AuthenticationError as exc:  # pragma: no cover
            logger.error("Invalid OpenAI credentials: %s", exc)
            raise StaffAssistantError("AI credentials are invalid. Ask an administrator to rotate the API key.") from exc
        except BadRequestError as exc:  # pragma: no cover
            logger.error("Assistant bad request: %s", exc)
            raise StaffAssistantError("AI assistant could not generate a response. Please tweak the question.") from exc
        except APIError as exc:  # pragma: no cover
            logger.error("Assistant API error: %s", exc)
            raise StaffAssistantError("AI assistant failed to reach the language model. Try again in a bit.") from exc

        text = (completion.choices[0].message.content or "").strip()
        if not text:
            raise StaffAssistantError("AI assistant returned an empty response. Please rephrase and send again.")
        return text

    @staticmethod
    def _should_bypass_model(plan: AssistantPlan, dataset: list[DatasetEntry]) -> bool:
        return bool(dataset and plan.intent in STRUCTURED_RESPONSE_INTENTS)

    @staticmethod
    def _render_dataset_entries(dataset: list[DatasetEntry]) -> str:
        blocks: list[str] = []
        for item in dataset:
            body = (item.body or "").strip()
            if body.startswith("<b>"):
                blocks.append(body)
                continue
            label = html.escape(item.label or "Insight")
            payload = html.escape(body) if body else "—"
            blocks.append(f"<b>{label}</b>\n{payload}")
        return "\n\n".join(blocks).strip()

    @staticmethod
    def _sanitize_int(value: Any, *, default: int, min_value: int, max_value: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(min_value, min(max_value, parsed))

    @staticmethod
    def _clean_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _extract_limit(self, text: str) -> int | None:
        for pattern in LIMIT_HINT_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            return self._sanitize_int(match.group(1), default=5, min_value=1, max_value=20)
        return None

    @staticmethod
    def _mentions_schedule_request(text: str) -> bool:
        if not text:
            return False
        if re.search(r"\bschedule\b", text):
            return True
        if any(keyword in text for keyword in ("calendar", "agenda", "bookings", "booking list", "schedule overview")):
            return True
        if "appointments" in text and any(token in text for token in ("today", "tomorrow", "week", "month", "next", "this", "have", "upcoming")):
            return True
        return False

    @staticmethod
    def _infer_schedule_target(text: str) -> str:
        normalized = text.replace("-", " ")
        if "next week" in normalized:
            return "next week"
        if "last week" in normalized or "previous week" in normalized:
            return "last week"
        if "next month" in normalized:
            return "next month"
        if "last month" in normalized or "previous month" in normalized:
            return "last month"
        if "this week" in normalized:
            return "week"
        if "this month" in normalized:
            return "month"
        if "tomorrow" in normalized:
            return "tomorrow"
        if "yesterday" in normalized:
            return "yesterday"
        if "week" in normalized:
            return "week"
        if "month" in normalized:
            return "month"
        if "upcoming" in normalized or "later" in normalized or "next" in normalized:
            return "next"
        return "today"

    @staticmethod
    def _infer_period_token(text: str) -> str:
        normalized = text.replace("-", " ")
        if "next week" in normalized:
            return "next week"
        if "last week" in normalized or "previous week" in normalized:
            return "last week"
        if "next month" in normalized:
            return "next month"
        if "last month" in normalized or "previous month" in normalized:
            return "last month"
        if "week" in normalized:
            return "week"
        if "month" in normalized:
            return "month"
        if "yesterday" in normalized:
            return "yesterday"
        if "tomorrow" in normalized:
            return "tomorrow"
        return "today"

    @staticmethod
    def _is_booking_request(text: str) -> bool:
        if not text:
            return False
        if BOOKING_VERB_PATTERN.search(text):
            return True
        if SCHEDULE_VERB_PATTERN.search(text):
            return True
        for phrase in ("create an appointment", "add an appointment", "set up an appointment", "new booking"):
            if phrase in text:
                return True
        return False

    @staticmethod
    def _extract_appointment_id(prompt: str) -> str | None:
        if not prompt:
            return None
        match = APPOINTMENT_ID_PATTERN.search(prompt)
        if match:
            return match.group(1)
        fallback = re.search(r"\b(\d{4,})\b", prompt)
        if fallback:
            return fallback.group(1)
        return None

    def _heuristic_plan(self, prompt: str) -> AssistantPlan | None:
        text = (prompt or "").strip().lower()
        if not text:
            return None

        appointment_id: str | None = None

        def ensure_appointment_id() -> str | None:
            nonlocal appointment_id
            if appointment_id is None:
                appointment_id = self._extract_appointment_id(prompt)
            return appointment_id

        payment_tokens = ("payment", "paid", "deposit", "invoice")
        mentions_payment = any(token in text for token in payment_tokens)
        if mentions_payment and ("status" in text or "confirm" in text or ensure_appointment_id()):
            args: dict[str, Any] = {}
            appt_id = ensure_appointment_id()
            if appt_id:
                args["appointment_id"] = appt_id
            return AssistantPlan(intent="payment_status", arguments=args)

        detail_tokens = (
            "detail",
            "info",
            "client",
            "email",
            "phone",
            "contact",
            "start",
            "time",
            "when",
            "notes",
            "status",
        )
        if any(token in text for token in ("appointment", "booking")) and any(marker in text for marker in detail_tokens):
            args: dict[str, Any] = {}
            appt_id = ensure_appointment_id()
            if appt_id:
                args["appointment_id"] = appt_id
            return AssistantPlan(intent="appointment_details", arguments=args)

        appt_id = ensure_appointment_id()
        if appt_id and any(token in text for token in ("appointment", "booking")) and not mentions_payment:
            return AssistantPlan(intent="appointment_details", arguments={"appointment_id": appt_id})

        if self._is_booking_request(text):
            return AssistantPlan(intent="booking_guidance", arguments={})

        if any(token in text for token in ("outstanding", "overdue", "unpaid", "pending", "owe", "balance", "due")):
            args: dict[str, Any] = {}
            limit = self._extract_limit(text)
            if limit is not None:
                args["limit"] = limit
            return AssistantPlan(intent="outstanding", arguments=args)

        if self._mentions_schedule_request(text):
            args: dict[str, Any] = {"target": self._infer_schedule_target(text)}
            limit = self._extract_limit(text)
            if limit is not None:
                args["limit"] = limit
            if "note" in text:
                args["include_notes"] = True
            return AssistantPlan(intent="schedule", arguments=args)

        if "management" in text or "revenue" in text or "finance" in text or "report" in text:
            period = self._infer_period_token(text)
            detailed = any(token in text for token in ("detail", "breakdown", "per service", "per-service"))
            return AssistantPlan(intent="management_summary", arguments={"period": period, "detailed": detailed})

        if any(token in text for token in ("kpi", "today", "daily", "overview", "summary")) and "management" not in text:
            return AssistantPlan(intent="today_summary", arguments={})

        return None
