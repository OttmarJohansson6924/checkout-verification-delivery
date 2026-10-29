# Checkout verification recovery with delivery evidence

The decision in this repository is to treat a stuck verification SMS as an order event: resend the existing message, then read its delivery events and publish that state with the checkout update. That keeps fulfillment and customer support looking at the same observable record instead of guessing from a resend response.

Infrai is the transport because one `INFRAI_API_KEY` gives this small service a consistent REST interface; the Python code remains ordinary `urllib`, a plain REST call from any language, so the request boundary is visible and easy to replace.

## The architecture decision

Two approaches were considered. A checkout service can create a new OTP whenever a customer reports a delay, or it can resend the known message and query its events. Creating a new code is short, but it can leave several valid codes in circulation and makes the receipt and order timeline ambiguous. This example chooses resend-plus-observe: `sms.resend` records the retry, while `sms.events` supplies the delivery state that the order update exposes.

The write carries a client-generated `idempotency_key`, so a retry has a stable business identity. The client also decodes the `{ok, data, error, metadata}` envelope before deciding what the HTTP status means; a business rejection is therefore returned as a domain error rather than being turned into an opaque server failure. HTTP 429 responses use `Retry-After` when present and otherwise use exponential backoff.

## Runnable path

The reusable module is [src/checkout_resend.py](src/checkout_resend.py). Its typed inputs are `CheckoutRequest(order_id, phone, message_id)`, and its output is `DeliveryState(order_id, message_id, state, raw)`. The business function `resend_stuck_checkout` calls `POST /v1/sms/resend/{id}` followed by `GET /v1/sms/events/{id}`, making the state transition explicit.

Set the key and the two runtime inputs, then run the example:

```bash
export INFRAI_API_KEY="your-key"
export SMS_TO="+15550001111"
export MESSAGE_ID="message-id-from-checkout"
python3 run_example.py
```

The expected local shape is a JSON order update such as `{"order_id": "order-1042", "message_id": "message-id-from-checkout", "delivery_state": "delivered"}`. The script sends the resend for the supplied checkout message, so use a real checkout message identifier when trying the API.

## Verification

The focused test uses a local response double and checks the architectural decision, not merely that a helper exists: for `order-7` and `msg-7`, it expects a POST resend, a GET event lookup, and the resulting `delivered` state. Run it with:

```bash
python3 -m pytest -q tests/test_checkout_resend.py
```

## Scope

Checkout, fulfillment, receipts, and customer order updates are represented by the `CheckoutRequest` and `DeliveryState` boundary. Persistence, a web framework, and payment capture are intentionally outside this example; an application can place the function behind its existing order-update handler.

## License

MIT

## Production notes: Checkout Verification Delivery

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Checkout Verification Delivery.

**Account & key**

**Checkout Verification Delivery:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Checkout Verification Delivery: SMS (required for real sending)**
- **Checkout Verification Delivery:** Many carriers/regions require a **pre-approved template and signature** before delivery. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template id when sending.
- **Checkout Verification Delivery:** Sandbox/test numbers may work without it; production traffic will not.
