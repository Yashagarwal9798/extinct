import pytest

from app import bot, telegram

OWNER = 42


def text_update(update_id, text="hi", sender=OWNER, chat_type="private"):
    return {"update_id": update_id, "message": {
        "message_id": update_id * 10, "date": 1790000000, "text": text,
        "from": {"id": sender}, "chat": {"id": sender, "type": chat_type}}}


def button_update(update_id, data="appr:abc:y", sender=OWNER):
    return {"update_id": update_id, "callback_query": {
        "id": f"cb{update_id}", "data": data, "from": {"id": sender}, "message": {"message_id": 555}}}


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def fake_send(text, *a, **k):
        out.append(("send", text))
        return [1]

    async def fake_answer(cb_id, text=None):
        out.append(("answer", cb_id))

    monkeypatch.setattr(telegram, "send", fake_send)
    monkeypatch.setattr(telegram, "answer_callback", fake_answer)
    return out


async def test_owner_text_is_stored(appdb, sent):
    row = await bot.ingest(text_update(1, "remind me"))
    assert row["kind"] == "text" and row["body"] == "remind me"
    stored = await appdb.fetchone("SELECT * FROM messages")
    assert stored["tg_update_id"] == 1 and stored["direction"] == "in" and not stored["dispatched"]


async def test_duplicate_update_is_ignored(appdb, sent):
    assert await bot.ingest(text_update(1)) is not None
    assert await bot.ingest(text_update(1)) is None
    assert (await appdb.fetchone("SELECT count(*) AS n FROM messages"))["n"] == 1


async def test_strangers_and_groups_are_ignored(appdb, sent):
    assert await bot.ingest(text_update(1, sender=999)) is None
    assert await bot.ingest(text_update(2, chat_type="group")) is None
    assert await bot.ingest(button_update(3, sender=999)) is None
    assert (await appdb.fetchone("SELECT count(*) AS n FROM messages"))["n"] == 0
    assert sent == []  # strangers get no reply at all


async def test_button_is_stored_and_answered(appdb, sent):
    row = await bot.ingest(button_update(5, "appr:abc:y"))
    assert row["kind"] == "button" and row["body"] == "appr:abc:y"
    assert ("answer", "cb5") in sent
    assert (await appdb.fetchone("SELECT tg_message_id FROM messages"))["tg_message_id"] == 555


async def test_non_text_gets_a_polite_reply(appdb, sent):
    upd = text_update(1)
    del upd["message"]["text"]
    upd["message"]["photo"] = [{}]
    assert await bot.ingest(upd) is None
    assert sent == [("send", "I can only read text for now.")]


async def test_rate_limit(appdb, sent, monkeypatch):
    monkeypatch.setattr(bot, "MAX_INBOUND_PER_HOUR", 2)
    await appdb.execute("INSERT INTO messages (direction, body) VALUES ('in', 'a'), ('in', 'b')")
    assert await bot.ingest(text_update(9)) is None


async def test_poll_does_not_advance_until_saved(appdb, sent, monkeypatch):
    """getUpdates offset must only move past an update after it was saved."""
    calls = []
    batches = [[text_update(1), text_update(2)], []]

    async def fake_api(method, **params):
        calls.append((method, params.get("offset")))
        if method == "getUpdates":
            if not batches:
                raise KeyboardInterrupt  # stop the loop
            return batches.pop(0)
        return True

    fails = {"left": 1}
    real_ingest = bot.ingest

    async def flaky_ingest(update):
        if update["update_id"] == 2 and fails["left"]:
            fails["left"] -= 1
            raise ConnectionError("db down")
        return await real_ingest(update)

    async def no_sleep(_):
        return None

    dispatched = []

    async def fake_dispatch(row):
        dispatched.append(row["id"])

    monkeypatch.setattr(telegram, "api", fake_api)
    monkeypatch.setattr(bot, "ingest", flaky_ingest)
    monkeypatch.setattr(bot, "dispatch", fake_dispatch)
    monkeypatch.setattr(bot.asyncio, "sleep", no_sleep)
    with pytest.raises(KeyboardInterrupt):
        await bot.poll_forever()
    offsets = [o for m, o in calls if m == "getUpdates"]
    # 2nd poll confirms both (only after update 2 was finally saved); an empty batch keeps the offset.
    assert offsets == [None, 3, 3]
    assert len(dispatched) == 2
    assert (await appdb.fetchone("SELECT count(*) AS n FROM messages"))["n"] == 2
