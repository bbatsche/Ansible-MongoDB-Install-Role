require_relative "bootstrap"

RSpec.configure do |config|
  config.before :suite do
    AnsibleHelper.playbook "playbooks/mongodb-install.yml"
  end
end

describe command("mongo --version") do
  its(:stdout) { should match /MongoDB shell/ }
  its(:stdout) { should match /\D3\.6\.\d+/ }

  its(:exit_status) { should eq 0 }
end

describe command("mongod --version") do
  its(:stdout) { should match /\D3\.6\.\d+/ }

  its(:exit_status) { should eq 0 }
end

describe service('mongod') do
  it { should be_running }
end

describe command('mongo -u vagrant -p vagrant admin --eval "db.system.users.count()"') do
  # its(:stdout) { should match /connecting to: admin/ }
  its(:stdout) { should match /^\d+$/ }

  its(:exit_status) { should eq 0}
end

describe command('mongo admin --eval "db.system.users.count()"') do
  # its(:stdout) { should match /connecting to: admin/ }
  its(:stdout) { should match /not authorized on admin to execute command/ }

  its(:exit_status) { should_not eq 0}
end

describe command('mongo -u vagrant -p vagrant admin --eval "db.serverStatus().storageEngine"') do
  its(:stdout) { should match /"name" : "wiredTiger"/ }
end

describe file('/sys/kernel/mm/transparent_hugepage/enabled') do
  its(:content) { should eq "always madvise [never]\n" }
end

describe file('/sys/kernel/mm/transparent_hugepage/defrag') do
  its(:content) { should eq "always madvise [never]\n" }
end
