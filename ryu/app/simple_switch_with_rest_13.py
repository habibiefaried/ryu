import json
import logging

from ryu.app import simple_switch_13
from webob import Response
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.app.wsgi import ControllerBase, WSGIApplication, route

simple_switch_instance_name = 'simple_switch_api_app'

class SimpleSwitchRest13(simple_switch_13.SimpleSwitch13):

	_CONTEXTS = {'wsgi': WSGIApplication}

	def __init__(self, *args, **kwargs):
		super(simple_switch_13.SimpleSwitch13, self).__init__(*args, **kwargs)
		self.switches = {}
		wsgi = kwargs['wsgi']
		wsgi.register(SimpleSwitchController, {simple_switch_instance_name : self})

	@set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
	def switch_features_handler(self, ev):
		super(SimpleSwitchRest13, self).switch_features_handler(ev)
		datapath = ev.msg.datapath
		self.switches[datapath.id] = datapath #dpid
		self.mac_to_port.setdefault(datapath.id, {}) #dpid

	def set_mac_to_port(self, dpid, entry):
		mac_table = self.mac_to_port.setdefault(dpid, {})
		datapath = self.switches.get(dpid)

		entry_port = entry['port']
		entry_mac = entry['mac']

		if datapath is not None:
			parser = datapath.ofproto_parser
			if entry_port not in mac_table.values():
				for mac, port in mac_table.items():

					#from known device to new device
					actions = [parser.OFPActionOutput(entry_port)]
					match = parser.OFPMatch(in_port=port, eth_dst=entry_mac)
					self.add_flow(datapath, 1, match, actions)

					#from new device to known device
					actions = [parser.OFPActionOutput(port)]
					match = parser.OFPMatch(in_port=entry_port, eth_dst=mac)
					self.add_flow(datapath, 1, match, actions)

				mac_table.update({entry_mac : entry_port})
				return mac_table
			else:
				return {"pesan": "Entry Port is already registered"}
		else:
			return {"pesan": "Datapath not found"}

	def deleteFlow(self, dpid, entry):
		mac_table = self.mac_to_port.setdefault(dpid, {})
		datapath = self.switches.get(dpid)
		entry_port = entry['port']
		entry_mac = entry['mac']
		
		if datapath is not None:
			parser = datapath.ofproto_parser
			print mac_table
			if entry_port in mac_table.values():
				for mac, port in mac_table.items():

					#from known device to new device
					match = parser.OFPMatch(in_port=port, eth_dst=entry_mac)
					self.del_flow(datapath, match)

					#from new device to known device
					match = parser.OFPMatch(in_port=entry_port, eth_dst=mac)
					self.del_flow(datapath, match)

				del mac_table[mac]
			else:
				return {"pesan": "Entry Port not found"}
		else:
			return {"pesan": "Datapath not found"}

		return mac_table

class SimpleSwitchController(ControllerBase):
	def __init__(self, req, link, data, **config):
		super(SimpleSwitchController,self).__init__(req, link, data,**config)
		self.simpl_switch_spp = data[simple_switch_instance_name]

	@route('simpleswitch', '/', methods=['GET'])
	def test(self, req, **kwargs):
		print req
		print kwargs
		body = {};
		body["pesan"] = "Welcome to Switch API with OpenFlow 1.3"
		return Response(content_type='application/json', body=json.dumps(body))
	
	@route('simpleswitch', '/simpleswitch/mactable',methods='[GET]')
	def list_all_mac_table(self, req, **kwargs):
		return Response(content_type='application/json', body=json.dumps(self.simpl_switch_spp.mac_to_port))

	@route('simpleswitch', '/simpleswitch/mactable/{dpid}', methods=['GET'])
	def list_mac_table(self, req, **kwargs):
		dpid = int(kwargs['dpid'])
		
		if dpid not in self.simpl_switch_spp.mac_to_port:
			return Response(status=404, body="DPID Not Found")

		mac_table = self.simpl_switch_spp.mac_to_port.get(dpid, {})
		return Response(content_type='application/json', body=json.dumps(mac_table))

	@route('simpleswitch', '/simpleswitch/mactable/{dpid}',  methods=['POST'])
	def put_mac_table(self, req, **kwargs):
		dpid = int(kwargs['dpid'])
		new_entry = eval(req.body)

		if dpid not in self.simpl_switch_spp.mac_to_port:
			return Response(status=404, body="DPID Not Found")

		try:
			mac_table = self.simpl_switch_spp.set_mac_to_port(dpid, new_entry)
			body = json.dumps(mac_table)
			return Response(content_type='application/json', body=body)
		except Exception as e:
			return Response(status=500, body="Internal Server Error")

	@route('simpleswitch','/simpleswitch/mactable/delete/{dpid}', methods=['POST'])
	def del_mac_table(self, req, **kwargs):
		dpid = int(kwargs['dpid'])
		if dpid not in self.simpl_switch_spp.mac_to_port:
			return Response(status=404, body="DPID Not Found")

		params = {}
		params['mac'] = req.params['mac']
		params['port'] = int(req.params['port'])

		mac_table = self.simpl_switch_spp.mac_to_port.get(dpid, {})
		if params['mac'] not in mac_table:
			return Response(status=404, body="DPID Found, but not the mac address")

		return Response(content_type='application/json', body=json.dumps(self.simpl_switch_spp.deleteFlow(dpid, params))) 