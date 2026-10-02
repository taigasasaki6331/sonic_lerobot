"""Build the fixed train/validation RGB cache, then run the bounded small-ACT baseline."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steps',type=int,default=1000)
    args = parser.parse_args()
    if not 1 <= args.steps <= 1000:
        parser.error('Bounded baseline: 1..1000 steps')
    subprocess.run([sys.executable,'-I',str(ROOT/'scripts/build_full_rgb_cache.py')],check=True)
    subprocess.run([sys.executable,'-I',str(ROOT/'scripts/train_gpu_smoke.py'),
                    '--full-data','--steps',str(args.steps),'--checkpoint-every','500'],check=True)
    subprocess.run([sys.executable,'-I',str(ROOT/'scripts/check_full_rgb_run.py')],check=True)

if __name__ == '__main__':
    main()
