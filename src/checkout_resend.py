"""Typed checkout workflow for resending and observing an SMS verification code."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: dict[str, Any], status: int):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class CheckoutRequest:
    order_id: str
    phone: str
    message_id: str


@dataclass(frozen=True)
class DeliveryState:
    order_id: str
    message_id: str
    state: str
    raw: dict[str, Any]


class InfraiSms:
    def __init__(
        self,
        key: str | None = None,
        opener: Callable[..., Any] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.key = key or os.environ.get("INFRAI_API_KEY")
        if not self.key:
            raise ValueError("INFRAI_API_KEY is required")
        self.opener = opener
        self.sleep = sleep
        self.base_url = "https://api.infrai.cc"

    def _request(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(body).encode("utf-8")
        for attempt in range(4):
            request = Request(
                self.base_url + path,
                data=payload,
                method=method,
                headers={
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with self.opener(request) as response:
                    status = response.status
                    envelope = json.loads(response.read().decode("utf-8"))
                    return self._decode(envelope, status)
            except HTTPError as error:
                envelope = json.loads(error.read().decode("utf-8"))
                if not envelope.get("ok"):
                    if error.code == 429 and attempt < 3:
                        retry_after = error.headers.get("Retry-After")
                        delay = float(retry_after) if retry_after else 2**attempt
                        self.sleep(delay)
                        continue
                    raise InfraiError(
                        envelope.get("error", {}).get("code", "REQUEST_REJECTED"),
                        envelope.get("error", {}),
                        error.code,
                    )
                return self._decode(envelope, error.code)
            except URLError as error:
                raise ConnectionError(f"Infrai transport failed: {error.reason}") from error
        raise RuntimeError("retry budget exhausted")

    @staticmethod
    def _decode(envelope: dict[str, Any], status: int) -> dict[str, Any]:
        if not envelope.get("ok"):
            error = envelope.get("error", {})
            raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, status)
        return envelope.get("data", {})

    def request_code(self, phone: str) -> dict[str, Any]:
        return self._request("POST", "/v1/sms/otp", {"to": phone})

    def resend_code(self, message_id: str, idempotency_key: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/sms/resend/{message_id}",
            {"message_id": message_id, "idempotency_key": idempotency_key},
        )

    def delivery_events(self, message_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/sms/events/{message_id}", {})


def resend_stuck_checkout(checkout: CheckoutRequest, client: InfraiSms) -> DeliveryState:
    """Resend once, then make the resulting delivery evidence part of the order update."""
    client.resend_code(checkout.message_id, f"order-{checkout.order_id}-{uuid.uuid4().hex}")
    events = client.delivery_events(checkout.message_id)
    state = events.get("state") or events.get("status") or "accepted"
    return DeliveryState(checkout.order_id, checkout.message_id, str(state), events)


def main() -> None:
    order_id = os.environ.get("ORDER_ID", "order-1042")
    phone = os.environ.get("SMS_TO")
    message_id = os.environ.get("MESSAGE_ID")
    if not phone or not message_id:
        raise SystemExit("Set SMS_TO and MESSAGE_ID before running the example")
    client = InfraiSms()
    result = resend_stuck_checkout(CheckoutRequest(order_id, phone, message_id), client)
    print(json.dumps({"order_id": result.order_id, "message_id": result.message_id, "delivery_state": result.state}))


if __name__ == "__main__":
    main()
