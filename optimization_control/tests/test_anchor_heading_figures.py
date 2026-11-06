"""Circular display keeps the original physical heading/misalignment relation."""
import unittest
import numpy as np
from optimization_control.maddpg_wind_farm.anchor_heading_figures import relative_angle


class HeadingDisplayTests(unittest.TestCase):
    def test_wind_wrap_is_displayed_continuously(self):
        wind=np.deg2rad([359.8,.1,.3])
        np.testing.assert_allclose(relative_angle(wind,wind[0]),[0.,.3,.5],atol=1e-12)

    def test_common_origin_preserves_misalignment(self):
        wind=np.deg2rad([359.8,.1,.3]); heading=np.deg2rad([359.7,360.,360.2])
        difference=relative_angle(heading,wind[0])-relative_angle(wind,wind[0])
        expected=((heading-wind+np.pi)%(2*np.pi)-np.pi)*180/np.pi
        np.testing.assert_allclose(difference,expected,atol=1e-12)


if __name__=='__main__':unittest.main()
