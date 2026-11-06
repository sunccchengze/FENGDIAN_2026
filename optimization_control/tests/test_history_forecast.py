"""Forecast contracts; these tests make no PINN or mock-plant queries."""
import io
import unittest
import numpy as np
from optimization_control.maddpg_wind_farm.history_wind_forecast import RidgeForecast,features,fit


class HistoryForecastTests(unittest.TestCase):
    def test_cold_start_padding_and_periodic_features(self):
        a=np.array([[9.,0.,.08]],np.float32);b=np.repeat(a,32,axis=0)
        np.testing.assert_array_equal(features(a),features(b))
        a[:,1]=np.float32(2*np.pi-1e-6);x=features(a)
        self.assertLess(abs(x[1]),2e-6);self.assertAlmostEqual(x[2],1.,places=10)
        self.assertEqual(x.shape,(96,))
    def test_domain_clipping_and_ti_constant(self):
        target=np.zeros(36);target[::3]=100.
        m=RidgeForecast(np.zeros(96),np.ones(96),target,np.zeros((96,36)))
        a,d=m.predict([[9.,6.28,.08]])
        np.testing.assert_array_equal(a[:,0],np.full(12,10.5));self.assertTrue(all(d['speed_clipped']))
        np.testing.assert_array_equal(a[:,2],np.full(12,np.float32(.08)))
        self.assertTrue(np.all((a[:,1]>=0)&(a[:,1]<=2*np.pi)))
    def test_fit_serialization_and_future_prefix_invariance(self):
        t=np.arange(129);series=[np.column_stack((9+.1*np.sin(t/8+i),np.mod(.03*np.sin(t/30+i),2*np.pi),np.full(129,.08))) for i in (0,1,2)]
        m,info=fit(series);self.assertEqual(info['fit_windows'],351)
        with io.BytesIO() as buffer:
            m.save(buffer);buffer.seek(0);loaded=RidgeForecast.load(buffer)
        old=[x.copy() for x in (m.mean,m.scale,m.target_mean,m.coefficients)]
        changed=series[0].copy();changed[33:]=[7.5,1.,.04]
        np.testing.assert_array_equal(m.predict(series[0][:33])[0],loaded.predict(changed[:33])[0])
        for before,after in zip(old,(m.mean,m.scale,m.target_mean,m.coefficients)):np.testing.assert_array_equal(before,after)


if __name__=='__main__':unittest.main()
