import numpy as np
import pytest

from specter.fusion.coordinate_frames import (
    R_CAM_BODY, FrameGraph, PinholeCamera, Transform, project_points, quat_to_matrix,
    rot_z, rpy_to_matrix,
)

CAM = PinholeCamera(fx=1000, fy=1000, cx=640, cy=400, width=1280, height=800)


def test_principal_point_projection():
    uv, ok = CAM.project(np.array([[0, 0, 5.0]]))
    assert ok[0]
    np.testing.assert_allclose(uv[0], [640, 400])


def test_known_offset_projection():
    # 1 m right, 0.5 m down, 10 m ahead -> u = 1000*0.1+640, v = 1000*0.05+400
    uv, ok = CAM.project(np.array([[1.0, 0.5, 10.0]]))
    np.testing.assert_allclose(uv[0], [740, 450])
    assert ok[0]


def test_behind_camera_and_out_of_image_invalid():
    uv, ok = CAM.project(np.array([[0, 0, -1.0], [100.0, 0, 1.0]]))
    assert not ok[0] and np.isnan(uv[0]).all()
    assert not ok[1] and np.isfinite(uv[1]).all()


def test_unproject_roundtrip():
    pts = np.array([[0.3, -0.2, 4.0], [-1.0, 0.7, 12.0]])
    uv, _ = CAM.project(pts)
    np.testing.assert_allclose(CAM.unproject(uv, pts[:, 2]), pts, atol=1e-9)


def test_from_fov():
    cam = PinholeCamera.from_fov(1280, 800, 90.0)
    assert cam.fx == pytest.approx(640.0)


def test_transform_inverse_and_compose():
    T = Transform(rpy_to_matrix(0.1, -0.2, 0.7), [1.0, 2.0, 3.0])
    p = np.array([[0.5, -0.5, 2.0], [3, 4, 5]])
    np.testing.assert_allclose(T.inverse().apply(T.apply(p)), p, atol=1e-12)
    I = T @ T.inverse()
    np.testing.assert_allclose(I.as_matrix(), np.eye(4), atol=1e-12)
    np.testing.assert_allclose(Transform.from_dict(T.to_dict()).as_matrix(), T.as_matrix())


def test_rejects_non_rotation():
    with pytest.raises(ValueError):
        Transform(np.diag([1, 1, -1]), [0, 0, 0])


def test_body_point_ahead_projects_to_center():
    # Point 5 m straight ahead in body frame (x fwd) -> camera centre.
    T_cam_body = Transform(R_CAM_BODY, [0, 0, 0])
    uv, ok = project_points(np.array([[5.0, 0, 0]]), T_cam_body, CAM)
    assert ok[0]
    np.testing.assert_allclose(uv[0], [640, 400])
    # Point to the left in body (+y) lands left of centre in image.
    uv, _ = project_points(np.array([[5.0, 1.0, 0]]), T_cam_body, CAM)
    assert uv[0, 0] < 640


def test_frame_graph_chain():
    g = FrameGraph()
    g.add("body", "cam_nv", Transform(rot_z(0.3), [0.1, 0, 0]))
    g.add("body", "radar", Transform(np.eye(3), [0.05, 0.02, -0.03]))
    T = g.lookup("cam_nv", "radar")  # radar -> body -> cam
    expected = g.lookup("cam_nv", "body") @ g.lookup("body", "radar")
    np.testing.assert_allclose(T.as_matrix(), expected.as_matrix(), atol=1e-12)


def test_quaternion():
    a = 0.4
    R = quat_to_matrix(np.cos(a / 2), 0, 0, np.sin(a / 2))
    np.testing.assert_allclose(R, rot_z(a), atol=1e-12)
