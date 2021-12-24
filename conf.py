"""Configure for ASCAR DRL Evaluation

Copyright (c) 2016, 2017 The Regents of the University of California. All
rights reserved.

Created by Yan Li <yanli@tuneup.ai>, Kenneth Chang <kchang44@ucsc.edu>,
Oceane Bel <obel@ucsc.edu>. Storage Systems Research Center, Baskin School
of Engineering.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of the Storage Systems Research Center, the
      University of California, nor the names of its contributors
      may be used to endorse or promote products derived from this
      software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
REGENTS OF THE UNIVERSITY OF CALIFORNIA BE LIABLE FOR ANY DIRECT,
INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
OF THE POSSIBILITY OF SUCH DAMAGE.
"""
from ascar import common
from ascar import LustreCommon
import glob
import logging
import os
import socket
from typing import List

__author__ = 'Yan Li'
__copyright__ = 'Copyright (c) 2016, 2017 The Regents of the University of California. All rights reserved.'

"""Maps hostname to MA ID
"""
# 主机名映射
nodeid_map = {
    '192.168.1.11': 1,
    '192.168.1.12': 2,
    '192.168.1.13': 3,
    '192.168.1.14': 4,
}

TICK_LEN = 1
servers = [
    '192.168.1.11',
    '192.168.1.12',
]
# client 观测参数数量
PI_PER_CLIENT_OBD = 11
# clint数量
OBD_PER_CLIENT_MA = len(servers)
clients = [
    '192.168.1.13',
    '192.168.1.14',
]
# todo 控制方法的含义
# 'mrif' max rpcs in flight osc到其ost的rpc的最大并发数
# control_method can be 'mrif', 'rules', or 'mrif_tau'
control_method = 'mrif_tau'
rule_archive_path = '/share/drl/rules'

if control_method == 'mrif':
    cpv_spec = [
        # name, initial value, min, max, step size
        ['mrif', 8, 1, 256, 4],
    ]
elif control_method == 'rules':
    cpv_spec = [
        # name, initial value, min, max, step size
        ['rtt_ratio_changepoint', 237, 37, 437, 10],
        ['ewma_changepoint_a', 41001, 20001, 60001, 1000],
        ['ewma_changepoint_b', 48427, 28427, 68427, 1000],
    ]
    rule_template_file = os.path.join(rule_archive_path, 'iorcp_alpha9999_472_3cpvs.csv')
    with open(rule_template_file, 'r') as f:
        rule_template = f.read()
elif control_method == 'mrif_tau':
    cpv_spec = [
        # name, initial value, min, max, step size
        ['mrif', 8, 1, 256, 4],
        ['tau', 32840, 0, 400000, 1500],
    ]
    rule_template_file = os.path.join(rule_archive_path, 'tau_only.csv')
    with open(rule_template_file, 'r') as f:
        tau_only_rule_template = f.read()
    _tau = 0
else:
    raise RuntimeError('Unknown control method: ' + control_method)

my_hostname = socket.gethostname()


# 收集到服务器的时间
def collect_ping_to_servers() -> List[float]:
    result = []
    for srv in servers:
        # PI 7
        result.append(common.get_ping_time(srv))
    return result


'''
收集了10个环境
max_rpcs_in_flight  最大并行rpc数
min_brw_rpc_gap     
指数加权移动平均
ack_ewma 
sent_ewma
rtt_ratio100
read_bandwidth
write_bandwidth
tau
cur_dirty_bytes
max_dirty_mb
'''


def collect_osc_pi_cpv(osc_path: str) -> List[float]:
    result = list()
    # PI 0
    result.append(LustreCommon.read_proc_file(os.path.join(osc_path, 'max_rpcs_in_flight')))
    # PI 1
    result.append(LustreCommon.read_proc_file(os.path.join(osc_path, 'min_brw_rpc_gap')))

    with open(os.path.join(osc_path, 'import'), 'r') as importfile:
        # import is a proc file and should be read as a whole, i.e., not using readline()
        import_data = importfile.read()

    # PI 2
    result.append(LustreCommon.extract_ack_ewma_from_import(import_data))
    # PI 3
    result.append(LustreCommon.extract_sent_ewma_from_import(import_data))
    # PI 4
    result.append(LustreCommon.extract_rtt_ratio100_from_import(import_data))
    # PI 5
    result.append(LustreCommon.extract_read_bandwidth_from_import(import_data))
    # PI 6
    result.append(LustreCommon.extract_write_bandwidth_from_import(import_data))
    # PI 7
    result.append(_tau)
    # PI 8
    result.append(LustreCommon.read_proc_file(os.path.join(osc_path, 'cur_dirty_bytes')))
    # PI 9
    result.append(LustreCommon.read_proc_file(os.path.join(osc_path, 'max_dirty_mb')))

    return result


# 从lustre收集所有数据
def lustre_collect_pi() -> List[float]:
    if my_hostname in clients:
        # collect ping time to all servers
        ping_times = collect_ping_to_servers()
        # collect PIs
        oscs = glob.glob('/proc/fs/lustre/osc/*/import')
        """ 收集信息大致如下
import:
    name: temp-OST0004-osc-ffff9068ea7c9000
    target: temp-OST0004_UUID
    state: IDLE
    connect_flags: [ write_grant, server_lock, version, request_portal, truncate_lock, max_byte_per_rpc, early_lock_cancel, adaptive_timeouts, lru_resize, alt_checksum_algorithm, fid_is_enabled, version_recovery, grant_shrink, full20, layout_lock, 64bithash, object_max_bytes, jobstats, einprogress, grant_param, lvb_type, short_io, lfsck, bulk_mbits, second_flags, lockaheadv2 ]
    connect_data:
       flags: 0xa0425af2e3440478
       instance: 1
       target_version: 2.12.7.0
       initial_grant: 8437760
       max_brw_size: 4194304
       grant_block_size: 4096
       grant_inode_size: 32
       grant_max_extent_size: 67108864
       grant_extent_tax: 24576
       cksum_types: 0xf7
       max_object_bytes: 17592186040320
    import_flags: [ replayable, pingable, connect_tried ]
    connection:
       failover_nids: [ 192.168.1.13@tcp ]
       current_connection: 192.168.1.13@tcp
       connection_attempts: 2
       generation: 2
       in-progress_invalidations: 0
       idle: 159490 sec
    rpcs:
       inflight: 0
       unregistering: 0
       timeouts: 0
       avg_waittime: 655647 usec
    service_estimates:
       services: 31 sec
       network: 1 sec
        """
        osc_paths = [os.path.dirname(p) for p in oscs]
        osc_paths.sort()
        osc_pis = list()
        for osc in osc_paths:
            osc_pis.extend(collect_osc_pi_cpv(osc))

        result = osc_pis + ping_times
        assert len(result) == len(servers) * PI_PER_CLIENT_OBD
        return result
    elif my_hostname in servers:
        # todo 服务器
        return list()
    else:
        raise RuntimeError('My hostname is neither client or server')


# lustre 根据不同的 control_method 进行控制
def lustre_controller(cpvs: List[float]):
    """Perform an action

    Applies the CPVs to the system

    :param cpvs: the new values of CPVs
    :return:
    """
    # cpvs[0] is the action id, remove it
    cpvs = cpvs[1:]
    if my_hostname in clients:
        if control_method == 'mrif':
            mrif = int(cpvs[0])
            # 必须位于最大最小值之间
            assert cpv_spec[0][2] <= mrif <= cpv_spec[0][3]
            LustreCommon.set_mrif(mrif, len(servers))
        elif control_method == 'rules':
            # convert cpvs list to a dict
            kv = dict([('cpv{0}'.format(i + 1), int(cpv)) for i, cpv in enumerate(cpvs)])
            rule = LustreCommon.gen_rule(rule_template, kv)
            LustreCommon.set_rule(rule, len(servers))
        elif control_method == 'mrif_tau':
            global _tau
            mrif = int(cpvs[0])
            assert cpv_spec[0][2] <= mrif <= cpv_spec[0][3]
            LustreCommon.set_mrif(mrif, len(servers))

            _tau = int(cpvs[1])
            rule = LustreCommon.gen_rule(tau_only_rule_template, {'tau': _tau})
            LustreCommon.set_rule(rule, len(servers))
        else:
            raise RuntimeError('Unknown control method: ' + control_method)
    elif my_hostname in servers:
        # todo 服务器优化
        pass
    else:
        raise RuntimeError('My hostname is neither client or server')


opt = {
    'loglevel': logging.INFO,
    'log_lazy_flush': True,
    # cProfile 性能分析工具
    # Pympler 内存诊断工具
    # level 1 enables cProfile, level 2 also enables Pympler
    'ma_debugging_level': 0,
    'dqldaemon_debugging_level': 0,
    # database location
    # todo: why not only use ram ?
    'dbfile': '/data/ascar/ascar_replay_db.sqlite',
    # todo 滴答声持续时间
    'tick_len': TICK_LEN,  # duration of a tick in second
    # todo 一次观察中有多少滴答声
    'ticks_per_observation': 10,  # how many ticks are in an observation
    # 节点映射表
    'nodeid_map': nodeid_map,
    # client 节点名
    'clients': clients,
    # server 节点名
    'servers': servers,
    # 可控制参数
    'cpvs': cpv_spec,
    # todo: 加减步长和不动？那也应该是3*len(cpv_spec)
    'num_actions': 2 * len(cpv_spec) + 1,
    'pi_per_client_obd': PI_PER_CLIENT_OBD,
    'obd_per_client_ma': OBD_PER_CLIENT_MA,
    'tick_data_size': PI_PER_CLIENT_OBD * OBD_PER_CLIENT_MA * len(clients),  # only four clients have PI so far

    # Collectors are functions that collect PIs. MA calls them in order and concatenate
    # their returns into a single list before passing them to IntfDaemon
    'collectors': [lustre_collect_pi],
    'controller': lustre_controller,
    # 用于接受，存储和聚合来自mas（monitor agents）的obs
    'intf_daemon_loc': '128.114.59.20:9123',
    # moniter 代理 日志文件
    'ascar.MonitorAgent.MonitorAgent_logfile': '/root/log/ma_log.txt',
    'ascar.IntfDaemon.IntfDaemon_logfile': '/data/ascar/intfdaemon_log.txt',
    'ascar.DQLDaemon.DQLDaemon_logfile': '/data/ascar/dqldaemon_log.txt',
    'pidfile_dir': '/tmp',

    'start_random_rate': 1,
    # How many actions should the exploration period include
    'exploration_period': 1000000,
    'random_action_probability': 0.05,

    'minibatch_size': 32,
    'enable_tuning': True,
}
