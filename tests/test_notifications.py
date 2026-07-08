"""
tests/test_notifications.py — Mixtape

Regression tests for rating notifications (Issue #4).

Adding a shared song to a playlist notified the song's sharer, but rating the
song saved the score without ever creating a notification. Rating should notify
the sharer the same way a playlist-add does.
"""

import pytest
from app import create_app, db
from models import User, Song
from services.notification_service import rate_song, get_notifications


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def seed(app):
    with app.app_context():
        sharer = User(username="aaliya", email="aaliya@x")   # shared the song
        rater = User(username="kenji", email="kenji@x")      # rates it
        db.session.add_all([sharer, rater])
        db.session.flush()

        song = Song(title="Golden Hour", artist="Solange K", shared_by=sharer.id)
        db.session.add(song)
        db.session.commit()
        yield {"sharer": sharer, "rater": rater, "song": song}


def test_rating_a_song_notifies_the_sharer(app, seed):
    """Rating someone else's shared song creates a 'song_rated' notification for them."""
    with app.app_context():
        rate_song(seed["rater"].id, seed["song"].id, 5)
        notifs = get_notifications(seed["sharer"].id)
        assert len(notifs) == 1                         # Bug: was 0
        assert notifs[0]["type"] == "song_rated"
        assert "kenji" in notifs[0]["body"]


def test_rating_your_own_song_does_not_notify(app, seed):
    """Rating a song you shared yourself should not generate a self-notification."""
    with app.app_context():
        rate_song(seed["sharer"].id, seed["song"].id, 4)
        notifs = get_notifications(seed["sharer"].id)
        assert notifs == []


def test_re_rating_a_song_still_notifies(app, seed):
    """Updating an existing rating still notifies the sharer (not just the first time)."""
    with app.app_context():
        rate_song(seed["rater"].id, seed["song"].id, 3)
        rate_song(seed["rater"].id, seed["song"].id, 5)
        notifs = get_notifications(seed["sharer"].id)
        assert all(n["type"] == "song_rated" for n in notifs)
        assert len(notifs) == 2
