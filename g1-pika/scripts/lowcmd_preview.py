"""Pinned LowCmd memory-layout/CRC preview; never a DDS/CDR serializer or sender."""
from contextlib import contextmanager
from pathlib import Path
import struct
import subprocess
import tempfile
from sonic_startup_ablation import ROOT, sha, vector

SDK = ROOT/'vendor/GR00T-WholeBodyControl/gear_sonic_deploy/thirdparty/unitree_sdk2'
INCLUDE = SDK/'include'
PINNED = {
    'unitree/idl/hg/LowCmd_.hpp':'3e2760c3475c7a7a003785c22f1c841c186a283cc2c415019eea2a908ecae4f7',
    'unitree/idl/hg/MotorCmd_.hpp':'b1690abfafffd33ea2f6816b8e42a05ce34ab52c83c9ad2dc86ac6598c4aca70',
    'unitree/dds_wrapper/common/crc.h':'3175e111c6f8e68b69bc08dffd34ee13e581a83c81d537c41411f5a544afcb34',
}


def export_data_headers(directory):
    """Export fixed data classes/CRC ONLY; no DDS traits or SDK IO objects."""
    directory=Path(directory)
    for name,digest in PINNED.items():
        if sha(INCLUDE/name)!=digest: raise ValueError('Pinned Unitree data/CRC source changed: '+name)
    license_comment='/*\n'+(SDK/'LICENSE').read_text()+'\n*/\n'
    for source,destination in (('unitree/idl/hg/MotorCmd_.hpp','MotorCmd_data.hpp'),('unitree/idl/hg/LowCmd_.hpp','LowCmd_data.hpp')):
        text=(INCLUDE/source).read_text(); marker='\n#include "dds/topic/TopicTraits.hpp"'
        if text.count(marker)!=1: raise ValueError('Unitree data-class boundary changed')
        text=text.split(marker)[0]+'\n#endif\n'
        text=text.replace('"unitree/idl/hg/MotorCmd_.hpp"','"MotorCmd_data.hpp"')
        (directory/destination).write_text(license_comment+text)
    (directory/'CRC_data.h').write_bytes((INCLUDE/'unitree/dds_wrapper/common/crc.h').read_bytes())


@contextmanager
def binary():
    for name,digest in PINNED.items():
        if sha(INCLUDE/name)!=digest: raise ValueError('Pinned Unitree data/CRC source changed: '+name)
    with tempfile.TemporaryDirectory(prefix='g1-lowcmd-preview-') as directory:
        directory=Path(directory); export_data_headers(directory)
        output=directory/'preview'
        subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-I'+str(directory),'-I'+str(INCLUDE),
            str(Path(__file__).with_suffix('.cpp')),'-o',str(output)],check=True,timeout=30)
        yield output


def crc_words(data):
    if len(data)%4: raise ValueError('CRC requires complete words')
    crc=0xffffffff
    for word in struct.unpack('<'+str(len(data)//4)+'I',data):
        for bit in range(31,-1,-1):
            crc=((crc<<1) ^ (0x04c11db7 if crc & 0x80000000 else 0) ^
                (0x04c11db7 if word & (1<<bit) else 0)) & 0xffffffff
    return crc


def preview(commands, *, fixture_machine_id, executable):
    if type(fixture_machine_id) is not int or not 0<=fixture_machine_id<=255:
        raise ValueError('Explicit fixture machine ID required')
    if not 1<=len(commands)<=10000: raise ValueError('Bounded preview batch required')
    lines=[]
    for command in commands:
        if (command.get('schema')!='abstract_29_joint_record_NOT_Unitree_LowCmd'
                or command.get('hardware_output_enabled') is not False or command.get('robot_commands_sent') is not False):
            raise ValueError('Record-only abstract command required')
        for key in ('q','dq','tau','kp','kd'): vector(command[key],29)
        if any(value<0 for key in ('kp','kd') for value in command[key]): raise ValueError('Negative gain')
        lines.append(' '.join(map(str,[fixture_machine_id,*[command[key][i] for i in range(29) for key in ('q','dq','tau','kp','kd')]])))
    result=subprocess.run([str(executable)],input='\n'.join(lines),capture_output=True,text=True,check=True,timeout=30)
    encoded=result.stdout.splitlines()
    if len(encoded)!=len(commands): raise ValueError('Incomplete preview')
    output=[]
    for command,hexadecimal in zip(commands,encoded):
        data=bytes.fromhex(hexadecimal)
        if len(data)!=1004 or data[:4]!=bytes([0,fixture_machine_id,0,0]): raise ValueError('LowCmd header/layout changed')
        for i in range(35):
            motor=struct.unpack_from('<B3x5fI',data,4+i*28)
            if i<29:
                expected=tuple(struct.unpack('<f',struct.pack('<f',command[key][i]))[0] for key in ('q','dq','tau','kp','kd'))
                if motor!=(1,*expected,0): raise ValueError('Motor layout/order/float conversion changed')
            elif motor!=(0,0.,0.,0.,0.,0.,0): raise ValueError('Unused motor slot not disabled')
            if data[5+i*28:8+i*28]!=b'\0'*3: raise ValueError('Nonzero motor padding')
        if data[-20:-4]!=b'\0'*16: raise ValueError('Nonzero packet reserve')
        crc=struct.unpack_from('<I',data,len(data)-4)[0]
        if crc!=crc_words(data[:-4]): raise ValueError('Independent CRC mismatch')
        output.append(dict(writer_seq=command['writer_seq'],scope='native_lowcmd_memory_preview_NOT_DDS_CDR_or_sent_data',
            mode_machine_source='fixture_only_NOT_detected_robot_id',fixture_machine_id=fixture_machine_id,
            size_bytes=len(data),native_memory_hex=hexadecimal,crc=crc,hardware_ready=False,robot_commands_sent=False))
    return output
