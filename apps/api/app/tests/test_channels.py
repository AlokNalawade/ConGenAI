from app.models.schemas import ChannelCreate, ChannelUpdate
import pytest


def test_channel_defaults_to_two_nightly_videos():
    channel = ChannelCreate(name="History", slug="history", niche="Weird history")
    assert channel.nightly_video_target == 2
    assert channel.nightly_enabled is True
    assert channel.is_active is True


@pytest.mark.parametrize("target", [0, 21, -1])
def test_channel_target_must_be_between_one_and_twenty(target):
    with pytest.raises(ValueError):
        ChannelCreate(
            name="History", slug="history", niche="Weird history",
            nightly_video_target=target,
        )


def test_channel_update_allows_individual_target():
    update = ChannelUpdate(nightly_video_target=5, nightly_enabled=False)
    assert update.nightly_video_target == 5
    assert update.nightly_enabled is False


def test_channel_slug_is_url_safe():
    with pytest.raises(ValueError):
        ChannelCreate(name="History", slug="Weird History", niche="Weird history")
