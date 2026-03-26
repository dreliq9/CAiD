import pytest
from build123d import Vector
import caid


@pytest.fixture
def simple_box():
    return caid.box(10, 20, 30)


@pytest.fixture
def simple_cylinder():
    return caid.cylinder(5, 20)


@pytest.fixture
def box_shape(simple_box):
    return simple_box.unwrap()


@pytest.fixture
def cylinder_shape(simple_cylinder):
    return simple_cylinder.unwrap()


@pytest.fixture
def two_pulley_setup():
    """Two pulleys separated along X axis."""
    return [
        (Vector(0, 0, 0), 10.0),
        (Vector(50, 0, 0), 10.0),
    ]
