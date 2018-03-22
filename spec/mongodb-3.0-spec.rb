require_relative "bootstrap"

RSpec.configure do |config|
  config.before :suite do
    AnsibleHelper.playbook "playbooks/mongodb-install.yml", ENV["TARGET_HOST"], mongodb_version: "3.0"
  end
end

describe command("mongo --version") do
  its(:stdout) { should match /MongoDB shell/ }
  its(:stdout) { should match /\D3\.0\.\d+/ }

  its(:exit_status) { should eq 0 }
end

describe command("mongod --version") do
  its(:stdout) { should match /\D3\.0\.\d+/ }

  its(:exit_status) { should eq 0 }
end
