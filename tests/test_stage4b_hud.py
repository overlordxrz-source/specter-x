"""Team HUD: teammate markers, peer contacts, minimap, arrows, pose badge."""
import numpy as np

from specter.hud.renderer import HUD_H, HUD_W, HudState, render
from specter.hud.team_overlay import (
    PeerContactView,
    TeamOverlayState,
    TeammateView,
    bearing_between,
    contact_from_report_tag,
    offscreen_arrows,
    relative_bearing,
    teammate_from_pose,
)


def _team_state():
    own = np.array([0.0, 0.0, 0.0])
    mates = [
        teammate_from_pose("unit-2", own, [3.0, 4.0, 0.0], "GNSS", 1.2),
        teammate_from_pose("unit-3", own, [-6.0, 1.0, 0.0], "REL", 4.5,
                           behind_wall=True),
    ]
    contacts = [contact_from_report_tag("unit-2", "thermal", 0.8, [10.0, 4.0, 0.0])]
    return TeamOverlayState(own_pos_enu=own, own_yaw_deg=0.0, teammates=mates,
                            contacts=contacts, pose_badge="POSE: GNSS ±1.2m")


def test_bearing_and_relative():
    d, b = bearing_between(np.zeros(3), np.array([10.0, 0.0, 0.0]))
    assert d == 10.0 and b == 90.0  # east of own = 090
    d, b = bearing_between(np.zeros(3), np.array([0.0, 5.0, 0.0]))
    assert d == 5.0 and b == 0.0  # north = 000
    assert relative_bearing(90.0, 0.0) == 90.0
    assert relative_bearing(350.0, 0.0) == -10.0


def test_teammate_labels_carry_wall_flag():
    t = teammate_from_pose("unit-3", np.zeros(3), [-6.0, 1.0, 0.0],
                           behind_wall=True)
    assert "behind wall" in t.label() and t.unit_id in t.label()
    t2 = teammate_from_pose("unit-2", np.zeros(3), [3.0, 4.0, 0.0])
    assert "behind wall" not in t2.label()


def test_peer_contact_src_tag():
    c = contact_from_report_tag("unit-2", "thermal", 0.8, [1, 2, 0])
    assert c.hud_tag == "SRC: unit-2/THERMAL conf 0.80"


def test_arrows_need_heading_and_respect_fov():
    st = _team_state()
    arrows = offscreen_arrows(st)
    kinds = {k for k, _, _ in arrows}
    assert "teammate" in kinds and "contact" in kinds  # side targets outside 35° FOV
    st_no_hdg = TeamOverlayState(own_pos_enu=np.zeros(3), own_yaw_deg=None,
                                 teammates=st.teammates, contacts=st.contacts)
    assert offscreen_arrows(st_no_hdg) == []  # no invented heading, no arrows


def test_render_with_team_draws_panel_minimap_badge():
    img = np.zeros((720, 1280, 3), np.uint8)
    plain = render(img, HudState())
    team = render(img, HudState(team=_team_state()))
    assert team.shape == (HUD_H, HUD_W, 3)
    assert not np.array_equal(plain, team)  # team UI adds pixels
    # minimap region (bottom-left) is non-black once teammates exist
    assert team[HUD_H - 252:HUD_H - 22, 12:242].sum() > 0


def test_render_without_team_unchanged_shape():
    img = np.zeros((720, 1280, 3), np.uint8)
    assert render(img, HudState()).shape == (HUD_H, HUD_W, 3)
