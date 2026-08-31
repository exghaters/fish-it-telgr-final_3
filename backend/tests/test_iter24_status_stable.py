"""Iteration 24 — Telegram status must be STABLE (no client rehydration).

Real bug (production, multi-worker): the account flip-flopped between
"Session aktif" and "Belum terhubung / minta nomor HP". Cause: get_meta
rehydrated a live client per status poll; on multi-worker only ONE worker owns
the session lease, so the others reported "not connected". Fix: status reads a
persisted `authorized` flag from Mongo and never creates a live client.

(DB is mocked so the test is a pure unit test — no motor event-loop coupling.)
"""
import asyncio
from unittest.mock import patch

import telegram_manager as tmod
from telegram_manager import telegram_manager as tm


class _FakeColl:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, query, projection=None):
        d = self.docs.get(query.get("user_id"))
        return dict(d) if d else None


class _FakeDB:
    def __init__(self, docs):
        self.telegram_sessions = _FakeColl(docs)


def test_status_is_dbflag_driven_and_creates_no_client():
    docs = {
        "u_auth": {"user_id": "u_auth", "authorized": True, "phone": "+62",
                   "display_name": "Sam", "api_id": 123, "session_enc": "x"},
        "u_legacy": {"user_id": "u_legacy", "session_enc": "enc",
                     "phone": "+62", "api_id": 1},
        "u_revoked": {"user_id": "u_revoked", "authorized": False,
                      "session_enc": "x", "api_id": 1},
    }

    async def run():
        with patch.object(tmod, "db", _FakeDB(docs)):
            # authorized flag True, no live client -> connected True, NO client made
            m1 = await tm.get_meta("u_auth", rehydrate=True)
            assert m1["connected"] is True, m1
            assert m1["display_name"] == "Sam"
            assert "u_auth" not in tm.users, "status must not create a live client"

            # legacy doc (session present, no `authorized` key) -> connected True
            m2 = await tm.get_meta("u_legacy")
            assert m2["connected"] is True, m2
            assert "u_legacy" not in tm.users

            # session revoked (authorized False) -> connected False
            m3 = await tm.get_meta("u_revoked", rehydrate=True)
            assert m3["connected"] is False, m3

            # no session at all -> connected False
            m4 = await tm.get_meta("u_none")
            assert m4["connected"] is False, m4

    asyncio.run(run())
