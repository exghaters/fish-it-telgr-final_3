"""Iteration 22 — join button in a BUSY group.

Real failure: @GCBLACKPEARL (VIP) floods with other players' messages, and the
join is a URL deep-link button (t.me/<bot>?start=daftar...). The button is not
in the immediate message and gets pushed down by chatter. _join_group_button
now scans a wide window and recognises the start-deeplink to our bot.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from automation_engine import AutomationRunner
from models import AutomationConfig


class Btn:
    def __init__(self, text, url=None):
        self.text = text
        self.url = url


class Msg:
    def __init__(self, mid, rows=None, raw_text=""):
        self.id = mid
        self.buttons = rows
        self.raw_text = raw_text

    async def click(self, text=None):
        return MagicMock()


class Client:
    def __init__(self, id_msg, recent):
        self._id_msg = id_msg
        self._recent = recent

    async def get_messages(self, group, ids=None):
        return self._id_msg

    async def iter_messages(self, group, limit=50):
        for m in self._recent[:limit]:
            yield m


class UT:
    def __init__(self, client):
        self.client = client
        self.sent = []

    async def send_command(self, chat, text):
        self.sent.append((chat, text))


def _cfg(**o):
    base = dict(user_id="u1", mode="group", group_username="@GCBLACKPEARL",
                bot_username="@fish_it_vip_bot", join_button_text="Daftar Mancing")
    base.update(o)
    return AutomationConfig(**base)


def _runner(ut):
    r = AutomationRunner("u1")
    r._get_client = AsyncMock(return_value=ut)
    r._event = AsyncMock()
    return r


def test_deeplink_button_buried_under_group_noise():
    async def run():
        # PENDAFTARAN message itself carries no button:
        pend = Msg(1000, rows=None, raw_text="🎣 PENDAFTARAN DIBUKA\n💎 VIP GROUP")
        # 40 noise messages then the real join deep-link button message on top.
        noise = [Msg(900 + i, rows=None, raw_text="⏱️ Sisa waktu 00:%02d" % i)
                 for i in range(40)]
        join = Msg(
            1001,
            rows=[[Btn("✅ Daftar Mancing",
                       url="https://t.me/fish_it_vip_bot?start=daftar2_-1004336696512")]],
            raw_text="")
        recent = [join] + noise  # iter_messages yields newest first
        ut = UT(Client(pend, recent))
        r = _runner(ut)
        method = await asyncio.wait_for(
            r._join_group_button(_cfg(), "@GCBLACKPEARL", 1000), timeout=10)
        assert method == "deeplink", method
        assert ("@fish_it_vip_bot", "/start daftar2_-1004336696512") in ut.sent, ut.sent
    asyncio.run(run())


def test_deeplink_recognized_by_target_bot_even_without_label_match():
    async def run():
        pend = Msg(2000, rows=None, raw_text="PENDAFTARAN DIBUKA")
        # Label is just an emoji (no 'daftar'/'mancing'), but URL targets our bot.
        join = Msg(2001, rows=[[Btn("✅ Gabung",
                    url="https://t.me/fish_it_vip_bot?start=daftar2_-100999")]])
        ut = UT(Client(pend, [join]))
        r = _runner(ut)
        method = await asyncio.wait_for(
            r._join_group_button(_cfg(), "@GCBLACKPEARL", 2000), timeout=10)
        assert method == "deeplink", method
        assert ("@fish_it_vip_bot", "/start daftar2_-100999") in ut.sent, ut.sent
    asyncio.run(run())


def test_unrelated_deeplink_to_other_bot_is_ignored():
    async def run():
        pend = Msg(3000, rows=None, raw_text="PENDAFTARAN DIBUKA")
        # An ad button to a DIFFERENT bot with no daftar/mancing label -> ignore.
        ad = Msg(3001, rows=[[Btn("🎁 Promo", url="https://t.me/some_ad_bot?start=xyz")]])
        ut = UT(Client(pend, [ad]))
        r = _runner(ut)
        method = await asyncio.wait_for(
            r._join_group_button(_cfg(), "@GCBLACKPEARL", 3000), timeout=30)
        assert method is None, method
        assert ut.sent == [], ut.sent
    asyncio.run(run())
