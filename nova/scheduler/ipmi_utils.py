import os
import subprocess


class IPMIManager(object):
    _POWER_STATUS_ON = "Chassis Power is on"
    _POWER_STATUS_OFF = "Chassis Power is off"

    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password

    def power_status(self):
        cmd = ("ipmitool -H %s -I lan -U %s -P %s chassis power status") % (
            self.host, self.username, self.password
        )
        return subprocess.check_output(cmd, shell=True)

    def power_reset(self):
        cmd = ("ipmitool -H %s -I lan -U %s -P %s chassis power reset") % (
            self.host, self.username, self.password
        )
        return subprocess.check_output(cmd, shell=True)

    def power_off(self):
        cmd = ("ipmitool -H %s -I lan -U %s -P %s chassis power off") % (
            self.host, self.username, self.password
        )
        return subprocess.check_output(cmd, shell=True)

    def is_power_on(self):
        if self._POWER_STATUS_ON in self.power_status():
            return True
        else:
            return False
