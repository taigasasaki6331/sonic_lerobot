"""Saved-only 4-channel x 3-reference factorial SONIC diagnostic.

Every condition has independent unexecuted raw-action recurrence. Never import
SDK/DDS/device code; the only inference worker is the file/stdio C++ binary.
Zero-entry gravity belongs to a diagnostic tensor, not fabricated sensor state.
"""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonic_process import SonicProcess, strict_message

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ('recorded_ik', 'measured_hold', 'causal_quintic_ik')
# Bits select upstream startup tensors; unset bits retain real ten-frame history.
CHANNELS = (('q', 30, 320), ('dq', 320, 610), ('gyro', 0, 30), ('gravity', 900, 930))
SCOPE = 'saved_startup_channel_reference_factorial_not_physical_closed_loop'
MODEL_HASHES = {'model_encoder.onnx': '60be43157f57d812f38bdbb740a5de5d5d070e8840d9edc16f02a91a6d06255b',
                'model_decoder.onnx': 'c4ac2e74045e7cbfb568f15e6bf47ea7ce023df7a94322af50be223e0a628bab'}
SOURCE_HASHES = {
    'src/g1_deploy_onnx_ref.cpp': '6fa5594c372e89b4df6fe8f49114225dbfa77c2088abaddf04c555657cb1300c',
    'include/policy_parameters.hpp': 'b9332adf07c2c9b75c9b1e0756e57c7a1c2a890d8bb0aa53c3f1905fb739b791',
    'src/state_logger.cpp': '21532714aed16d7aa0faa5b4e27b5665a5022defe24daeb795b594e92c659dc0',
    'include/math_utils.hpp': 'd85de60b9f2c6a4d26b1380264b172b3380200138173998f2a64660310f3c4d5',
}
SOURCE_REPORT_SHA = '11d9cc3ad0e297f1bf0551a25b68ef66b5455ed18163936f7914a696d8013dec'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, allow_nan=False, separators=(',', ':')); stream.write('\n')


def vector(value, size):
    if not isinstance(value, list) or len(value) != size or any(
            type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 3.4028234663852886e38 for v in value):
        raise ValueError('Invalid finite vector')


def mix_tail(current, startup, mask, actions):
    vector(current, 930); vector(startup, 930)
    if type(mask) is not int or not 0 <= mask < 16: raise ValueError('Invalid channel mask')
    if len(actions) != 10: raise ValueError('Require ten prior raw actions')
    for action in actions: vector(action, 29)
    values = list(current)
    for bit, (_, begin, end) in enumerate(CHANNELS):
        if mask & (1 << bit): values[begin:end] = startup[begin:end]
    values[610:900] = list(itertools.chain.from_iterable(actions))
    return values


def startup_tail(frames, order, defaults):
    """Diagnostic-only Logger padding after CONTROL starts, normalized real quat."""
    import numpy as np
    from sonic_observation import rotation
    if not 1 <= len(frames) <= 10: raise ValueError('Invalid startup length')
    gyro = np.zeros((10, 3)); q = np.zeros((10, 29)); dq = np.zeros((10, 29))
    # quat_rotate_d(conjugate([0,0,0,0]), [0,0,-1]) is +Z in upstream zeroEntry.
    gravity = np.tile([0., 0., 1.], (10, 1))
    for i, frame in enumerate(frames, 10-len(frames)):
        gyro[i] = frame['gyroscope']
        q[i] = (np.asarray(frame['q'][:29])-defaults)[order]
        dq[i] = np.asarray(frame['dq'][:29])[order]
        gravity[i] = rotation(frame['quaternion']).T @ [0., 0., -1.]
    return np.concatenate([gyro.ravel(), q.ravel(), dq.ravel(), np.zeros(290), gravity.ravel()]).astype(np.float32).tolist()


def constants(header):
    # Compile the pinned data-only header rather than evaluate C++ expressions.
    source = '''#include <vector>
#include <iostream>
#include <iomanip>
#include "policy_parameters.hpp"
int main(){std::cout<<std::setprecision(17);
for(auto v:isaaclab_to_mujoco)std::cout<<v<<' ';std::cout<<'\\n';
for(auto v:g1_action_scale)std::cout<<v<<' ';std::cout<<'\\n';
for(auto v:default_angles)std::cout<<v<<' ';std::cout<<'\\n';}
'''
    with tempfile.TemporaryDirectory(prefix='g1-pika-constants-') as directory:
        path = Path(directory) / 'constants.cpp'; path.write_text(source)
        binary = Path(directory) / 'constants'
        subprocess.run(['g++', '-std=c++17', '-O2', '-I'+str(header.parent), str(path), '-o', str(binary)], check=True, timeout=30)
        lines = subprocess.check_output([str(binary)], text=True, timeout=5).splitlines()
    result = dict(inverse_order=list(map(int, lines[0].split())),
                  scales=list(map(float, lines[1].split())), defaults=list(map(float, lines[2].split())))
    if sorted(result['inverse_order']) != list(range(29)): raise ValueError('Inverse joint order')
    vector(result['scales'], 29); vector(result['defaults'], 29)
    return result


def prepare(report_path, baseline_directory):
    import numpy as np
    from prepare_online_ablation import prepare as prepare_reference
    from verify_online_record import verify, checked_file
    from sonic_observation import ObservationBuilder
    from audit_motion_record import joint_limits
    report_path = Path(report_path); baseline_directory = Path(baseline_directory)
    base = ROOT / 'vendor/GR00T-WholeBodyControl/gear_sonic_deploy/src/g1/g1_deploy_onnx_ref'
    sources = {str(base/name): digest for name, digest in SOURCE_HASHES.items()}
    for path, digest in sources.items():
        if sha(path) != digest: raise ValueError('Pinned source changed: '+path)
    if sha(report_path) != SOURCE_REPORT_SHA: raise ValueError('Unexpected baseline source report')
    integrity = verify(report_path); report = strict_message(report_path.read_bytes())
    if len(report['outputs']) != 150: raise ValueError('Require 150 consecutive saved periods')
    prepared = {ref: prepare_reference(report_path, ref, .4) for ref in REFERENCES}
    builder = ObservationBuilder(); body = []; recent = []; raw_quat_norm_errors = []
    timestamps = []; ticks = []
    for seq, out in enumerate(report['outputs']):
        frames = strict_message(checked_file(report_path.parent, out['body_input_record'], r'body-[0-9]{4}\.json'))['body_history']
        endpoint = dict(frames[-1]); quat = np.asarray(endpoint['quaternion'])
        raw_quat_norm_errors.append(float(abs(np.linalg.norm(quat)-1)))
        endpoint['quaternion'] = (quat / np.linalg.norm(quat)).tolist()
        timestamps.append(endpoint['receive_monotonic_s']); ticks.append(endpoint['tick'])
        recent.append(endpoint)
        current = prepared['recorded_ik']['frames'][seq]['decoder_tail']
        for ref in REFERENCES:
            if current != prepared[ref]['frames'][seq]['decoder_tail']: raise ValueError('Reference changed body template')
        startup = startup_tail(recent[-10:], builder.order, builder.defaults)
        if seq >= 9 and current != startup: raise ValueError('Body templates do not converge at period 9')
        body.append(dict(seq=seq, current_tail=current, startup_tail=startup))
    original = strict_message((baseline_directory/'prepared-01/inputs.json').read_bytes())
    for seq, item in enumerate(body):
        if (item['current_tail'] != original['frames'][seq]['current_tail']
                or item['startup_tail'] != original['frames'][seq]['startup_tail']
                or prepared['recorded_ik']['frames'][seq]['encoder'] != original['frames'][seq]['encoder']):
            raise ValueError('Independent startup input reconstruction differs')
    baseline_paths = {
        'recorded_ik': ROOT/'artifacts/sonic-replay/run-n4vkz49q/recurrent.json',
        'measured_hold': ROOT/'artifacts/sonic-replay/run-b0x8o3am/recurrent.json',
        'causal_quintic_ik': ROOT/'artifacts/sonic-replay/run-ptukt__r/recurrent.json',
        'recorded_ik_startup': baseline_directory/'results-01/startup.json',
    }
    baselines = {name: strict_message(path.read_bytes())['outputs'] for name, path in baseline_paths.items()}
    refs = {name: [{key: value for key, value in row.items() if key != 'decoder_tail'}
                  for row in prepared[name]['frames']] for name in REFERENCES}
    urdf = ROOT/'artifacts/models/g1_pika_closed.urdf'
    durations = np.diff(timestamps).tolist()
    source_paths = [report_path, urdf, Path(__file__), Path(__file__).with_name('prepare_online_ablation.py'),
                    Path(__file__).with_name('sonic_observation.py'), Path(__file__).with_name('sonic_joint_trajectory.py'),
                    baseline_directory/'prepared-01/inputs.json', *baseline_paths.values()]
    sources.update({str(path): sha(path) for path in source_paths})
    return dict(schema_version=1, scope=SCOPE, hardware_ready=False, robot_commands_sent=False,
        g1_connected=False, source_report_sha256=sha(report_path), source_files=sources,
        model_hashes=MODEL_HASHES, channels=[name for name, _, _ in CHANNELS], body_templates=body,
        references=refs, expected_baselines=baselines, transition_s=.4,
        limits=joint_limits(urdf), constants=constants(base/'include/policy_parameters.hpp'), integrity=integrity,
        saved_contract_diagnostics=dict(raw_quaternion_norm_error_max=max(raw_quat_norm_errors),
            body_endpoint_interval_min_s=min(durations), body_endpoint_interval_max_s=max(durations),
            body_tick_increments=sorted(set(b-a for a,b in zip(ticks, ticks[1:]))),
            measured_default_pose_offset_max_rad=max(abs(v-d) for row in refs['recorded_ik'] for v,d in zip(row['measured_q'], builder.defaults)),
            startup_template_different_periods=[r['seq'] for r in body if r['current_tail'] != r['startup_tail']]),
        limitations=['Fixed saved body never responds to inferred actions',
            'Zero-entry padding is a tensor ablation, not an actual sensor history',
            'No original INIT, ownership, support/contact, heading reset or physical stop reproduction',
            'Causal interpolation activation uses saved first-policy-use clock, not GPU publish clock'])


def validate(data):
    if (data.get('schema_version') != 1 or type(data['schema_version']) is not int or data.get('scope') != SCOPE
            or any(data.get(key) is not False for key in ('hardware_ready', 'robot_commands_sent', 'g1_connected'))
            or data.get('model_hashes') != MODEL_HASHES or data.get('channels') != [c[0] for c in CHANNELS]
            or data.get('source_report_sha256') != SOURCE_REPORT_SHA or data.get('transition_s') != .4):
        raise ValueError('Unsupported diagnostic schema/mode')
    constants = data['constants']
    order = constants['inverse_order']
    if any(type(v) is not int for v in order) or sorted(order) != list(range(29)):
        raise ValueError('Invalid constant joint permutation')
    vector(constants['defaults'], 29); vector(constants['scales'], 29)
    if any(v <= 0 for v in constants['scales']): raise ValueError('Invalid constant action scale')
    if set(data['references']) != set(REFERENCES) or len(data['body_templates']) != 150:
        raise ValueError('Require full 3 x 150 factorial input')
    for seq, body in enumerate(data['body_templates']):
        if type(body['seq']) is not int or body['seq'] != seq: raise ValueError('Body sequence')
        for field in ('current_tail', 'startup_tail'):
            vector(body[field], 930)
            if any(body[field][610:900]): raise ValueError('Action templates must be zero')
        if seq >= 9 and body['current_tail'] != body['startup_tail']: raise ValueError('Unexpected late body-template difference')
    for name in REFERENCES:
        rows = data['references'][name]
        if len(rows) != 150: raise ValueError('Incomplete reference')
        for seq, row in enumerate(rows):
            if type(row['seq']) is not int or row['seq'] != seq or row.get('gripper_actuated') is not False:
                raise ValueError('Reference identity/mode')
            vector(row['encoder'], 1247); vector(row['measured_q'], 29)
            width = row['gripper_width_m']
            if type(width) not in (float,int) or not math.isfinite(width) or not 0 <= width <= .1:
                raise ValueError('Invalid saved width')
    if len(data['limits']) != 29: raise ValueError('Limit schema')
    names = [limit['name'] for limit in data['limits']]
    if any(not isinstance(name, str) or not name for name in names) or len(set(names)) != 29:
        raise ValueError('Limit identity')
    for limit in data['limits']:
        if (any(type(limit[key]) not in (int, float) or not math.isfinite(limit[key]) for key in ('lower_rad','upper_rad'))
                or limit['lower_rad'] >= limit['upper_rad']):
            raise ValueError('Invalid model limit')
    if set(data['expected_baselines']) != set(REFERENCES) | {'recorded_ik_startup'}:
        raise ValueError('Baseline identity')
    for name, outputs in data['expected_baselines'].items():
        rows = data['references']['recorded_ik' if name == 'recorded_ik_startup' else name]
        if len(outputs) != len(rows): raise ValueError('Incomplete baseline')
        for row, output in zip(rows, outputs): check_result(output, row)
    return data


def infer_condition(worker, rows, templates, mask):
    if not rows or len(rows) != len(templates): raise ValueError('Incomplete condition input')
    history = [[0.] * 29 for _ in range(10)]; result = []
    for seq, (original, body) in enumerate(zip(rows, templates)):
        row = dict(original)
        row['decoder_tail'] = mix_tail(body['current_tail'], body['startup_tail'], mask, history)
        output = worker.infer(row)
        check_result(output, row)
        result.append(output); history = history[1:] + [list(output['raw_action_isaaclab'])]
    return result


def check_result(output, row):
    if type(output.get('seq')) is not int or output['seq'] != row['seq']:
        raise ValueError('Result sequence')
    for name, size in (('token',64), ('raw_action_isaaclab',29), ('q_target_hardware',29)):
        vector(output[name], size)
    if output.get('gripper_actuated') is not False or output.get('gripper_width_m') != row['gripper_width_m']:
        raise ValueError('Gripper side channel changed')


def difference(a, b, field):
    if len(a) != len(b) or not a: raise ValueError('Comparison length mismatch')
    return max(abs(x-y) for left,right in zip(a,b) for x,y in zip(left[field], right[field]))


def segments(rows, inputs, limits):
    result = {}
    for label, start, end in (('first_10',0,10), ('after_10',10,len(rows)), ('all',0,len(rows))):
        if end <= start: raise ValueError('Empty segment')
        peak = (-1.,0,0); counts = {}
        for seq in range(start,end):
            for joint, (value, measured, limit) in enumerate(zip(rows[seq]['q_target_hardware'], inputs[seq]['measured_q'], limits)):
                offset = abs(value-measured)
                if offset > peak[0]: peak = (offset,seq,joint)
                if not limit['lower_rad'] <= value <= limit['upper_rad']:
                    counts[limit['name']] = counts.get(limit['name'],0)+1
        result[label] = dict(windows=end-start, max_target_measured_offset_rad=peak[0],
            peak_seq=peak[1], peak_joint=limits[peak[2]]['name'], outside_urdf_counts=counts)
    return result


def analyze(data, conditions):
    validate(data)
    if set(conditions) != set(REFERENCES): raise ValueError('Incomplete reference conditions')
    summaries = {}; baseline_errors = {}; comparisons = {}; formula_error = 0.
    constants = data['constants']
    for ref in REFERENCES:
        rows = data['references'][ref]; sets = conditions[ref]
        if set(sets) != set(range(16)): raise ValueError('Incomplete factorial conditions')
        summaries[ref] = {}
        for mask, results in sets.items():
            if len(results) != len(rows): raise ValueError('Incomplete condition')
            for row, output in zip(rows, results):
                check_result(output, row)
                expected = [output['raw_action_isaaclab'][order]*scale+default
                    for order,scale,default in zip(constants['inverse_order'],constants['scales'],constants['defaults'])]
                formula_error = max(formula_error,max(abs(a-b) for a,b in zip(expected,output['q_target_hardware'])))
            if difference(results, sets[0], 'token') != 0: raise ValueError('Startup mask changed encoder tokens')
            summaries[ref][str(mask)] = dict(padded_channels=[name for bit,(name,_,_) in enumerate(CHANNELS) if mask & (1<<bit)],
                **segments(results, rows, data['limits']))
        baseline_errors[ref] = {field:difference(sets[0], data['expected_baselines'][ref], field)
                               for field in ('token','raw_action_isaaclab','q_target_hardware')}
        if ref == 'recorded_ik':
            baseline_errors[ref+'_startup'] = {field:difference(sets[15],data['expected_baselines'][ref+'_startup'],field)
                                             for field in ('token','raw_action_isaaclab','q_target_hardware')}
        comparisons[ref] = {}
        for bit, (name,_,_) in enumerate(CHANNELS):
            comparisons[ref][name] = {
                'single_channel_vs_current_first10_target_max_diff_rad': difference(sets[1<<bit][:10],sets[0][:10],'q_target_hardware'),
                'all_except_channel_vs_all_padding_first10_target_max_diff_rad': difference(sets[15^(1<<bit)][:10],sets[15][:10],'q_target_hardware')}
    if formula_error != 0 or any(v != 0 for row in baseline_errors.values() for v in row.values()):
        raise ValueError('Original baseline or output formula not reproduced exactly')
    return dict(scope=SCOPE, inference_completed=True, hardware_ready=False, robot_commands_sent=False,
        g1_connected=False, condition_count=48, inference_count=7200,
        conditions=summaries, baseline_max_abs_differences=baseline_errors,
        encoder_tokens_identical_across_startup_masks=True, formula_max_difference_rad=formula_error,
        channel_contrasts=comparisons, saved_contract_diagnostics=data['saved_contract_diagnostics'],
        limitations=data['limitations'], interpretation='Channel effects interact nonlinearly; offsets are not tracking errors. No physical or task acceptance.')


def execute(input_path, binary, models, output):
    input_path = Path(input_path); output = Path(output); models = Path(models)
    data = validate(strict_message(input_path.read_bytes()))
    for name, digest in MODEL_HASHES.items():
        if sha(models/name) != digest: raise ValueError('Model checksum mismatch')
    before = {name:sha(models/name) for name in ('model_encoder.onnx','model_decoder.onnx','model_encoder.trt','model_decoder.trt')}
    output.mkdir(exist_ok=False); conditions = {}; worker = None; started = time.monotonic()
    report = dict(scope=SCOPE,inference_completed=False,hardware_ready=False,robot_commands_sent=False,g1_connected=False)
    try:
        with (output/'sonic.stderr.log').open('x') as log:
            worker = SonicProcess(binary,models/'model_encoder.onnx',models/'model_decoder.onnx',log)
            try:
                for ref in REFERENCES:
                    conditions[ref] = {}
                    for mask in range(16):
                        results = infer_condition(worker,data['references'][ref],data['body_templates'],mask)
                        save(output/(ref+'-mask-'+str(mask)+'.json'),dict(outputs=results,hardware_ready=False,robot_commands_sent=False))
                        conditions[ref][mask] = results
                    print(json.dumps(dict(reference_completed=ref,conditions=16)),flush=True)
                worker.stop()
            finally: worker.close()
        report = analyze(data, conditions)
        after = {name:sha(models/name) for name in before}
        report.update(worker_exit_code=worker.process.returncode,model_and_cache_sha256_before=before,
                      model_and_cache_sha256_after=after,model_cache_unchanged=before==after)
        if before != after: raise ValueError('New deployment model/cache changed during diagnostic')
    except Exception as exc:
        report.update(inference_completed=False,error=type(exc).__name__+': '+str(exc))
    finally:
        if worker: report['worker_exit_code'] = worker.process.returncode
        report.update(input_sha256=sha(input_path),worker_sha256=sha(binary),wall_seconds=time.monotonic()-started)
        save(output/'report.json',report)
    print(json.dumps({key:value for key,value in report.items() if key!='conditions'},indent=2))
    return 0 if report['inference_completed'] else 1


def verify_saved(input_path, output):
    data = validate(strict_message(Path(input_path).read_bytes())); output = Path(output)
    report = strict_message((output/'report.json').read_bytes())
    if report.get('inference_completed') is not True or sha(input_path) != report['input_sha256']:
        raise ValueError('Incomplete or unrelated result')
    conditions = {ref:{mask:strict_message((output/(ref+'-mask-'+str(mask)+'.json')).read_bytes())['outputs']
                      for mask in range(16)} for ref in REFERENCES}
    recalculated = analyze(data,conditions)
    for key, value in recalculated.items():
        if report[key] != value: raise ValueError('Saved report summary differs: '+key)
    if report['worker_exit_code'] != 0 or report.get('model_cache_unchanged') is not True:
        raise ValueError('Worker or cache verification failed')
    before = report['model_and_cache_sha256_before']; after = report['model_and_cache_sha256_after']
    if (before != after or set(before) != set(MODEL_HASHES) | {'model_encoder.trt','model_decoder.trt'}
            or any(before.get(name) != digest for name,digest in MODEL_HASHES.items())
            or any(not isinstance(digest,str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)
                   for digest in before.values())):
        raise ValueError('Saved cache/model hashes inconsistent')
    return dict(integrity_passed=True,conditions=48,inference_count=7200,baseline_formula_and_summary_reverified=True,
                hardware_ready=False,robot_commands_sent=False,scope='saved_factored_diagnostic_integrity_only')


def factorial_contrasts(conditions):
    """All eight paired backgrounds per channel; includes each pair's own recurrence."""
    result = {}
    for ref, sets in conditions.items():
        if set(sets) != set(range(16)): raise ValueError('Incomplete factorial')
        result[ref] = {}
        for bit, (name, _, _) in enumerate(CHANNELS):
            pairs = []
            for mask in range(16):
                if mask & (1 << bit): continue
                other = mask | (1 << bit)
                pairs.append(dict(without_channel_mask=mask, with_channel_mask=other,
                    first10_target_max_abs_difference_rad=difference(sets[mask][:10],sets[other][:10],'q_target_hardware'),
                    after10_target_max_abs_difference_rad=difference(sets[mask][10:],sets[other][10:],'q_target_hardware')))
            result[ref][name] = dict(paired_backgrounds=pairs,
                first10_pair_max_min_rad=min(row['first10_target_max_abs_difference_rad'] for row in pairs),
                first10_pair_max_max_rad=max(row['first10_target_max_abs_difference_rad'] for row in pairs))
    return result


def summarize_saved(input_path, output):
    integrity = verify_saved(input_path, output)
    output = Path(output); report = strict_message((output/'report.json').read_bytes())
    conditions = {ref:{mask:strict_message((output/(ref+'-mask-'+str(mask)+'.json')).read_bytes())['outputs']
                      for mask in range(16)} for ref in REFERENCES}
    summaries = report['conditions']
    return dict(scope='saved_factorial_analysis_not_motion_approval', hardware_ready=False,
        robot_commands_sent=False, g1_connected=False, inference_performed=False, integrity=integrity,
        input_sha256=sha(input_path), source_report_sha256=sha(output/'report.json'),
        analysis_script_sha256=sha(__file__), all_channel_background_contrasts=factorial_contrasts(conditions),
        condition_count=48,
        conditions_with_any_urdf_exceedance=sum(bool(row['all']['outside_urdf_counts']) for ref in summaries.values() for row in ref.values()),
        conditions_with_urdf_exceedance_after10=sum(bool(row['after_10']['outside_urdf_counts']) for ref in summaries.values() for row in ref.values()),
        current_vs_all_padding={ref:{mask:summaries[ref][mask] for mask in ('0','15')} for ref in REFERENCES},
        interpretation='Paired differences include unexecuted recurrence. Nonlinear effects are not additive causal shares or physical tracking errors.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare','infer','verify','summarize'))
    parser.add_argument('--input',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--baseline-directory',type=Path)
    parser.add_argument('--binary',type=Path)
    parser.add_argument('--models',type=Path)
    parser.add_argument('--results',type=Path,help='Saved output directory for summarize')
    args = parser.parse_args()
    if args.operation == 'prepare':
        if not args.report or not args.baseline_directory: parser.error('prepare requires --report and --baseline-directory')
        data = prepare(args.report,args.baseline_directory); validate(data); save(args.output,data)
        print(json.dumps(dict(prepared_periods=150,conditions=48,saved_contract_diagnostics=data['saved_contract_diagnostics']),indent=2))
    elif args.operation == 'infer':
        if not args.input or not args.binary or not args.models: parser.error('infer requires input/binary/models')
        return execute(args.input,args.binary,args.models,args.output)
    elif args.operation == 'verify':
        if not args.input: parser.error('verify requires --input')
        print(json.dumps(verify_saved(args.input,args.output),indent=2))
    else:
        if not args.input or not args.results: parser.error('summarize requires --input and --results')
        result = summarize_saved(args.input,args.results); save(args.output,result)
        print(json.dumps({key:value for key,value in result.items()
            if key not in ('all_channel_background_contrasts','current_vs_all_padding')},indent=2))
    return 0


if __name__ == '__main__': raise SystemExit(main())
