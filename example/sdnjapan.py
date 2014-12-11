import json
import sys

from ryu.base import app_manager
from ryu.ofproto import ofproto_v1_3
from ryu.ofproto import ether
from ryu.controller import dpset
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib import ofctl_v1_3 as ofctl
from ryu.lib import hub
from ryu.lib.packet import packet, arp, ethernet
from oslo.config import cfg
from ryu.app import wsgi as app_wsgi
from ryu.app.wsgi import ControllerBase, WSGIApplication

CONF = cfg.CONF
CONF.register_opts([
    cfg.StrOpt('config', default='[]', help='config'),
    ])

class RestController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(RestController, self).__init__(req, link, data, **config)
        self.tunnels = data

    def delete(self, _req, network_id, **_kwargs):
        try:
            self.tunnels.delete_key(network_id)
        except (ryu_exc.NetworkNotFound, tunnels.TunnelKeyNotFound):
            return Response(status=404)

        return Response(status=200)

class LagoCtrl(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(LagoCtrl, self).__init__(*args, **kwargs)
        self.waiters = {}
        self.cookie = 0

        config = json.loads(CONF.config)

        port = [c['port'] for c in config if c['role'] == 'interconnect']
        assert len(port) == 1
        self.inter_port = int(port[0])

        port = [c['port'] for c in config if c['role'] == 'internet']
        assert len(port) == 1
        self.access_port = int(port[0])

        port = [c['port'] for c in config if c['role'] == 'wlc']
        assert len(port) == 1
        self.wlc_port = int(port[0])

    def _next_cookie(self):
        self.cookie += 1
        return self.cookie

    @set_ev_cls([ofp_event.EventOFPPortStatsReply,
                 ofp_event.EventOFPGroupDescStatsReply,
                 ofp_event.EventOFPTableStatsReply,
                 ofp_event.EventOFPFlowStatsReply], MAIN_DISPATCHER)
    def stats_reply_handler_v1_3(self, ev):
        msg = ev.msg
        dp = msg.datapath

        if (dp.id not in self.waiters
                or msg.xid not in self.waiters[dp.id]):
            return
        lock, msgs = self.waiters[dp.id][msg.xid]
        msgs.append(msg)

        if msg.flags:
            return
        del self.waiters[dp.id][msg.xid]
        lock.set()

    @set_ev_cls(dpset.EventDP, dpset.DPSET_EV_DISPATCHER)
    def setup_dp(self, ev):
        def _setup_dp():
            self.dp = ev.dp

            # delete all flows and groups at first
            self.logger.debug("initializing..")
            self.initialize_switch()

            # create flood to down group entry
            buckets = []
            for vid in (i+101 for i in range(3)):
                actions = [{'type':'PUSH_VLAN', 'ethertype':ether.ETH_TYPE_8021Q},
                           {'type':'SET_FIELD', 'field':'vlan_vid', 'value':vid | 0x1000},
                           {'type':'OUTPUT', 'port':self.inter_port}]
                buckets.append({'actions': actions})

            buckets.append({'actions':[{'type':'OUTPUT', 'port':self.access_port}]})
            buckets.append({'actions':[{'type':'OUTPUT', 'port':self.wlc_port}]})

            self.flood_group_ids = []

            for i in range(len(buckets)):
                group_id = self._next_cookie()
                self.flood_group_ids.append(group_id)
                b = []
                for j, e in enumerate(buckets):
                    if j != i:
                        b.append(e)
                ofctl.mod_group_entry(self.dp, {'type':'ALL', 'group_id':group_id, 'buckets':b}, self.dp.ofproto.OFPGC_ADD)

            buckets = []
            buckets.append({'actions':[{'type':'OUTPUT', 'port':self.access_port}]})
            buckets.append({'actions':[{'type':'OUTPUT', 'port':self.wlc_port}]})
            group_id = self._next_cookie()
            self.flood_group_ids.append(group_id)
            ofctl.mod_group_entry(self.dp, {'type':'ALL', 'group_id':group_id, 'buckets':buckets}, self.dp.ofproto.OFPGC_ADD)

            # create 3 meter entry
            meter_id = self._next_cookie()
            self.low_meter_id = meter_id

            meter = {'meter_id': meter_id,
                    'flags': 'KBPS',
                    'bands': [{'type': 'DROP', 'rate': 50000}]}
            ofctl.mod_meter_entry(self.dp, meter, self.dp.ofproto.OFPMC_ADD)

            meter_id = self._next_cookie()
            self.mid_meter_id = meter_id

            meter = {'meter_id': meter_id,
                    'flags': 'KBPS',
                    'bands': [{'type': 'DROP', 'rate': 30000}]}
            ofctl.mod_meter_entry(self.dp, meter, self.dp.ofproto.OFPMC_ADD)

            meter_id = self._next_cookie()
            self.high_meter_id = meter_id

            meter = {'meter_id': meter_id,
                    'flags': 'KBPS',
                    'bands': [{'type': 'DROP', 'rate': 20000}]}
            ofctl.mod_meter_entry(self.dp, meter, self.dp.ofproto.OFPMC_ADD)

            # default drop at table 0
            cmd = self.dp.ofproto.OFPFC_ADD
            flow = {'priority':0, 'table_id':0, 'cookie':self._next_cookie()}
            ofctl.mod_flow_entry(self.dp, flow, cmd)

            # default flood up at table 1
            cmd = self.dp.ofproto.OFPFC_ADD

#            match = {'in_port' : self.inter_port, 'metadata' : '101'}
            match = {'in_port' : self.inter_port}
            actions = [{'type':'GROUP', 'group_id':self.flood_group_ids[5]}]
            flow = {'match':match, 'priority':0, 'table_id':1, 'actions':actions, 'cookie':self._next_cookie()}
            ofctl.mod_flow_entry(self.dp, flow, cmd)

##            match = {'in_port' : self.inter_port, 'metadata' : '102'}
#            match = {'in_port' : self.inter_port}
#            actions = [{'type':'GROUP', 'group_id':self.flood_group_ids[1]}]
#            flow = {'match':match, 'priority':0, 'table_id':1, 'actions':actions, 'cookie':self._next_cookie()}
#            ofctl.mod_flow_entry(self.dp, flow, cmd)
#
##            match = {'in_port' : self.inter_port, 'metadata' : '103'}
#            match = {'in_port' : self.inter_port}
#            actions = [{'type':'GROUP', 'group_id':self.flood_group_ids[2]}]
#            flow = {'match':match, 'priority':0, 'table_id':1, 'actions':actions, 'cookie':self._next_cookie()}
#            ofctl.mod_flow_entry(self.dp, flow, cmd)

            match = {'in_port' : self.access_port}
            actions = [{'type':'GROUP', 'group_id':self.flood_group_ids[3]}]
            flow = {'match':match, 'priority':0, 'table_id':1, 'actions':actions, 'cookie':self._next_cookie()}
            ofctl.mod_flow_entry(self.dp, flow, cmd)

            match = {'in_port' : self.wlc_port}
            actions = [{'type':'GROUP', 'group_id':self.flood_group_ids[4]}]
            flow = {'match':match, 'priority':0, 'table_id':1, 'actions':actions, 'cookie':self._next_cookie()}
            ofctl.mod_flow_entry(self.dp, flow, cmd)

            # packet-in when node is not familier at table 0
            actions = [{'type':'OUTPUT', 'port':self.dp.ofproto.OFPP_CONTROLLER}]

            # should be more tight? may occur many packet in
            match = {'in_port' : self.inter_port}
            flow = {'match':match, 'actions':actions, 'table_id':0, 'priority':1, 'cookie':self._next_cookie()}
            ofctl.mod_flow_entry(self.dp, flow, cmd)

            match = {'in_port' : self.access_port}
            flow = {'match':match, 'actions':actions, 'table_id':0, 'priority':1, 'cookie':self._next_cookie()}
            ofctl.mod_flow_entry(self.dp, flow, cmd)

            match = {'in_port' : self.wlc_port}
            flow = {'match':match, 'actions':actions, 'table_id':0, 'priority':1, 'cookie':self._next_cookie()}
            ofctl.mod_flow_entry(self.dp, flow, cmd)

        # run in another eventlet thread to make waiter work
        hub.spawn(_setup_dp)

    def initialize_switch(self):
        flow_stat = ofctl.get_flow_stats(self.dp, self.waiters)
        for s in flow_stat[str(self.dp.id)]:
            self.logger.debug("deleting flow [cookie: %d]" % s['cookie'])
            cmd = self.dp.ofproto.OFPFC_DELETE
            ofctl.mod_flow_entry(self.dp, {'table_id':self.dp.ofproto.OFPTT_ALL}, cmd)

        group_stat = ofctl.get_group_desc(self.dp, self.waiters)
        for s in group_stat[str(self.dp.id)]:
            self.logger.debug("deleting group[id: %d] %s" % (s['group_id'], s))
            cmd = self.dp.ofproto.OFPGC_DELETE
            ofctl.mod_group_entry(self.dp, {'type':s['type'], 'group_id':s['group_id']}, cmd)

        ofctl.mod_meter_entry(self.dp, {'meter_id':self.dp.ofproto.OFPM_ALL}, self.dp.ofproto.OFPMC_DELETE)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        try:
            pkt = packet.Packet(msg.data)
        except:
            self.logger.debug("malformed packet")
            return
        header_list = dict((p.protocol_name, p)
                           for p in pkt.protocols if type(p) != str)
        self.logger.debug(header_list)

        cmd = self.dp.ofproto.OFPFC_DELETE

        dl_mac = header_list['ethernet'].src
        ofctl.mod_flow_entry(self.dp, {'table_id':0, 'match':{'dl_src':dl_mac}}, cmd)
        ofctl.mod_flow_entry(self.dp, {'table_id':1, 'match':{'dl_dst':dl_mac}}, cmd)

        cmd = self.dp.ofproto.OFPFC_ADD

        if 'vlan' in header_list:
            match = {'dl_vlan':header_list['vlan'].vid, 'dl_src':dl_mac}
            actions = [{'type':'POP_VLAN'},
#                       {'type':'WRITE_METADATA', 'metadata':str(header_list['vlan'].vid)},
                       {'type':'GOTO_TABLE', 'table_id':1}]
        else:
            match = {'dl_src':dl_mac}
            actions = [{'type':'GOTO_TABLE', 'table_id':1}]

        flow = {'match':match, 'actions':actions, 'table_id':0, 'idle_timeout':60,
                'cookie':self._next_cookie(), 'priority':20}
        ofctl.mod_flow_entry(self.dp, flow, cmd)

        match = {'dl_dst':dl_mac}

        actions = []

        if msg.match['in_port'] == self.inter_port:
            if 'vlan' in header_list:
                vid = header_list['vlan'].vid
            else:
                self.logger.debug("come from trunk port, but have no vlan header")
                return

            if vid == 101:
                self.logger.debug("add low meter flow")
                actions.append({'type':'METER', 'meter_id':self.low_meter_id})
            elif vid == 102:
                self.logger.debug("add mid meter flow")
                actions.append({'type':'METER', 'meter_id':self.mid_meter_id})
            elif vid == 103:
                self.logger.debug("add high meter flow")
                actions.append({'type':'METER', 'meter_id':self.high_meter_id})
            else:
                self.logger.debug("invalid vlan id: %d" % vid)
                return

            actions.append({'type':'PUSH_VLAN', 'ethertype': ether.ETH_TYPE_8021Q})
            actions.append({'type':'SET_FIELD', 'field':'vlan_vid', 'value':vid | 0x1000})

        actions.append({'type':'OUTPUT', 'port':msg.match['in_port']})

        flow = {'match':match, 'actions':actions, 'table_id':1, 'idle_timeout':60,
                'cookie':self._next_cookie(), 'priority':20}
        ofctl.mod_flow_entry(self.dp, flow, cmd)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        if 'vlan' in header_list:
            vid = header_list['vlan'].vid
            self.logger.debug(pkt.protocols)
            v = pkt.protocols.pop(1)
            self.logger.debug("VLAN: %s" % v)
            e = pkt.protocols[0]
            e.ethertype = v.ethertype
            self.logger.debug(pkt.protocols)
            self.logger.debug("going to serialize")
            data = pkt.serialize()
            if vid == 101:
                group_id = self.flood_group_ids[0]
            elif vid == 102:
                group_id = self.flood_group_ids[1]
            elif vid == 103:
                group_id = self.flood_group_ids[2]
            else:
                self.logger.debug("invalid vlan id: %d" % vid)
                return
            group_id = self.flood_group_ids[5]

            out = parser.OFPPacketOut(datapath=dp,
                                      buffer_id=ofproto.OFP_NO_BUFFER,
                                      in_port=msg.match['in_port'],
                                      actions=[parser.OFPActionGroup(group_id)],
                                      data=data)
        else:
            if msg.match['in_port'] == self.access_port:
                group_id = self.flood_group_ids[3]
            elif msg.match['in_port'] == self.wlc_port:
                group_id = self.flood_group_ids[4]
            else:
                self.logger.debug("invalid in_port: %d" % msg.match['in_port'])
                return

            out = parser.OFPPacketOut(datapath=dp,
                                      buffer_id=msg.buffer_id,
                                      in_port=msg.match['in_port'],
                                      actions=[parser.OFPActionGroup(group_id)],
                                      data=data)
        dp.send_msg(out)
