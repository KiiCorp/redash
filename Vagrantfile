# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  config.vm.box = "minimal/xenial64"

  config.vm.network :forwarded_port, guest:5000, host:5000

  config.ssh.insert_key = false

  config.vm.provision "shell", inline: <<-SHELL
    update-locale LANG=C.UTF-8 LANGUAGE=
    sed -i.bak -e 's!http://\\(archive\\|security\\).ubuntu.com/!ftp://ftp.jaist.ac.jp/!g' /etc/apt/sources.list
    apt update

    # Docker
    apt install -y apt-transport-https ca-certificates curl software-properties-common
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
    apt-key fingerprint 0EBFCD88
    add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
    apt update
    apt install -y docker-ce
    #gwpasswd -a vagrant docker
    adduser vagrant docker

    # docker-compose
    curl -L https://github.com/docker/compose/releases/download/1.15.0/docker-compose-Linux-x86_64 -o /usr/local/bin/docker-compose
    chmod 0755 /usr/local/bin/docker-compose

    # Node
    apt-get install -y build-essential
    curl -sL https://deb.nodesource.com/setup_6.x | bash -
    apt-get install -y nodejs

  SHELL

end
