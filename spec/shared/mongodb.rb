require "serverspec"

shared_examples "mongodb" do |version|
  describe "MongoDB Shell" do
    let(:subject) { command "mongo --version" }

    it "is installed" do
      expect(subject.stdout).to match /MongoDB shell/
    end

    it "is the correct version" do
      expect(subject.stdout).to match /\D#{Regexp.quote(version)}\.\d+/
    end

    include_examples "no errors"
  end

  describe "MongoDB Server" do
    let(:subject) { command "mongod --version" }

    it "is the correct version" do
      expect(subject.stdout).to match /\D#{Regexp.quote(version)}\.\d+/
    end

    include_examples "no errors"
  end

  describe "MongoDB Service" do
    let(:subject) { service "mongod" }

    it "is running" do
      expect(subject).to be_running
    end
  end
end
