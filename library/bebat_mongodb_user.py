#!/usr/bin/python

# (c) 2012, Elliott Foster <elliott@fourkitchens.com>
# Sponsored by Four Kitchens http://fourkitchens.com.
# (c) 2014, Epic Games, Inc.
#
# Modifications (c) 2016, Ben Batschelet <ben.batschelet@gmail.com>
#
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
# This module has been modified to better support updating users in an idempotent manner.
# In exchange, we are knowingly opening a second connection to the database and potentially
# causing authentication failures.
# This is far from best practice, but does solve the need for being able to check
# a new user's password.

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import os
import ssl as ssl_lib
import traceback
from distutils.version import LooseVersion

try:
    from pymongo.errors import ConnectionFailure
    from pymongo.errors import OperationFailure
    from pymongo import version as PyMongoVersion
    from pymongo import MongoClient
except ImportError:
    try:  # for older PyMongo 2.2
        from pymongo import Connection as MongoClient
    except ImportError:
        pymongo_found = False
    else:
        pymongo_found = True
else:
    pymongo_found = True

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.six import binary_type, text_type
from ansible.module_utils.six.moves import configparser
from ansible.module_utils._text import to_native

# =========================================
# MongoDB module specific support methods.
#

class MongoUser(object):
    def __init__(self, module):
        self.module = module

        self.login_user     = module.params['login_user']
        self.login_password = module.params['login_password']
        self.login_host     = module.params['login_host']
        self.login_port     = int(module.params['login_port'])
        self.login_database = module.params['login_database']

        self.replica_set = module.params['replica_set']
        self.ssl         = module.params['ssl']

        self.database = module.params['database']

        self.client = self.get_client()

        if self.login_user is None and self.login_password is None:
            if not self.load_mongocnf() and LooseVersion(PyMongoVersion) >= LooseVersion('3.0') and self.database != "admin":
               module.fail_json(msg='The localhost login exception only allows the first admin account to be created')
        elif self.login_password is None or self.login_user is None:
            module.fail_json(msg='when supplying login arguments, both login_user and login_password must be provided')

        if not self.localhost_exception():
            self.client.admin.authenticate(self.login_user, self.login_password, source=self.login_database)

        self.check_compatibility()

    def get_client(self):
        if self.replica_set:
            return MongoClient(self.login_host, self.login_port, replicaset=self.replica_set, ssl=self.ssl)
        else:
            return MongoClient(self.login_host, self.login_port, ssl=self.ssl)

    def load_mongocnf(self):
        config   = configparser.RawConfigParser()
        mongocnf = os.path.expanduser('~/.mongodb.cnf')

        try:
            config.readfp(open(mongocnf))

            self.login_user     = config.get('client', 'user')
            self.login_password = config.get('client', 'pass')
        except (configparser.NoOptionError, IOError):
            return False

        return True

    def check_compatibility(self):
        loose_srv_version = LooseVersion(self.client.server_info()['version'])
        loose_driver_version = LooseVersion(PyMongoVersion)

        if loose_srv_version >= LooseVersion('3.2') and loose_driver_version <= LooseVersion('3.2'):
            self.module.fail_json(msg=' (Note: you must use pymongo 3.2+ with MongoDB >= 3.2)')
        elif loose_srv_version >= LooseVersion('3.0') and loose_driver_version <= LooseVersion('2.8'):
            self.module.fail_json(msg=' (Note: you must use pymongo 2.8+ with MongoDB 3.0)')
        elif loose_srv_version >= LooseVersion('2.6') and loose_driver_version <= LooseVersion('2.7'):
            self.module.fail_json(msg=' (Note: you must use pymongo 2.7+ with MongoDB 2.6)')
        elif loose_srv_version <= LooseVersion('2.5'):
            self.module.fail_json(msg=' (Note: you must be on mongodb 2.4+ and pymongo 2.5+ to use the roles param)')

    def localhost_exception(self):
        return self.login_user is None and self.login_password is None \
            and LooseVersion(PyMongoVersion) >= LooseVersion('3.0') and self.database == "admin"

    def add(self, user, password, roles):
        if self.module.check_mode:
            self.module.exit_json(changed=True, user=user)

        db = self.client[self.database]

        try:
            if roles is None:
                db.add_user(user, password, False)
            else:
                db.add_user(user, password, None, roles=roles)
        except OperationFailure as e:
            self.module.fail_json(msg='Unable to add or update user: %s' % str(e))

    def find(self, user):
        for mongo_user in self.client["admin"].system.users.find():
            if mongo_user['user'] == user:
                if 'db' not in mongo_user:
                    return mongo_user

                if mongo_user['db'] == self.database:
                    return mongo_user

        return False

    def update(self, uinfo, user, password, roles):
        if roles_changed(uinfo, roles, self.database):
            self.add(user, password, roles)
        else:
            test_client = self.get_client()

            db = test_client[self.database]

            try:
                db.authenticate(user, password)

                self.module.exit_json(changed=False, user=user)
            except OperationFailure:
                # If we get an operation failure, assume authentication failed, meaning we need to change the password
                # This is...so not good practice, but it's a way to get idempotence from our task
                self.add(user, password, roles)

    def remove(self, user):
        if self.find(user):
            if self.module.check_mode:
                self.module.exit_json(changed=True, user=user)
            db = self.client[self.database]

            db.remove_user(user)
        else:
            self.module.exit_json(changed=False, user=user)

def roles_changed(uinfo, roles, db_name):
    def roles_as_dict(roles, db_name):
        output = list()
        for role in roles:
            if isinstance(role, basestring):
                role = { "role": role, "db": db_name }
            output.append(role)
        return output

    roles = roles_as_dict(roles, db_name)
    uinfo_roles = uinfo.get('roles', [])

    if sorted(roles) == sorted(uinfo_roles):
        return False
    return True

# =========================================
# Module execution.
#

def main():
    module = AnsibleModule(
        argument_spec=dict(
            login_user=dict(default=None),
            login_password=dict(default=None, no_log=True),
            login_host=dict(default='localhost'),
            login_port=dict(default='27017'),
            login_database=dict(default=None),
            replica_set=dict(default=None),
            database=dict(required=True, aliases=['db']),
            name=dict(required=True, aliases=['user']),
            password=dict(aliases=['pass'], no_log=True),
            ssl=dict(default=False, type='bool'),
            roles=dict(default=None, type='list'),
            state=dict(default='present', choices=['absent', 'present']),
            ssl_cert_reqs=dict(default='CERT_REQUIRED', choices=['CERT_NONE', 'CERT_OPTIONAL', 'CERT_REQUIRED']),
        ),
        supports_check_mode=True
    )

    if not pymongo_found:
        module.fail_json(msg='the python pymongo module is required')

    try:
        mongo_user = MongoUser(module)
    except ConnectionFailure as e:
        module.fail_json(msg='unable to connect to database: %s' % str(e))

    state = module.params['state']

    user     = module.params['name']
    password = module.params['password']
    roles    = module.params['roles']

    if state == 'present':
        if password is None:
            module.fail_json(msg='password parameter required when adding a user')

        if mongo_user.localhost_exception():
            mongo_user.add(user, password, roles)
        else:
            uinfo = mongo_user.find(user)

            if uinfo:
                mongo_user.update(uinfo, user, password, roles)
            else:
                mongo_user.add(user, password, roles)

    elif state == 'absent':
        try:
            mongo_user.remove(user)
        except OperationFailure as e:
            module.fail_json(msg='Unable to remove user: %s' % str(e))

    module.exit_json(changed=True, user=user)

if __name__ == '__main__':
    main()
