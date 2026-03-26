from __future__ import annotations
from typing import Any
import math

import numpy as np

from ._backend import get_backend

_DEFAULT_BG = (40, 40, 40)
_DEFAULT_SIZE = (512, 512)


def _bg_to_float(bg: tuple) -> list[float]:
    return [bg[0] / 255.0, bg[1] / 255.0, bg[2] / 255.0, 1.0]


def _camera_pose(view: str, center: np.ndarray, distance: float) -> np.ndarray:
    """Build a 4x4 camera pose matrix for the given view."""
    view_angles = {
        "iso":   (math.radians(45), math.radians(35)),
        "top":   (math.radians(0),  math.radians(90)),
        "front": (math.radians(0),  math.radians(0)),
        "right": (math.radians(90), math.radians(0)),
    }
    azimuth, elevation = view_angles.get(view, view_angles["iso"])

    eye = center + np.array([
        distance * math.cos(elevation) * math.sin(azimuth),
        distance * math.cos(elevation) * math.cos(azimuth),
        distance * math.sin(elevation),
    ])
    return _look_at(eye, center, np.array([0.0, 0.0, 1.0]))


def _look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Build a 4x4 look-at matrix (OpenGL convention: camera looks down -Z)."""
    forward = target - eye
    forward = forward / np.linalg.norm(forward)
    right = np.cross(forward, up)
    if np.linalg.norm(right) < 1e-10:
        up = np.array([0.0, 1.0, 0.0])
        right = np.cross(forward, up)
    right = right / np.linalg.norm(right)
    true_up = np.cross(right, forward)

    pose = np.eye(4)
    pose[:3, 0] = right
    pose[:3, 1] = true_up
    pose[:3, 2] = -forward
    pose[:3, 3] = eye
    return pose


def _tessellate_to_trimesh(shape: Any):
    """Tessellate a CQ shape and return a trimesh.Trimesh with fixed normals."""
    import trimesh

    verts, faces = get_backend().tessellate(shape, tolerance=0.05)
    if len(verts) == 0 or len(faces) == 0:
        return None
    mesh = trimesh.Trimesh(vertices=verts, faces=faces)
    trimesh.repair.fix_normals(mesh)
    return mesh


def _add_camera_and_light(scene, view: str, center: np.ndarray, extent: float):
    """Add camera and directional light to a pyrender scene."""
    import pyrender

    distance = extent * 1.5
    cam = pyrender.PerspectiveCamera(yfov=math.pi / 4.0)
    cam_pose = _camera_pose(view, center, distance)
    scene.add(cam, pose=cam_pose)
    scene.add(pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=3.0), pose=cam_pose)


def preview(
    shape: Any,
    size: tuple[int, int] = _DEFAULT_SIZE,
    view: str = "iso",
    background: tuple = _DEFAULT_BG,
) -> "Image.Image | None":
    try:
        from PIL import Image
        import pyrender

        mesh = _tessellate_to_trimesh(shape)
        if mesh is None:
            return None

        scene = pyrender.Scene(bg_color=_bg_to_float(background))
        scene.add(pyrender.Mesh.from_trimesh(mesh))

        center = (mesh.bounds[0] + mesh.bounds[1]) / 2.0
        extent = np.linalg.norm(mesh.bounds[1] - mesh.bounds[0])
        _add_camera_and_light(scene, view, center, extent)

        renderer = pyrender.OffscreenRenderer(size[0], size[1])
        color, _ = renderer.render(scene)
        renderer.delete()
        return Image.fromarray(color)
    except Exception:
        return None


def preview_multi(
    shapes: list[Any],
    colors: list[tuple] | None = None,
    size: tuple[int, int] = _DEFAULT_SIZE,
    view: str = "iso",
    background: tuple = _DEFAULT_BG,
) -> "Image.Image | None":
    try:
        from PIL import Image
        import pyrender

        scene = pyrender.Scene(bg_color=_bg_to_float(background))
        all_bounds = []

        for i, shape in enumerate(shapes):
            mesh = _tessellate_to_trimesh(shape)
            if mesh is None:
                continue
            all_bounds.append(mesh.bounds)

            if colors and i < len(colors):
                c = colors[i]
                rgba = [c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, (c[3] if len(c) > 3 else 255) / 255.0]
                material = pyrender.MetallicRoughnessMaterial(baseColorFactor=rgba)
                scene.add(pyrender.Mesh.from_trimesh(mesh, material=material))
            else:
                scene.add(pyrender.Mesh.from_trimesh(mesh))

        if not all_bounds:
            return None

        all_bounds = np.array(all_bounds)
        global_min = all_bounds[:, 0, :].min(axis=0)
        global_max = all_bounds[:, 1, :].max(axis=0)
        center = (global_min + global_max) / 2.0
        extent = np.linalg.norm(global_max - global_min)
        _add_camera_and_light(scene, view, center, extent)

        renderer = pyrender.OffscreenRenderer(size[0], size[1])
        color_img, _ = renderer.render(scene)
        renderer.delete()
        return Image.fromarray(color_img)
    except Exception:
        return None
