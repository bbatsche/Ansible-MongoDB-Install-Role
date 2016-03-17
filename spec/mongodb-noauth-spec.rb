require_relative "lib/ansible_helper"
require_relative "bootstrap"

RSpec.configure do |config|
  config.before :suite do
    AnsibleHelper.instance.playbook "playbooks/mongodb-install.yml", mongodb_authorization: "disabled"
  end
end

describe command('mongo admin --eval "db.system.users.count()"') do
  it "should allow a user to connect without authentication" do
    expect(subject.stdout).to match /connecting to: admin/
    expect(subject.stdout).to match /^\d+$/

    expect(subject.exit_status).to eq 0
  end
end
