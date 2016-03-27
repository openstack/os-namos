# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os
import socket
import uuid

from oslo_context import context
from oslo_log import log

from os_namos.common import rpcapi

NAMOS_RPCAPI = None
logger = log.getLogger(__name__)

# TODO(mrkanag) when more than one workers are reported per service component
# Then make the IDENTIFICATION for each worker instead. Currrently its only
# one for whole service component == PID
IDENTIFICATION = str(uuid.uuid4())
HEART_BEAT_STARTED = False
NAMOS_RPCSERVER_STARTED = False


class RegistrationInfo(object):
    def __init__(self,
                 host,
                 project_name,
                 prog_name,
                 fqdn=socket.gethostname(),
                 pid=os.getpid(),
                 config_file_list=None,
                 config_dict=None):
        self.host = host
        self.project_name = project_name
        self.fqdn = fqdn
        self.prog_name = prog_name
        self.pid = pid
        self.config_file_list = config_file_list or list()
        self.config_file_dict = self.get_config_files()
        # List of configuration which CONF is already updated with
        self.config_dict = config_dict or dict()
        self.identification = IDENTIFICATION

    def get_config_files(self):
        files = {}
        for f in self.config_file_list:
            files[f] = open(f).read()

        return files


class Config(object):
    def __init__(self,
                 name,
                 type,
                 value,
                 group='DEFAULT',
                 help=None,
                 default_value=None,
                 required=False,
                 secret=False,
                 file=None):
        self.name = name
        self.default_value = default_value
        self.help = help
        self.type = type
        self.value = value
        self.required = required
        self.secret = secret
        self.file = file
        self.group = group


def collect_registration_info():
    from oslo_config import cfg
    self = cfg.CONF

    def normalize_type(type):
        try:
            if str(type).find('function'):
                return 'String'
        except TypeError:  # noqa
            # TODO(mrkanag) why this type error occurs?
            return 'String'

        return type

    def get_host():
        try:
            return getattr(self, 'host')
        except:  # noqa
            import socket
            return socket.gethostname()

    reg_info = RegistrationInfo(host=get_host(),
                                project_name=self.project,
                                prog_name=self.prog,
                                config_file_list=self.default_config_files)

    config_dict = dict()
    for opt_name in sorted(self._opts):
        opt = self._get_opt_info(opt_name)['opt']
        cfg = Config(name='%s' % opt_name,
                     type='%s' % normalize_type(opt.type),
                     value='%s' % getattr(self, opt_name),
                     help='%s' % opt.help,
                     required=opt.required,
                     secret=opt.secret,
                     default_value='%s' % opt.default)
        config_dict[cfg.name] = cfg

    for group_name in self._groups:
        group_attr = self.GroupAttr(self, self._get_group(group_name))
        for opt_name in sorted(self._groups[group_name]._opts):
            opt = self._get_opt_info(opt_name, group_name)['opt']
            cfg = Config(name="%s" % opt_name,
                         type='%s' % normalize_type(opt.type),
                         value='%s' % getattr(group_attr, opt_name),
                         help='%s' % opt.help,
                         required=opt.required,
                         secret=opt.secret,
                         default_value='%s' % opt.default,
                         group='%s' % group_name)
            config_dict[cfg.name] = cfg
    reg_info.config_dict = config_dict

    return reg_info


def register_myself(registration_info=None,
                    start_heart_beat=True,
                    start_rpc_server=True):
    global NAMOS_RPCAPI

    if registration_info is None:
        registration_info = collect_registration_info()

    import sys
    current_module = sys.modules[__name__]

    if NAMOS_RPCAPI is None:
        NAMOS_RPCAPI = rpcapi.ConductorAPI(
            project=registration_info.project_name,
            host=registration_info.host,
            identification=registration_info.identification,
            mgr=current_module
        )

    ctx = context.RequestContext()
    NAMOS_RPCAPI.register_myself(ctx, registration_info)

    logger.info("*** [%s ]Registeration with Namos started successfully. ***" %
                registration_info.identification)

    if start_heart_beat:
        heart_beat(registration_info.identification)
    if start_rpc_server:
        manage_me()

    return registration_info.identification


def regisgration_ackw(identification):
    # TODO(mrkanag) start the heart beat here
    logger.info("*** [%s ]Registeration with Namos completed successfully. ***"
                % identification)


def heart_beat(identification):
    global HEART_BEAT_STARTED

    if HEART_BEAT_STARTED:
        return

    HEART_BEAT_STARTED = True
    from oslo_service import loopingcall
    th = loopingcall.FixedIntervalLoopingCall(NAMOS_RPCAPI.heart_beat,
                                              context=context.RequestContext(),
                                              identification=identification)
    # TODO(mrkanag) make this periods configurable
    th.start(60, 120)

    logger.info("*** [%s] HEART-BEAT with Namos is started successfully. ***" %
                identification)


def i_am_dieing():
    if NAMOS_RPCAPI:
        NAMOS_RPCAPI.heart_beat(context,
                                NAMOS_RPCAPI,
                                IDENTIFICATION,
                                True)
        logger.info("*** [%s] HEART-BEAT with Namos is stopping. ***" %
                    IDENTIFICATION)
        NAMOS_RPCAPI.stop_me()
        logger.info("*** [%s] RPC Server for Namos is stopping. ***" %
                    IDENTIFICATION)


def manage_me():
    global NAMOS_RPCSERVER_STARTED

    if NAMOS_RPCSERVER_STARTED:
        return

    NAMOS_RPCSERVER_STARTED = True
    from oslo_service import loopingcall
    th = loopingcall.FixedIntervalLoopingCall(NAMOS_RPCAPI.manage_me)
    # TODO(mrkanag) make this periods configurable
    th.start(60, 0)

    logger.info("*** [%s] RPC Server for Namos is started successfully. ***" %
                IDENTIFICATION)


def add_config(config):
    pass


def remove_config(config):
    pass


def update_config(config):
    pass


# TODO(mrkanag) Remove this before production !
if __name__ == '__main__':
    from oslo_config import cfg
    from oslo_log import log as logging

    import os_namos  # noqa

    PROJECT_NAME = 'namos'
    VERSION = '0.0.1'
    CONF = cfg.CONF

    def init_conf(prog):
        CONF(project=PROJECT_NAME,
             version=VERSION,
             prog=prog)

    def init_log(project=PROJECT_NAME):
        logging.register_options(cfg.CONF)
        logging.setup(cfg.CONF,
                      project,
                      version=VERSION)

    def read_confs():
        r = RegistrationInfo('', '', '',
                             config_file_list=['/etc/nova/nova.conf'])
        print (r.get_config_files())

    init_log()
    init_conf('test-run')

    print (register_myself())
    read_confs()
