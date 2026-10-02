"""Saved-only raw quaternion / heading / initial-pose contract audit; no inference or IO."""
import argparse
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonic_startup_ablation import ROOT, SOURCE_HASHES, SOURCE_REPORT_SHA, sha, save
from sonic_process import strict_message
from sonic_observation import ObservationBuilder
from verify_online_record import verify, checked_file
from audit_motion_record import joint_limits

ORACLE = Path(__file__).with_name('sonic_startup_math_oracle.cpp')
INCLUDE = ROOT/'vendor/GR00T-WholeBodyControl/gear_sonic_deploy/src/g1/g1_deploy_onnx_ref/include'


def normalized(values):
    values = np.asarray(values, dtype=float)
    if (values.ndim != 2 or values.shape[1] != 4 or not np.isfinite(values).all()
            or np.any(np.linalg.norm(values, axis=1) < .5)):
        raise ValueError('Invalid real quaternion batch')
    return values / np.linalg.norm(values, axis=1)[:, None]


def oracle(values):
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or values.shape[1] != 16 or not len(values) or not np.isfinite(values).all():
        raise ValueError('Invalid oracle batch')
    for start in range(0, 16, 4): normalized(values[:, start:start+4])
    if sha(INCLUDE/'math_utils.hpp') != SOURCE_HASHES['include/math_utils.hpp']:
        raise ValueError('Pinned upstream math changed')
    with tempfile.TemporaryDirectory(prefix='sonic-startup-contract-') as directory:
        binary = str(Path(directory)/'oracle')
        subprocess.run(['g++', '-std=c++17', '-O2', '-I'+str(INCLUDE), str(ORACLE), '-o', binary],
                       check=True, timeout=30)
        result = subprocess.run([binary], input='\n'.join(' '.join(map(str, row)) for row in values),
                                text=True, capture_output=True, check=True, timeout=10)
    output = np.array([[float(v) for v in line.split()] for line in result.stdout.splitlines()])
    if output.shape != (len(values), 19) or not np.isfinite(output).all():
        raise ValueError('Incomplete/nonfinite oracle output')
    return output


def compare_quaternions(body, references):
    """First saved CONTROL-like endpoint as heading origin; not actual INIT/reset."""
    body = np.asarray(body, dtype=float); references = np.asarray(references, dtype=float)
    b = normalized(body); r = normalized(references)
    if body.shape != references.shape: raise ValueError('Quaternion count mismatch')
    raw = np.concatenate([body, references, np.tile(body[0], (len(body), 1)),
                          np.tile(references[0], (len(body), 1))], axis=1)
    unit = np.concatenate([b, r, np.tile(b[0], (len(body), 1)), np.tile(r[0], (len(body), 1))], axis=1)
    outputs = oracle(np.concatenate([raw, unit])); original, normalized_result = np.split(outputs, 2)
    float_difference = lambda a, c: float(np.max(abs(a.astype(np.float32).astype(float)-c.astype(np.float32).astype(float))))
    return dict(
        body_quaternion_norm_error_max=float(np.max(abs(np.linalg.norm(body, axis=1)-1))),
        reference_quaternion_norm_error_max=float(np.max(abs(np.linalg.norm(references, axis=1)-1))),
        raw_vs_normalized_orientation6_max_abs_difference=float(np.max(abs(original[:, :6]-normalized_result[:, :6]))),
        raw_vs_normalized_orientation6_float32_max_abs_difference=float_difference(original[:, :6], normalized_result[:, :6]),
        raw_vs_normalized_gravity_max_abs_difference=float(np.max(abs(original[:, 12:15]-normalized_result[:, 12:15]))),
        raw_vs_normalized_gravity_float32_max_abs_difference=float_difference(original[:, 12:15], normalized_result[:, 12:15]),
        initial_heading_delta_wxyz=normalized_result[0, 15:19].tolist(),
        initial_heading_delta_angle_rad=float(2*math.atan2(normalized_result[0, 18], normalized_result[0, 15])),
        heading_aligned_vs_zero_offset_orientation6_float32_max_abs_difference=float_difference(
            normalized_result[:, :6], normalized_result[:, 6:12])), normalized_result


def audit(report_path):
    report_path = Path(report_path)
    if sha(report_path) != SOURCE_REPORT_SHA: raise ValueError('Unexpected source record')
    base = INCLUDE.parent; sources = {str(base/name): digest for name, digest in SOURCE_HASHES.items()}
    for path, digest in sources.items():
        if sha(path) != digest: raise ValueError('Pinned source changed: '+path)
    integrity = verify(report_path); report = strict_message(report_path.read_bytes())
    if len(report['outputs']) != 150: raise ValueError('Require complete saved 150 periods')
    builder = ObservationBuilder(); endpoints = []; references = []; histories = []; q = []; times = []; ticks = []
    expected_orientation = []; expected_gravity = []; captures = {}
    for output in report['outputs']:
        body = strict_message(checked_file(report_path.parent, output['body_input_record'], r'body-[0-9]{4}\.json'))['body_history']
        policy = report['policy_records'][output['policy_seq']]
        index = output['policy_seq']
        if index not in captures:
            captures[index] = strict_message(checked_file(report_path.parent, policy['capture'], r'capture-[0-9]{4}\.json'))
        reference = captures[index]['g1_state']['quaternion']
        endpoints.append(body[-1]['quaternion']); references.append(reference)
        histories.extend(frame['quaternion'] for frame in body)
        q.append(body[-1]['q'][:29]); times.append(body[-1]['receive_monotonic_s']); ticks.append(body[-1]['tick'])
        unit_body = normalized([frame['quaternion'] for frame in body]); unit_ref = normalized([reference])[0]
        expected_orientation.append(builder.encoder(np.tile(policy['ik']['q_reference_hardware'], (10, 1)),
            np.zeros((10, 29)), np.tile(unit_ref, (10, 1)), unit_body[-1])[584:590])
        expected_gravity.extend(builder.decoder_tail([frame['q'][:29] for frame in body],
            [frame['dq'][:29] for frame in body], [frame['gyroscope'] for frame in body], unit_body,
            np.zeros((10, 29)))[900:930].reshape(10, 3))
    comparison, normalized_endpoints = compare_quaternions(endpoints, references)
    # Audit all 1500 history quaternion uses, not only the 150 endpoints.
    history_comparison, normalized_history = compare_quaternions(histories, np.tile([1., 0., 0., 0.], (len(histories), 1)))
    encoder_error = float(np.max(abs(normalized_endpoints[:, :6].astype(np.float32)-expected_orientation)))
    gravity_error = float(np.max(abs(normalized_history[:, 12:15].astype(np.float32)-expected_gravity)))
    if encoder_error > 2e-7 or gravity_error > 2e-7: raise ValueError('Normalized Python observation disagrees with C++ oracle')
    offsets = abs(np.asarray(q)-builder.defaults); peak = np.unravel_index(np.argmax(offsets), offsets.shape)
    limits = joint_limits(ROOT/'artifacts/models/g1_pika_closed.urdf'); intervals = np.diff(times)
    paths = [report_path, Path(__file__), ORACLE, Path(__file__).with_name('sonic_observation.py'),
             Path(__file__).with_name('sonic_measured_stream.py'), Path(__file__).with_name('prepare_online_ablation.py'),
             Path(__file__).parent/'state_receiver/receive_state.c']
    sources.update({str(path): sha(path) for path in paths})
    return dict(scope='saved_startup_contract_source_and_tensor_audit_not_hardware_acceptance',
        hardware_ready=False, robot_commands_sent=False, g1_connected=False, inference_performed=False,
        source_files=sources, input_integrity=integrity, periods=150, body_quaternion_uses=1500,
        endpoint_reference_comparison=comparison,
        history_gravity_comparison={key:value for key,value in history_comparison.items()
            if key == 'body_quaternion_norm_error_max' or key.startswith('raw_vs_normalized_gravity')},
        normalized_python_vs_cpp_encoder_max_abs_difference=encoder_error,
        normalized_python_vs_cpp_gravity_max_abs_difference=gravity_error,
        body_endpoint_interval_min_s=float(intervals.min()), body_endpoint_interval_max_s=float(intervals.max()),
        body_tick_increments=sorted(set(b-a for a,b in zip(ticks, ticks[1:]))),
        measured_default_pose_offset=dict(first_endpoint_max_rad=float(offsets[0].max()),
            all_endpoints_max_rad=float(offsets[peak]), peak_seq=int(peak[0]), peak_joint=limits[peak[1]]['name']),
        not_reproduced=['Actual upstream INIT/WAIT_FOR_CONTROL transition and ownership',
            'Original motion frame-0 / reinitialize_heading state', 'Support/contact and physical stop',
            'Body reaction to computed actions; hardware sensor frame calibration; DDS CRC verification'],
        interpretation='Tensor differences only: no decoder rerun or physical conclusion. Fixed first saved heading origin is hypothetical; no runtime behavior changed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT/'artifacts/full-record/run-b5do1ocs/outputs/report.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = audit(args.report); save(args.output, result)
    import json
    print(json.dumps({key:value for key,value in result.items() if key != 'source_files'}, indent=2))


if __name__ == '__main__': main()
