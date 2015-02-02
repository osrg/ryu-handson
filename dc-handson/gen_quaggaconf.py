# coding: UTF-8
#!/usr/bin/env python

import os

def gen_text(neighbornum=2, router_type="spine", subnum=1):

	myAS = 0
	myid = 0
	network=[]
	route_map=[]
	network_num=0
	if router_type=="spine":
		myAS = "6500"+str(subnum)
		myid = "10."+str(subnum)+".1.1"
		for i in xrange(1,3):
			network.append("10."+str(subnum)+"."+str(i)+".0")
		for i in range(neighbornum):
			route_map.append("route-map LEAF_ROUTE"+str(i))

	else:
		myAS = "6501"+str(subnum)
		myid = "10.1."+str(subnum)+".2"
		for i in xrange(1,4):		
			network.append("10."+str(i)+"."+str(subnum)+".0")
		network.append("192.168."+str(subnum)+".0")

		for i in range(neighbornum):
			route_map.append("route-map SPINE_ROUTE"+str(i+1))


	conf_tex ="hostname "+ router_type + str(subnum)
	conf_tex += """
password zebra
log file /var/log/quagga/bgpd.log
!
!
"""
	conf_tex += "router bgp "+myAS+"\n"

	conf_tex+="bgp router-id "+myid+"\n"
	for i in range(len(network)):
		conf_tex+="network "+network[i]+"/24\n"
		
	conf_tex+="!\n!\n"

	if router_type=="spine":
		for p in range(neighbornum):
			nid = "neighbor "+"10."+str(subnum)+"."+str(p+1)+".2"
			conf_tex+= nid + " remote-as 6501"+str(p+1)+"\n"
			conf_tex+= nid + " timers 1 4\n"
			conf_tex+= nid + " version 4\n"
			conf_tex+= nid + " timers connect 1\n"
			conf_tex+= nid + " "+route_map[p]+" in\n"
			conf_tex+= "!\n!\n"
		for q in range(len(network)):
			if route_map[q]=="":
				break
			conf_tex+= route_map[q]+" permit 10 \n"
			conf_tex+= "!\n!\n"

	else:
		for p in range(neighbornum):
			nid = "neighbor "+"10."+str(p+1)+"."+str(subnum)+".1"
			conf_tex+= nid + " remote-as 6500"+str(p+1)+"\n"
			conf_tex+= nid + " timers 1 4\n"
			conf_tex+= nid + " version 4\n"
			conf_tex+= nid + " timers connect 1\n"
			conf_tex+= nid + " "+route_map[p]+" in\n"
			conf_tex+="!\n!\n"

		conf_tex+= "access-list 1 permit 192.168."+str(3 - subnum )+".0 0.0.0.255\n"
		conf_tex+= "!\n!\n"

		for q in range(neighbornum):
			if route_map[q]=="":
				break
			conf_tex+= route_map[q]+" permit 10 \n"
			conf_tex+= "\tmatch ip address 1\n"
			conf_tex+= "\tset local-preference " +str(3-q)+"00\n"
			conf_tex+= "!\n!\n"
			conf_tex+= route_map[q]+" permit 20 \n"
			conf_tex+= "!\n!\n"

	conf_tex+="""\
!
line vty
!
end"""
	return conf_tex


for i in xrange(1,4):
	dirname = "s"+str(i)
	if not os.path.exists(dirname):
		os.mkdir(dirname)
	fname=dirname+"/bgpd.conf"
	conf_tex = gen_text(2,"spine",i)
	f = open(fname, 'w')
	f.write(conf_tex)
	f.close()

for i in xrange(1,3):
	dirname = "l"+str(i)
	if not os.path.exists(dirname):
		os.mkdir(dirname)
	fname=dirname+"/bgpd.conf"
	conf_tex = gen_text(3,"leaf",i)
	f = open(fname, 'w')
	f.write(conf_tex)
	f.close()
		

