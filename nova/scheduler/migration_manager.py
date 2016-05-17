from oslo_config import cfg
from oslo_log import log as logging
from keystoneclient.auth.identity.generic import password  as  generic_password
from keystoneclient import session
from novaclient.client import Client

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

    def auth_migration_check(self):
        dead_hosts = self._get_dead_hosts()
        for dead_host in dead_hosts:
            self._execute_migrate(dead_host.host)

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

    def _get_dead_hosts(self):
        dead_hosts = []
        nc = self._get_novaclient()
        hosts = nc.services.list()
        for host in hosts:
            if host.binary == 'nova-compute' and host.state == 'down':
                dead_hosts.append(host)
        return dead_hosts
