#!/usr/bin/python

import os

def gen_text(neighbornum=2, router_type="spine", subnum=1):

	myAS = 0
	myid = 0
	network=[]
	network_num=0
	if router_type=="spine":
		myAS = "6500"+str(subnum)
		myid = "10."+str(subnum)+".1.1"
		network.append("10."+str(subnum)+".1.0/24")
		network.append("10."+str(subnum)+".2.0/24")
		network_num=2

	else:
		myAS = "6501"+str(subnum)
		myid = "10.1."+str(subnum)+".2"
		network.append("10.1."+str(subnum)+".0/24")
		network.append("10.2."+str(subnum)+".0/24")
		network.append("10.3."+str(subnum)+".0/24")
		network.append("192.168."+str(subnum)+".0/24")
		network_num=4
	conf_tex ="\t\thostname "+ router_type + str(subnum)
	conf_tex += """
		password zebra
		log file /var/log/quagga/bgpd.log
		!
		!
		"""
	conf_tex += "router bgp "+myAS+"\n"

	conf_tex+="\t\tbgp router-id "+myid+"\n"
	for i in range(network_num):
		conf_tex+="\t\tnetwork "+network[i]+"\n"
		
	conf_tex+="\t\t!\n \t\t!\n"

	if router_type=="spine":
		for p in range(neighbornum):
			nid = "neighbor "+"10."+str(subnum)+"."+str(p+1)+".2"
			conf_tex+="\t\t"+nid + " remote-as 6501"+str(p+1)+"\n"
			conf_tex+="\t\t"+nid + " timers 1 4\n"
			conf_tex+="\t\t"+nid + " version 4\n"
			conf_tex+="\t\t"+nid + " timers connect 1\n"
			conf_tex+="\t\t!\n \t\t!\n"
	else:
		for p in range(neighbornum):
			nid = "neighbor "+"10."+str(p+1)+"."+str(subnum)+".1"
			conf_tex+="\t\t"+nid + " remote-as 6500"+str(p+1)+"\n"
			conf_tex+="\t\t"+nid + " timers 1 4\n"
			conf_tex+="\t\t"+nid + " version 4\n"
			conf_tex+="\t\t"+nid + " timers connect 1\n"
			conf_tex+="\t\t!\n \t\t!\n"


	conf_tex+="""\
		!
		line vty
		!
		end"""
	return conf_tex
#!/usr/bin/env python


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
	fname=dirname+"/gpd.conf"
	conf_tex = gen_text(3,"leaf",i)
	f = open(fname, 'w')
	f.write(conf_tex)
	f.close()
		

