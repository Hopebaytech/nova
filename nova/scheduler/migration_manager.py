from oslo_config import cfg
from oslo_log import log as logging
from keystoneclient.auth.identity.generic import password  as  generic_password
from keystoneclient import session
from novaclient.client import Client
import ipmi_utils
import os
import json
import pylibmc
import sherlock
from sherlock import MCLock

LOG = logging.getLogger(__name__)

CONF = cfg.CONF
keystone_opts = [
    cfg.StrOpt('auth_uri'),
    cfg.StrOpt('username'),
    cfg.StrOpt('project_name'),
    cfg.StrOpt('password')
]

CONF.register_opts(keystone_opts,
                   group='keystone_authtoken')


class MigrationManager:
    def __init__(self, ncversion=2):
        self.auth_url = CONF.keystone_authtoken.auth_uri
        self.username = CONF.keystone_authtoken.username
        self.password = CONF.keystone_authtoken.password
        self.project_name = CONF.keystone_authtoken.project_name
        self.endpoint_type = 'internalURL'
        self.ncversion = ncversion
        self.nc = self._get_novaclient()
        self.ping_retry_nums = 3
        sherlock.configure(expire=120, timeout=20)

    def auth_migration_check(self):
        # if no memcached_server, skip auto migration function  -> need memcached server to use sherlock function
        if not CONF.memcached_servers:
            return
        self._check_hosts()

    def _execute_migrate(self, hostname):
        hypervisors = self.nc.hypervisors.search(hostname, servers=True)
        for hyper in hypervisors:
            if hasattr(hyper, 'servers'):
                LOG.info(('Start migration from: %(hostname)s'), {'hostname': hostname})
                for server in hyper.servers:
                    self._server_evacuate(server)

    def _server_evacuate(self, server):
        try:
            self.nc.servers.evacuate(server=server['uuid'], on_shared_storage=False)
            LOG.info(('Migrated instance: %(server_id)s'), {'server_id': server['uuid']})
        except Exception as e:
            LOG.error(('Error while evacuating instance-%(server_id)s: %(error_msg)s'),
                      {'server_id': server['uuid'], 'error_msg': str(e)})

    def _get_novaclient(self):
        nc = Client(self.ncversion, endpoint_type=self.endpoint_type, session=self._get_session())
        return nc

    def _get_session(self):
        auth = generic_password.Password(auth_url=self.auth_url,
                                         username=self.username, password=self.password,
                                         project_name=self.project_name)
        sess = session.Session(auth=auth)
        return sess

    def _check_hosts(self):
        nc = self._get_novaclient()
        hosts = nc.services.list()
        for host in hosts:
            if host.binary == 'nova-compute' and host.state == 'down':
                # get lock by compute hostname
                lock = self._get_lock(host.host)
                if lock.locked():  # if locked by other scheduler, continue to check next compute node
                    continue
                else:
                    lock.acquire()
                    LOG.debug('Lock host for failover: ' + host.host)
                try:
                    hypervisor_search = nc.hypervisors.search(host.host)
                    hypervisor = nc.hypervisors.get(hypervisor_search[0].id)
                    # check BMC information set in compute node
                    bmc_info = {}
                    try:
                        bmc_info = json.loads(hypervisor.extra_resources)
                    except (TypeError, ValueError) as e:
                        continue

                    if not bmc_info['failover_enabled']:
                        continue

                    ping_status = self._check_ping(hypervisor.host_ip, self.ping_retry_nums)

                    # host.disabled_reason = 'failover' represent this host already execute failover once
                    if not ping_status and host.disabled_reason != "failover":
                        ipmi_manager = ipmi_utils.IPMIManager(bmc_info['bmc_ip'], bmc_info['bmc_username'],
                                                              bmc_info['bmc_password'])
                        LOG.debug(("Auto Migration instances on compute node: %(host)s"), {'host': host.host})
                        # turn off the compute node by IPMI command
                        LOG.debug("IPMI-PowerOff: " + ipmi_manager.power_off())
                        self._execute_migrate(host.host)
                        nc.services.disable_log_reason(host.host, host.binary, "failover")
                except Exception as e:
                    LOG.error(("Auto Migration ERROR at compute node %(host)s : %(err_msg)s"),
                              {'host': host.host, 'err_msg': str(e.message)})
                finally:
                    lock.release()

    def _check_ping(self, ip, count):
        while count > 0:
            response = os.system("ping -c 1 " + ip)
            if response == 0:
                return True
            count -= 1
        else:
            return False

    def _get_lock(self, lock_name):
        client = pylibmc.Client(CONF.memcached_servers, binary=True)
        return MCLock(str(lock_name), client=client)
