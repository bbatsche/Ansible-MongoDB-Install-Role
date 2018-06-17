Ansible Install MongoDB Role
============================

[![Build Status](https://travis-ci.org/bbatsche/Ansible-MongoDB-Role.svg?branch=master)](https://travis-ci.org/bbatsche/Ansible-MongoDB-Role)
[![Ansible Galaxy](https://img.shields.io/ansible/role/6787.svg)](https://galaxy.ansible.com/detail#/role/6787)

This Ansible role will install and lockdown a basic setup of MongoDB v3.0+

Role Variables
--------------

- `db_admin` &mdash; Admin username to be created. Default: "vagrant"
- `db_pass` &mdash; Password for admin user. Default: "vagrant"
- `mongodb_version` &mdash; Version of MongoDB to install. **Must** be a string value, either "3.0" or "3.2". Default: "3.2"
- `mongodb_log_path` &mdash; Location for MongoDB logs. Default: "/var/log/mongodb"
- `mongodb_db_path` &mdash; Location for MongoDB data files. Default: "/var/lib/mongodb"
- `mongodb_bind_ip` &mdash; IP Address for MongoDB to listen for connections. Default: "127.0.0.1"
- `mongodb_authorization` &mdash; Whether to MongoDB will require authentication to connect. Values should be either "enabled" or "disabled". Default: "enabled". Setting this to "disabled" is **strongly** discouraged.

Example Playbook
----------------

```yml
- hosts: servers
  roles:
  - { role: bbatsche.MongoDB-Install }
```

License
-------

MIT

Testing
-------

Included with this role is a set of specs for testing each task individually or as a whole. To run these tests you will first need to have [Vagrant](https://www.vagrantup.com/) and [VirtualBox](https://www.virtualbox.org/) installed. The spec files are written using [Serverspec](http://serverspec.org/) so you will need Ruby and [Bundler](http://bundler.io/).

To run the full suite of specs:

```bash
$ gem install bundler
$ bundle install
$ rake
```

The spec suite will target Ubuntu Trusty Tahr (14.04), Xenial Xerus (16.04), and Bionic Bever (18.04).

To see the available rake tasks (and specs):

```bash
$ rake -T
```

These specs are **not** meant to test for idempotence. They are meant to check that the specified tasks perform their expected steps. Idempotency is tested independently via integration testing.
