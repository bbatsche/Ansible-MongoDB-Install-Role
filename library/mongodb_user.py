#!/usr/bin/python

# (c) 2012, Elliott Foster <elliott@fourkitchens.com>
# Sponsored by Four Kitchens http://fourkitchens.com.
# (c) 2014, Epic Games, Inc.
#
# This file was part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#
# This module has been modified to better support updating users in an idempotent manner.
# In exchange, we are knowingly opening a second connection to the database and potentially
# causing authentication failures.
# This is far from best practice, but does solve the need for being able to check
# a new user's password.

DOCUMENTATION = '''
---
module: mongodb_user
short_description: Adds or removes a user from a MongoDB database.
description:
    - Adds or removes a user from a MongoDB database.
version_added: "1.1"
options:
    login_user:
        description:
            - The username used to authenticate with
        required: false
        default: null
    login_password:
        description:
            - The password used to authenticate with
        required: false
        default: null
    login_host:
        description:
            - The host running the database
        required: false
        default: localhost
    login_port:
        description:
            - The port to connect to
        required: false
        default: 27017
    login_database:
        version_added: "2.0"
        description:
            - The database where login credentials are stored
        required: false
        default: null
    replica_set:
        version_added: "1.6"
        description:
            - Replica set to connect to (automatically connects to primary for writes)
        required: false
        default: null
    database:
        description:
            - The name of the database to add/remove the user from
        required: true
    name:
        description:
            - The name of the user to add or remove
        required: true
        default: null
        aliases: [ 'user' ]
    password:
        description:
            - The password to use for the user
        required: false
        default: null
    ssl:
        version_added: "1.8"
        description:
            - Whether to use an SSL connection when connecting to the database
        default: False
    roles:
        version_added: "1.3"
        description:
            - "The database user roles valid values could either be one or more of the following strings: 'read', 'readWrite', 'dbAdmin', 'userAdmin', 'clusterAdmin', 'readAnyDatabase', 'readWriteAnyDatabase', 'userAdminAnyDatabase', 'dbAdminAnyDatabase'"
            - "Or the following dictionary '{ db: DATABASE_NAME, role: ROLE_NAME }'."
            - "This param requires pymongo 2.5+. If it is a string, mongodb 2.4+ is also required. If it is a dictionary, mongo 2.6+  is required."
        required: false
        default: "readWrite"
    state:
        state:
        description:
            - The database user state
        required: false
        default: present
        choices: [ "present", "absent" ]

notes:
    - Requires the pymongo Python package on the remote host, version 2.4.2+. This
      can be installed using pip or the OS package manager. @see http://api.mongodb.org/python/current/installation.html
requirements: [ "pymongo" ]
author: "Elliott Foster (@elliotttf)"
'''

EXAMPLES = '''
# Create 'burgers' database user with name 'bob' and password '12345'.
- mongodb_user: database=burgers name=bob password=12345 state=present

# Create a database user via SSL (MongoDB must be compiled with the SSL option and configured properly)
- mongodb_user: database=burgers name=bob password=12345 state=present ssl=True

# Delete 'burgers' database user with name 'bob'.
- mongodb_user: database=burgers name=bob state=absent

# Define more users with various specific roles (if not defined, no roles is assigned, and the user will be added via pre mongo 2.2 style)
- mongodb_user: database=burgers name=ben password=12345 roles='read' state=present
- mongodb_user: database=burgers name=jim password=12345 roles='readWrite,dbAdmin,userAdmin' state=present
- mongodb_user: database=burgers name=joe password=12345 roles='readWriteAnyDatabase' state=present

# add a user to database in a replica set, the primary server is automatically discovered and written to
- mongodb_user: database=burgers name=bob replica_set=belcher password=12345 roles='readWriteAnyDatabase' state=present

# add a user 'oplog_reader' with read only access to the 'local' database on the replica_set 'belcher'. This is usefull for oplog access (MONGO_OPLOG_URL).
# please notice the credentials must be added to the 'admin' database because the 'local' database is not syncronized and can't receive user credentials
# To login with such user, the connection string should be MONGO_OPLOG_URL="mongodb://oplog_reader:oplog_reader_password@server1,server2/local?authSource=admin"
# This syntax requires mongodb 2.6+ and pymongo 2.5+
- mongodb_user:
    login_user: root
    login_password: root_password
    database: admin
    user: oplog_reader
    password: oplog_reader_password
    state: present
    replica_set: belcher
    roles:
     - { db: "local"  , role: "read" }

'''

import ConfigParser
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
        config   = ConfigParser.RawConfigParser()
        mongocnf = os.path.expanduser('~/.mongodb.cnf')

        try:
            config.readfp(open(mongocnf))

            self.login_user     = config.get('client', 'user')
            self.login_password = config.get('client', 'pass')
        except (ConfigParser.NoOptionError, IOError):
            return False

        return True

    def check_compatibility(self):
        srv_info = self.client.server_info()

        if LooseVersion(srv_info['version']) >= LooseVersion('3.2') and LooseVersion(PyMongoVersion) <= LooseVersion('3.2'):
            self.module.fail_json(msg=' (Note: you must use pymongo 3.2+ with MongoDB >= 3.2)')
        elif LooseVersion(srv_info['version']) >= LooseVersion('3.0') and LooseVersion(PyMongoVersion) <= LooseVersion('2.8'):
            self.module.fail_json(msg=' (Note: you must use pymongo 2.8+ with MongoDB 3.0)')
        elif LooseVersion(srv_info['version']) >= LooseVersion('2.6') and LooseVersion(PyMongoVersion) <= LooseVersion('2.7'):
            self.module.fail_json(msg=' (Note: you must use pymongo 2.7+ with MongoDB 2.6)')
        elif LooseVersion(PyMongoVersion) <= LooseVersion('2.5'):
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
            if mongo_user['user'] == user and mongo_user['db'] == self.database:
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

    def user_remove(self, user):
        if self.find(user):
            if self.module.check_mode:
                self.module.exit_json(changed=True, user=user)
            db = self.client[self.database]

            db.remove_user(user)
        else:
            self.module.exit_json(changed=False, user=user)

# We must be aware of users which can read the oplog on a replicaset
# Such users must have access to the local DB, but since this DB does not store users credentials
# and is not synchronized among replica sets, the user must be stored on the admin db
# Therefore their structure is the following :
# {
#     "_id" : "admin.oplog_reader",
#     "user" : "oplog_reader",
#     "db" : "admin",                    # <-- admin DB
#     "roles" : [
#         {
#             "role" : "read",
#             "db" : "local"             # <-- local DB
#         }
#     ]
# }
def roles_as_dict(roles, db_name):
    output = list()
    for role in roles:
        if isinstance(role, basestring):
            role = { "role": role, "db": db_name }
        output.append(role)
    return output

def roles_changed(uinfo, roles, db_name):
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
        argument_spec = dict(
            login_user=dict(default=None),
            login_password=dict(default=None),
            login_host=dict(default='localhost'),
            login_port=dict(default='27017'),
            login_database=dict(default=None),
            replica_set=dict(default=None),
            database=dict(required=True, aliases=['db']),
            name=dict(required=True, aliases=['user']),
            password=dict(aliases=['pass']),
            ssl=dict(default=False, type='bool'),
            roles=dict(default=None, type='list'),
            state=dict(default='present', choices=['absent', 'present']),
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

# import module snippets
from ansible.module_utils.basic import *
main()
