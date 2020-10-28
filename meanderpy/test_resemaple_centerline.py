import meanderpy.meanderpy as mp
import meanderpy.meanderpyp as mpp
import meanderpy.cases as cases

import numpy as np
from numpy.testing import assert_almost_equal
import matplotlib.pyplot as plt

def test_sine_no_slope():
	self = cases.ChannelSineNoSlope()

	ONES = np.ones(len(self.x))
	base_x, base_y, base_z, _, _, _, _, _ = mp.resample_centerline(self.x,self.y,self.z,10)
	test_x, test_y, test_z, _, _, _, _, _, _, _ = mpp.resample_centerline(self.x,self.y,self.z,self.W*ONES, self.D*ONES, 10)

	assert_almost_equal(base_x, test_x)
	assert_almost_equal(base_y, test_y)
	assert_almost_equal(base_z, test_z)

def test_sine_constant_slope():
	self = cases.ChannelSineConstantSlope()

	ONES = np.ones(len(self.x))
	base_x, base_y, base_z, _, _, _, _, _ = mp.resample_centerline(self.x,self.y,self.z,10)
	test_x, test_y, test_z, _, _, _, _, _, _, _ = mpp.resample_centerline(self.x,self.y,self.z,self.W*ONES, self.D*ONES, 10)

	assert_almost_equal(base_x, test_x)
	assert_almost_equal(base_y, test_y)
	assert_almost_equal(base_z, test_z)

def test_scattered_sine_no_slope():
	self = cases.ChannelScatteredSineNoSlope()

	ONES = np.ones(len(self.x))
	base_x, base_y, base_z, _, _, _, _, _ = mp.resample_centerline(self.x,self.y,self.z,10)
	test_x, test_y, test_z, _, _, _, _, _, _, _ = mpp.resample_centerline(self.x,self.y,self.z,self.W*ONES, self.D*ONES, 10)

	assert_almost_equal(base_x, test_x)
	assert_almost_equal(base_y, test_y)
	assert_almost_equal(base_z, test_z)

def test_scattered_sine_constant_slope():
	self = cases.ChannelScatteredSineConstantSlope()

	ONES = np.ones(len(self.x))
	base_x, base_y, base_z, _, _, _, _, _ = mp.resample_centerline(self.x,self.y,self.z,10)
	test_x, test_y, test_z, _, _, _, _, _, _, _ = mpp.resample_centerline(self.x,self.y,self.z,self.W*ONES, self.D*ONES, 10)

	assert_almost_equal(base_x, test_x)
	assert_almost_equal(base_y, test_y)
	assert_almost_equal(base_z, test_z)