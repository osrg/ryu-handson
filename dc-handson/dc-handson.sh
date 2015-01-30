#!/bin/sh

add_netns() {
    local pid=$(docker inspect --format '{{.State.Pid}}' $1)
    sudo ln -s /proc/$pid/ns/net /var/run/netns/$1
}

run_host() {
    docker run --name $1 --privileged=true --net none -itd ubuntu:14.04 /bin/bash
    add_netns $1
}

run_router() {
    head -n2 $1/bgpd.conf > $1/zebra.conf
    docker run  --name $1 --privileged=true --net none -v $PWD/$1:/etc/quagga -itd osrg/quagga
    add_netns $1
}

add_link() {
    local name1=$1
    local   if1=$2
    local   ip1=$3
    local name2=$4
    local   if2=$5
    local   ip2=$6
    sudo ip link add name ${name1}-${if1} type veth peer name ${name2}-${if2}
    sudo ip link set netns ${name1} dev ${name1}-${if1}
    sudo ip netns exec ${name1} ip link set name ${if1} dev ${name1}-${if1}
    sudo ip netns exec ${name1} ip link set up dev ${if1}
    sudo ip netns exec ${name1} ip addr add ${ip1} dev ${if1}
    sudo ip link set netns ${name2} dev ${name2}-${if2}
    sudo ip netns exec ${name2} ip link set name ${if2} dev ${name2}-${if2}
    sudo ip netns exec ${name2} ip link set up dev ${if2}
    sudo ip netns exec ${name2} ip addr add ${ip2} dev ${if2}
}

add_route() {
    local name=$1
    local prefix=$2
    local nexthop=$3
    sudo ip netns exec $name ip route add $prefix via $nexthop
}

del_link() {
    local name=$1
    local   if=$2
    sudo ip netns exec $name ip link del dev $2
}

del_all_link() {
    local cname=$1
    sudo ip netns exec $cname ip link | awk -F': ' '/^[0-9]+:/{print $2}' | grep -v lo | while read if; do
        sudo ip netns exec $cname ip link del $if
    done
}

del_all_netns() {
    docker ps -q | while read cid; do
        cname=$(docker inspect --format '{{.Name}}' $cid | tr -d /)
        sudo rm -f /var/run/netns/$cname
    done
}

check_user() {
    if [ `whoami` = "root" ]; then
        echo "Super user cannot execute! Please execute as non super user"
        exit 2
    fi
}

case "$1" in
    install)
        check_user
	sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 36A1D7869245C8950F966E92D8576A8BA88D21E9
	sudo sh -c "echo deb https://get.docker.io/ubuntu docker main > /etc/apt/sources.list.d/docker.list"
	sudo apt-get update
	sudo apt-get install -y --force-yes lxc-docker-1.3.2
	sudo ln -sf /usr/bin/docker.io /usr/local/bin/docker
	sudo gpasswd -a `whoami` docker
	sudo apt-get install -y --force-yes iputils-arping bridge-utils tcpdump lv
        sudo docker pull ubuntu:14.04
        sudo docker pull osrg/quagga
        sudo mkdir -p /var/run/netns
        python gen_quaggaconf.py
	;;
    start)
	run_host h1
	run_host h2
	run_router l1
	run_router l2
	run_router s1
	run_router s2

	add_link l1 eth0 192.168.1.1/24 h1 eth0 192.168.1.2/24
	add_link l2 eth0 192.168.2.1/24 h2 eth0 192.168.2.2/24
	add_link s1 eth1    10.1.1.1/24 l1 eth1    10.1.1.2/24
	add_link s1 eth2    10.1.2.1/24 l2 eth1    10.1.2.2/24
	add_link s2 eth1    10.2.1.1/24 l1 eth2    10.2.1.2/24
	add_link s2 eth2    10.2.2.1/24 l2 eth2    10.2.2.2/24

        add_route h1 0.0.0.0/0 192.168.1.1
        add_route h2 0.0.0.0/0 192.168.2.1

        case "$2" in
            --s3)
                run_router s3
                add_link s3 eth1 10.3.1.1/24 l1 eth3 10.3.1.2/24
                add_link s3 eth2 10.3.2.1/24 l2 eth3 10.3.2.2/24
                ;;
        esac
	;;
    stop)
        del_all_link l1
        del_all_link l2
        del_all_netns
	docker rm -f $(docker ps -qa)
	;;
    *)
        echo "Usage: $0 {install|start|stop}"
        exit 2
        ;;
esac
