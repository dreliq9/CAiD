import pytest
import caid


def test_preview_returns_image_or_none(box_shape):
    """Preview may return None in headless CI. Either result is acceptable."""
    result = caid.preview(box_shape)
    if result is not None:
        assert result.size == (512, 512)


def test_preview_multi_returns_image_or_none(box_shape, cylinder_shape):
    result = caid.preview_multi(
        [box_shape, cylinder_shape],
        colors=[(255, 0, 0, 255), (0, 0, 255, 255)],
    )
    if result is not None:
        assert result.size == (512, 512)


def test_preview_custom_size(box_shape):
    result = caid.preview(box_shape, size=(256, 256))
    if result is not None:
        assert result.size == (256, 256)


def test_preview_views(box_shape):
    for view in ("iso", "top", "front", "right"):
        result = caid.preview(box_shape, view=view)
        # Just confirm it doesn't crash
