"""
tests/test_feed.py — Mixtape

Regression tests for the "Friends Listening Now" feed (Issue #2).

The feed used a rolling 24-hour window, so a friend's listen from late last
night stayed visible until the same time the next day. It should instead only
show listens from *today* (since UTC midnight).

The module clock is patched to a fixed "now" so these tests are deterministic
regardless of when they run.
"""

import pytest
from datetime import datetime, timezone
import services.feed_service as feed_service
from app import create_app, db
from models import User, Song, ListeningEvent, friendships
from services.feed_service import get_friends_listening_now


# 9:00am on Sunday 2024-06-16 — the "this morning" from the bug report.
FIXED_NOW = datetime(2024, 6, 16, 9, 0, 0, tzinfo=timezone.utc)


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED_NOW


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    """Freeze feed_service's view of 'now' at FIXED_NOW."""
    monkeypatch.setattr(feed_service, "datetime", _FixedDateTime)


@pytest.fixture
def seed(app):
    """me is friends with darius (listened 11pm yesterday) and simone (listened today)."""
    with app.app_context():
        me = User(username="nova", email="nova@x")
        darius = User(username="darius", email="darius@x")
        simone = User(username="simone", email="simone@x")
        db.session.add_all([me, darius, simone])
        db.session.flush()

        for friend in (darius, simone):
            db.session.execute(friendships.insert().values(user_id=me.id, friend_id=friend.id))
            db.session.execute(friendships.insert().values(user_id=friend.id, friend_id=me.id))

        song = Song(title="Some Track", artist="Some Artist", shared_by=me.id)
        db.session.add(song)
        db.session.flush()

        # darius: 11:00pm the night before (before today's midnight, but < 24h ago)
        db.session.add(ListeningEvent(
            user_id=darius.id, song_id=song.id,
            listened_at=datetime(2024, 6, 15, 23, 0, 0, tzinfo=timezone.utc),
        ))
        # simone: 8:30am today
        db.session.add(ListeningEvent(
            user_id=simone.id, song_id=song.id,
            listened_at=datetime(2024, 6, 16, 8, 30, 0, tzinfo=timezone.utc),
        ))
        db.session.commit()
        yield {"me": me, "darius": darius, "simone": simone, "song": song}


def test_friend_from_last_night_is_excluded(app, seed):
    """A listen from 11pm yesterday must NOT show up in this morning's feed."""
    with app.app_context():
        feed = get_friends_listening_now(seed["me"].id)
        usernames = [entry["friend"]["username"] for entry in feed]
        assert "darius" not in usernames  # Bug: rolling 24h window kept darius visible


def test_friend_from_today_is_included(app, seed):
    """A listen from earlier today should still appear."""
    with app.app_context():
        feed = get_friends_listening_now(seed["me"].id)
        usernames = [entry["friend"]["username"] for entry in feed]
        assert usernames == ["simone"]
