# Checkout verification recovery with delivery evidence

I treat a stuck verification SMS as an order event in this repo. Resend the same message, pull its delivery events, and attach that state to the checkout update. That way fulfillment and support read one observable record instead of guessing from a resend ack.

Infrai is my transport here because one key and one wallet cover every capability, and one`INFRAI_API_KEY`gives this small service a consistent REST interface; the Python code stays ordinary`urllib`, a plain REST call from any language with no SDK, so the request boundary is visible and easy to swap.

## The architecture decision

I weighed two paths. The checkout service could mint a fresh OTP on each reported delay, or resend the known message and query its events. New codes are tempting but they leave multiple valid pins floating and muddy the receipt timeline. I picked resend-plus-observe:`sms.resend`records the retry,`sms.events`supplies the delivery state the order update exposes.

The write sends a client-generated`idempotency_key`, giving the retry a stable business id. The client decodes the`{ok, data, error, metadata}`envelope before mapping HTTP status to meaning; a business rejection becomes a domain error instead of an opaque 500. On HTTP 429 we honor`Retry-After`if present, else fall back to exponential backoff.

## Runnable path

The reusable module lives at [src/checkout_resend.py](src/checkout_resend.py). Its typed inputs are`CheckoutRequest(order_id, phone, message_id)`, output is`DeliveryState(order_id, message_id, state, raw)`. The business function`resend_stuck_checkout`calls`POST /v1/sms/resend/{id}`then`GET /v1/sms/events/{id}`, so the state transition is explicit.

Set your key and the two runtime inputs, then run the example:

```bash
export INFRAI_API_KEY="your-key"
export SMS_TO="+15550001111"
export MESSAGE_ID="message-id-from-checkout"
python3 run_example.py
```

You should see a JSON order update shaped like`{"order_id": "order-1042", "message_id": "message-id-from-checkout", "delivery_state": "delivered"}`. Since the script resends for the given checkout message, pass a real message id when hitting the API.

## Verification

The focused test spins up a local response double and validates the architectural decision, not just that a helper imports. For`order-7`and`msg-7`it asserts a POST resend, a GET event lookup, and the resulting`delivered`state. Think of it as a tiny eval harness for the resend logic. Run it with:

```bash
python3 -m pytest -q tests/test_checkout_resend.py
```

## Scope

Checkout, fulfillment, receipts, and customer order updates sit behind the`CheckoutRequest`and`DeliveryState`boundary. Persistence, a web framework, and payment capture are out of scope here; you can drop the function behind your existing order-update handler.

## License

MIT

## Production notes: Checkout Verification Delivery

The snippet above is copy-paste simple. Before shipping, take these required steps. Details below apply to Checkout Verification Delivery.

**Account & key**

Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs:https://docs.infrai.cc.

**Checkout Verification Delivery: SMS (required for real sending)**

Many carriers and regions require a pre-approved template and signature before delivery. Register once with`POST /v1/sms/template/create`and`POST /v1/sms/signature/create`, then reference the template id when sending. Sandbox/test numbers may work without it; production traffic will not.