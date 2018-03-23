require_relative "bootstrap"

RSpec.configure do |config|
  config.before :suite do
    AnsibleHelper.playbook "playbooks/mongodb-install.yml", ENV["TARGET_HOST"], mongodb_version: "3.0"
  end
end

context "MongoDB" do
  include_examples "mongodb", "3.0"
end
