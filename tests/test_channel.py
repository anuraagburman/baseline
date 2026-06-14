"""Tests for the channel abstraction: InboundMessage, LocalChannel, TwilioWhatsApp."""

from __future__ import annotations

import pytest

from baseline.channels.base import Channel, InboundMessage
from baseline.channels.local import LocalChannel
from baseline.channels.twilio_whatsapp import TwilioWhatsAppChannel


# --- InboundMessage ---

def test_inbound_message_text_only():
    msg = InboundMessage(user_id="+1234567890", text="hello")
    assert msg.text == "hello"
    assert msg.media_bytes is None
    assert msg.has_media is False


def test_inbound_message_with_media():
    msg = InboundMessage(user_id="u1", text=None,
                         media_url="https://api.twilio.com/foo", media_bytes=b"\xff\xd8")
    assert msg.has_media is True


# --- LocalChannel ---

def test_local_channel_satisfies_protocol():
    assert isinstance(LocalChannel(), Channel)


def test_local_channel_send_text_captured():
    ch = LocalChannel()
    ch.send_text("u1", "Hello, Pranav!")
    assert ch.sent == [("u1", "Hello, Pranav!")]


def test_local_channel_send_buttons_captured():
    ch = LocalChannel()
    ch.send_buttons("u1", "Pick one:", ["Option A", "Option B"])
    assert len(ch.sent) == 1
    assert "Option A" in ch.sent[0][1]


def test_local_channel_clear_resets_sent():
    ch = LocalChannel()
    ch.send_text("u1", "hi")
    ch.clear()
    assert ch.sent == []


# --- TwilioWhatsAppChannel.parse_inbound ---

def test_parse_inbound_text_message():
    form = {
        "From": "whatsapp:+12025551234",
        "Body": "I just had chicken and rice",
        "NumMedia": "0",
    }
    ch = TwilioWhatsAppChannel(account_sid="AC_test", auth_token="tok", from_number="whatsapp:+1")
    msg = ch.parse_inbound(form)
    assert msg.user_id == "whatsapp:+12025551234"
    assert msg.text == "I just had chicken and rice"
    assert not msg.has_media


def test_parse_inbound_media_message():
    form = {
        "From": "whatsapp:+12025551234",
        "Body": "chicken",
        "NumMedia": "1",
        "MediaUrl0": "https://api.twilio.com/media/abc",
        "MediaContentType0": "image/jpeg",
    }
    ch = TwilioWhatsAppChannel(account_sid="AC_test", auth_token="tok", from_number="whatsapp:+1")
    msg = ch.parse_inbound(form)
    assert msg.media_url == "https://api.twilio.com/media/abc"
    assert msg.caption == "chicken"
    assert msg.has_media is True


def test_twiml_response_wraps_reply():
    ch = TwilioWhatsAppChannel(account_sid="AC_test", auth_token="tok", from_number="whatsapp:+1")
    twiml = ch.make_twiml_response("Great, logged your meal!")
    assert "<Message>" in twiml
    assert "Great, logged your meal!" in twiml
    assert "</Response>" in twiml
