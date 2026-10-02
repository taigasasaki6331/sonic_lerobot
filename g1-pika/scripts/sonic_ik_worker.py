"""Persistent upstream IK worker for archived/measured packets; no device IO."""
import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_sonic_tcp_pipeline import prepare
from sonic_tcp_reference import TcpReference
from sonic_observation import ObservationBuilder
from sonic_reference import ReferencePacker


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--urdf',type=Path,required=True)
    parser.add_argument('--input-mode',choices=('archived','measured'),default='archived')
    args=parser.parse_args()
    with redirect_stdout(sys.stderr):
        components=(TcpReference(args.urdf),ObservationBuilder(),ReferencePacker())
        # Initialize solver/linear algebra before cameras are opened. These
        # synthetic numerical seeds never become a measured reference/output.
        reference=components[0]
        seed=reference.robot.q_zero[reference.indices].copy()
        for _ in range(3): reference.candidate([0,0,0,1,0,0,0,1,0,.04],seed)
        print('Synthetic IK initialization: 3 discarded candidates; no device IO',file=sys.stderr)
    mode='measured_input_record_only' if args.input_mode=='measured' else 'archived_record_only'
    print(json.dumps(dict(ready=True,mode=mode,hardware_output_enabled=False)),flush=True)
    expected=0
    for line in sys.stdin:
        if len(line)>2000000: raise ValueError('Oversized IK request')
        request=json.loads(line)
        if request.get('op')=='stop':
            print(json.dumps(dict(stopped=True)),flush=True); break
        if request.get('op')!='infer' or type(request.get('seq')) is not int or request['seq']!=expected:
            raise ValueError('IK request identity')
        if args.input_mode=='measured' and 'g1_state_history' not in request['frame']['capture']:
            raise ValueError('Measured input mode requires actual body history')
        with redirect_stdout(sys.stderr):
            output=prepare(dict(frames=[request['frame']]),args.urdf,components=components)
        print(json.dumps(dict(seq=expected,result=output['frames'][0],scope=output['scope'],
                              hardware_output_enabled=False),allow_nan=False),flush=True)
        expected+=1
        if expected>=10000: raise ValueError('Request count limit')


if __name__=='__main__': main()
