#!/bin/sh

run_ryu() {
    docker run --name ryu --expose 6633 -itd osrg/ryu /bin/bash
}

run_ovs() {
    docker run  --name ovs --link ryu:OF -p 6640:6640 -p 9001:9001 --privileged=true -d -i -t davetucker/docker-ovs:2.1.2 /usr/bin/supervisord
    docker exec ovs rmdir /usr/var/run/openvswitch
    docker exec ovs ln -s /var/run/openvswitch /usr/var/run/

    # wait for ovs
    sleep 5

    docker exec ovs ovs-vsctl add-br s0
    docker exec ovs ovs-vsctl set bridge s0 datapath_type=netdev
    docker exec ovs ovs-vsctl set bridge s0 protocols=OpenFlow13
    docker exec ovs ovs-vsctl set-fail-mode s0 secure
    local ryu_addr=`docker exec ovs env|awk -F"=" '$1 == "OF_PORT"{ print $2 }'|sed -e "s/\/\///"`
    docker exec ovs ovs-vsctl set-controller s0 $ryu_addr
}

run_host() {
    local host_name=h$1
    docker run --name $host_name -itd osrg/ryu /bin/bash
}

link_ovs_to_host() {
    local host_name=h$1
    sudo pipework br$1 -i eth$1 ovs 0/0
    sudo pipework br$1 -i eth1 $host_name 10.0.0.$1/24 02:00:00:00:00:0$1
    docker exec ovs ovs-vsctl add-port s0 eth$1
}

delete_bridge() {
    local name=$1
    local sysfs_name=/sys/class/net/$name
    if [ -e $sysfs_name ]; then
	sudo ifconfig $name down
	sudo brctl delbr $name
    fi
}

check_user() {
    if [ `whoami` = "root" ]; then
        echo "Super user cannot execute! Please execute as non super user"
        exit 2
    fi
}

case "$1" in
    start)
	run_ryu
	run_ovs
	run_host 1
	run_host 2
	run_host 3
        run_host 4

	link_ovs_to_host 1
	link_ovs_to_host 2
	link_ovs_to_host 3
	link_ovs_to_host 4
	;;
    stop)
	docker rm -f $(docker ps -qa)
	delete_bridge 1
	delete_bridge 2
	delete_bridge 3
        delete_bridge 4
	;;
    install)
        check_user
	sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 36A1D7869245C8950F966E92D8576A8BA88D21E9
	sudo sh -c "echo deb https://get.docker.io/ubuntu docker main > /etc/apt/sources.list.d/docker.list"
	sudo apt-get update
	sudo apt-get install -y --force-yes lxc-docker-1.3.2
	sudo ln -sf /usr/bin/docker.io /usr/local/bin/docker
	sudo gpasswd -a `whoami` docker
        sudo apt-get install -y --force-yes emacs23-nox
        sudo apt-get install -y --force-yes wireshark
	sudo apt-get install -y --force-yes iputils-arping
        sudo apt-get install -y --force-yes bridge-utils
        sudo apt-get install -y --force-yes tcpdump
        sudo apt-get install -y --force-yes lv
	sudo wget https://raw.github.com/jpetazzo/pipework/master/pipework -O /usr/local/bin/pipework
	sudo chmod 755 /usr/local/bin/pipework
        sudo docker pull osrg/ryu
        sudo docker pull davetucker/docker-ovs:2.1.2
	;;
    *)
        echo "Usage: ryu-docker-handson {start|stop|install}"
        exit 2
        ;;
esac
