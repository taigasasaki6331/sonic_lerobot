"""Offline test of tensor isolation, recurrence reset and summary boundaries."""
from pathlib import Path
import copy
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sonic_startup_ablation import mix_tail, segments, infer_condition, CHANNELS, check_result, validate, REFERENCES, MODEL_HASHES, SOURCE_REPORT_SHA, SCOPE, factorial_contrasts


def fixture():
    rows = [dict(seq=i, encoder=[0.]*1247, measured_q=[0.]*29, gripper_width_m=.04, gripper_actuated=False) for i in range(150)]
    outputs = [dict(seq=i, token=[0.]*64, raw_action_isaaclab=[0.]*29, q_target_hardware=[0.]*29,
                    gripper_width_m=.04, gripper_actuated=False) for i in range(150)]
    return dict(schema_version=1, scope=SCOPE, hardware_ready=False, robot_commands_sent=False, g1_connected=False,
        source_report_sha256=SOURCE_REPORT_SHA, model_hashes=MODEL_HASHES, channels=[c[0] for c in CHANNELS], transition_s=.4,
        constants=dict(inverse_order=list(range(29)), defaults=[0.]*29, scales=[1.]*29),
        body_templates=[dict(seq=i,current_tail=[0.]*930,startup_tail=[0.]*930) for i in range(150)],
        references={ref:copy.deepcopy(rows) for ref in REFERENCES},
        expected_baselines={ref:copy.deepcopy(outputs) for ref in (*REFERENCES,'recorded_ik_startup')},
        limits=[dict(name='joint_'+str(i),lower_rad=-1.,upper_rad=1.) for i in range(29)])


class Tests(unittest.TestCase):
    def test_all_masks_switch_only_selected_channels(self):
        current=[float(i) for i in range(930)]; startup=[float(-i-1) for i in range(930)]
        history=[[float(i)]*29 for i in range(10)]
        for mask in range(16):
            result=mix_tail(current,startup,mask,history)
            expected=current.copy()
            for bit,(_,begin,end) in enumerate(CHANNELS):
                if mask & (1<<bit): expected[begin:end]=startup[begin:end]
            expected[610:900]=[v for row in history for v in row]
            self.assertEqual(result,expected)
        self.assertEqual(current[0],0.)
        self.assertEqual(startup[0],-1.)

    def test_recurrence_is_independent_per_condition(self):
        class Worker:
            calls=[]
            def infer(self,row):
                self.calls.append(row['decoder_tail'][610:900])
                value=float(row['seq']+1)
                return dict(seq=row['seq'],token=[0.]*64,raw_action_isaaclab=[value]*29,
                            q_target_hardware=[0.]*29,gripper_width_m=.04,gripper_actuated=False)
        worker=Worker()
        rows=[dict(seq=i,gripper_width_m=.04) for i in range(3)]
        body=[dict(current_tail=[0.]*930,startup_tail=[0.]*930) for _ in rows]
        for mask in (0,15): infer_condition(worker,rows,body,mask)
        self.assertEqual(worker.calls[0],[0.]*290)
        self.assertEqual(worker.calls[3],[0.]*290)
        self.assertEqual(worker.calls[1][-29:],[1.]*29)
        self.assertEqual(worker.calls[2][-58:],[1.]*29+[2.]*29)

    def test_channel_invalid_and_float_overflow(self):
        for mask in (True,-1,16):
            with self.assertRaises(ValueError): mix_tail([0.]*930,[0.]*930,mask,[[0.]*29]*10)
        with self.assertRaises(ValueError): mix_tail([float('nan')]*930,[0.]*930,0,[[0.]*29]*10)
        with self.assertRaises(ValueError): mix_tail([1e39]*930,[0.]*930,0,[[0.]*29]*10)
        with self.assertRaises(ValueError): mix_tail([0.]*930,[0.]*930,0,[[0.]*29]*9)

    def test_ten_period_summary_counts_and_peak(self):
        rows=[dict(q_target_hardware=[float(i)]) for i in range(12)]
        inputs=[dict(measured_q=[0.]) for _ in rows]
        result=segments(rows,inputs,[dict(name='joint',lower_rad=-1.,upper_rad=9.)])
        self.assertEqual(result['first_10']['outside_urdf_counts'],{})
        self.assertEqual(result['after_10']['outside_urdf_counts'],{'joint':2})
        self.assertEqual(result['after_10']['windows'],2)
        self.assertEqual(result['all']['peak_seq'],11)

    def test_width_mode_sequence_and_nonfinite_rejected(self):
        row=dict(seq=0,gripper_width_m=.04)
        good=dict(seq=0,gripper_width_m=.04,gripper_actuated=False,token=[0.]*64,
                  raw_action_isaaclab=[0.]*29,q_target_hardware=[0.]*29)
        for key,value in (('seq',True),('gripper_actuated',True),('gripper_width_m',.05),('token',[float('inf')]*64)):
            output=dict(good); output[key]=value
            with self.assertRaises(ValueError): check_result(output,row)

    def test_zero_entry_is_tensor_padding_not_identity_gravity(self):
        import numpy as np
        from sonic_startup_ablation import startup_tail
        frame=dict(q=[0.]*29,dq=[0.]*29,gyroscope=[0.]*3,quaternion=[1.,0.,0.,0.])
        values=startup_tail([frame],np.arange(29),np.zeros(29))
        self.assertEqual(values[900:927],[0.,0.,1.]*9)
        self.assertEqual(values[927:930],[0.,0.,-1.])
        self.assertEqual(frame['quaternion'],[1.,0.,0.,0.])

    def test_pinned_constants_header_compiles_without_device_code(self):
        from sonic_startup_ablation import constants, ROOT
        from sonic_observation import ObservationBuilder
        header=ROOT/'vendor/GR00T-WholeBodyControl/gear_sonic_deploy/src/g1/g1_deploy_onnx_ref/include/policy_parameters.hpp'
        values=constants(header); builder=ObservationBuilder()
        self.assertEqual(values['defaults'],builder.defaults.tolist())
        for isaac,hardware in enumerate(builder.order):
            self.assertEqual(values['inverse_order'][hardware],isaac)
        self.assertTrue(all(v>0 for v in values['scales']))

    def test_complete_input_and_constant_dimensions_required(self):
        data = fixture(); validate(data)
        for field, value in (('inverse_order',list(range(28))),('inverse_order',[False]+list(range(1,29))),
                             ('scales',[1.]*28),('scales',[0.]*29),('defaults',[0.]*28)):
            bad = copy.deepcopy(data); bad['constants'][field] = value
            with self.assertRaises(ValueError): validate(bad)

    def test_baseline_identity_mode_and_dimensions_required(self):
        data = fixture()
        for kind in ('missing','short','wrong_width','nan','duplicate_limit'):
            bad = copy.deepcopy(data)
            if kind == 'missing': del bad['expected_baselines']['measured_hold']
            if kind == 'short': bad['expected_baselines']['recorded_ik'].pop()
            if kind == 'wrong_width': bad['expected_baselines']['recorded_ik'][0]['gripper_actuated'] = True
            if kind == 'nan': bad['expected_baselines']['recorded_ik'][0]['token'][0] = float('nan')
            if kind == 'duplicate_limit': bad['limits'][0]['name'] = bad['limits'][1]['name']
            with self.assertRaises(ValueError): validate(bad)

    def test_incomplete_condition_rejected_before_worker_call(self):
        with self.assertRaises(ValueError): infer_condition(None,[{}],[],0)

    def test_all_paired_backgrounds_not_just_isolated_channel(self):
        sets = {mask:[dict(q_target_hardware=[float(mask)]) for _ in range(12)] for mask in range(16)}
        contrasts = factorial_contrasts({'fixture':sets})['fixture']
        for bit,(name,_,_) in enumerate(CHANNELS):
            self.assertEqual(len(contrasts[name]['paired_backgrounds']),8)
            self.assertEqual(contrasts[name]['first10_pair_max_min_rad'],float(1<<bit))
            for pair in contrasts[name]['paired_backgrounds']:
                self.assertEqual(pair['with_channel_mask']^pair['without_channel_mask'],1<<bit)
        with self.assertRaises(ValueError): factorial_contrasts({'fixture':{0:sets[0]}})


if __name__=='__main__': unittest.main()
