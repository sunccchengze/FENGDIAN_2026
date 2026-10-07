"""Team ordering/units, admission rejection and fixed-condition safeguards."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch
from uuid import uuid4
import unittest
import numpy as np
from optimization_control.environments.teammate_pinn_backend import (
    CONTROL_ORDER,OUTPUT_ORDER,unit_factors,validate_positions,validate_run,FixedConditionPredictor,create_predictor)
from optimization_control.maddpg_wind_farm.workflow import build_env
from optimization_control.maddpg_wind_farm.stable_workflow import load_protocol,DEFAULT


class CaptureModel:
    def __call__(self,inputs,training):
        assert training is False
        self.inputs=inputs
        return np.tile([1e6,1e6,1e6,9,8,7],(len(inputs["controls"]),1))


class HandoverTests(unittest.TestCase):
    def predictor(self):
        m=CaptureModel(); p=validate_positions([[0,0,90],[400,0,90],[800,0,90]])
        f=unit_factors(dict(yaw="deg",pitch="deg",rotor_speed="rpm"))
        return m,FixedConditionPredictor(m,p,f,np.tile([-30,0,0],3),np.tile([30,30,20],3),[9,1.5*np.pi,.08])

    def input(self):
        return np.array([[9,1.5*np.pi,.08,.1,.2,.3,.01,.02,.03,.7,.8,.9]],dtype=np.float32)

    def test_batch_interleave_units_and_physical_output(self):
        m,p=self.predictor(); x=np.repeat(self.input(),2,axis=0); y=p(x)
        expected=np.array([.1,.01,.7,.2,.02,.8,.3,.03,.9])*np.tile([180/np.pi,180/np.pi,30/np.pi],3)
        np.testing.assert_allclose(m.inputs["controls"],np.tile(expected,(2,1)),rtol=1e-6)
        self.assertEqual(m.inputs["turbine_positions"].shape,(2,3,3))
        np.testing.assert_array_equal(y[0],[1e6,1e6,1e6,9,8,7])

    def test_varying_ambient_and_out_of_range_controls_rejected(self):
        _,p=self.predictor()
        for col,value in ((0,9.1),(1,0),(2,.1),(3,.8),(9,4)):
            x=self.input(); x[0,col]=value
            with self.assertRaises(ValueError): p(x)
        with self.assertRaises(ValueError): p(np.zeros((1,9)))

    def test_positions_units_and_nonphysical_output_rejected(self):
        for v in ([[None]*3]*3,[[0,0,90],[400,0,90],[900,0,90]],[[0,0,90],[0,400,90],[0,800,90]]):
            with self.assertRaises(ValueError): validate_positions(v)
        with self.assertRaises(ValueError): unit_factors(dict(yaw="degree",pitch="rad",rotor_speed="rpm"))
        _,p=self.predictor(); p.model=lambda inputs,training:np.array([[-1,1,1,9,9,9]])
        with self.assertRaises(ValueError): p(self.input())

    def run_fixture(self):
        root=Path("tmp")/f"pinn_admission_test_{uuid4().hex}"; root.mkdir(parents=True)
        cfg=dict(turbine_positions_m=[[0,0,90],[400,0,90],[800,0,90]],control_units=dict(yaw="deg",pitch="deg",rotor_speed="rpm"),fixed_inlet_wind_speed_m_s=9.)
        report=dict(status="trained_supervised_transfer_requires_accuracy_review",epochs_completed=2,config=cfg,
            control_order=list(CONTROL_ORDER),output_order=list(OUTPUT_ORDER),output_units=["W"]*3+["m/s"]*3,
            constant_controls_in_training=[],negative_test_output_count=0,original_parameters_unchanged=True,
            training_control_min=[-30,0,0]*3,training_control_max=[30,30,20]*3,
            test_metrics={n:dict(RMSE=1,unit="W" if i<3 else "m/s") for i,n in enumerate(OUTPUT_ORDER)})
        def save():
            (root/"config_used.json").write_text(json.dumps(cfg),encoding="utf-8")
            (root/"training_report.json").write_text(json.dumps(report),encoding="utf-8")
        save(); (root/"trained.keras").write_bytes(b"fixture_only_not_a_real_model")
        b=dict(max_test_rmse=[10]*6,fixed_condition=dict(direction_rad=1.5*np.pi,turbulence_intensity=.08),yaw_convention="misalignment_same_sign_as_gamma")
        return root,cfg,report,b,save

    def test_completed_report_requires_quality_and_convention_review(self):
        root,cfg,r,b,save=self.run_fixture(); validate_run(root,b)
        for key in ("max_test_rmse","fixed_condition","yaw_convention"):
            wrong=deepcopy(b); wrong.pop(key)
            with self.assertRaises(ValueError): validate_run(root,wrong)
        r["constant_controls_in_training"]=["yaw1"]; save()
        with self.assertRaises(ValueError): validate_run(root,b)
        r["constant_controls_in_training"]=[]; r["test_metrics"]["P1"]["RMSE"]=100; save()
        with self.assertRaises(ValueError): validate_run(root,b)

    def test_current_delivery_rejected_before_dependency_loading(self):
        path=Path("pinn/PINNs_multi_turbine_wake_simulation-outputchange/OutputChange/iochanged_9ms")
        with self.assertRaisesRegex(ValueError,"untrained.keras is not accepted"):
            create_predictor(dict(run_dir=str(path),script="not_loaded.py"))

    def test_workflow_prevents_double_normalization_and_wrong_geometry(self):
        _,cfg=load_protocol(DEFAULT); _,predictor=self.predictor(); predictor.spacing_m=400
        cfg["plant"].update(kind="pinn",factory="_test_team_backend:create",model_version="fixture_only",layout=dict(spacing_m=400))
        mod=ModuleType("_test_team_backend"); mod.create=lambda b:predictor
        with patch.dict(sys.modules,{"_test_team_backend":mod}):
            build_env(cfg)
            for key,value in (("input_scale",[2]*12),("output_scale",[2]*6)):
                c=deepcopy(cfg); c["plant"][key]=value
                with self.assertRaisesRegex(ValueError,"identity scaling"): build_env(c)
            c=deepcopy(cfg); c["plant"]["layout"]["spacing_m"]=500
            with self.assertRaisesRegex(ValueError,"geometry"): build_env(c)


if __name__=="__main__": unittest.main()
