import json

from src.checkout_resend import CheckoutRequest, InfraiSms, resend_stuck_checkout


class FakeResponse:
    status = 200

    def __init__(self, data):
        self.data = json.dumps({"ok": True, "data": data}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.data


def test_resend_then_delivery_state_becomes_order_update():
    calls = []

    def opener(request):
        calls.append((request.method, request.full_url, json.loads(request.data)))
        if request.full_url.endswith("/resend/msg-7"):
            return FakeResponse({"message_id": "msg-7"})
        return FakeResponse({"state": "delivered"})

    client = InfraiSms(key="test-key", opener=opener)
    result = resend_stuck_checkout(CheckoutRequest("order-7", "+15550001111", "msg-7"), client)

    assert result.state == "delivered"
    assert calls[0][0] == "POST"
    assert calls[0][2]["message_id"] == "msg-7"
    assert calls[1][0] == "GET"
